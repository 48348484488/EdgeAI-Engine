#include "edgeai/Kernels.hpp"
#include <algorithm>
#include <cstring>
#include <stdexcept>
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__)) && !defined(EDGEAI_DISABLE_SIMD)
#define EDGEAI_X86_TARGET 1
#include <immintrin.h>
#else
#define EDGEAI_X86_TARGET 0
#endif
namespace edgeai {
bool avx2_available() {
#if EDGEAI_X86_TARGET
    static const bool available = [] { __builtin_cpu_init(); return bool(__builtin_cpu_supports("avx2")); }();
    return available;
#else
    return false;
#endif
}
const char* kernel_name(Kernel k) { switch(k) {case Kernel::Scalar:return "scalar";case Kernel::Lookup:return "lookup2";case Kernel::Avx2:return "avx2";default:return "auto";} }
Kernel select_kernel(std::size_t rows,std::size_t cols,Kernel k) {
    if(k==Kernel::Auto) {
        if(avx2_available() && cols>=8 && cols%4==0) return Kernel::Avx2;
        return rows>=16 && cols%4==0 ? Kernel::Lookup : Kernel::Scalar;
    }
    if(k==Kernel::Avx2 && !avx2_available()) throw std::runtime_error("AVX2 unavailable; use auto/scalar/lookup2");
    if(cols%4!=0 && k!=Kernel::Scalar) return Kernel::Scalar;
    return k;
}
namespace {
void scalar(const std::uint8_t* p,const float* s,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y) {
    for(std::size_t r=0;r<rows;++r) {
        float sum=0;const auto base=r*cols;
        for(std::size_t c=0;c<cols;++c){auto idx=base+c;unsigned code=(p[idx/4]>>((idx%4)*2))&3u;
            if(code==1)sum+=x[c];else if(code==2)sum-=x[c];}
        y[r]=sum*s[r]+b[r];
    }
}
void lookup(const std::uint8_t* p,const float* s,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y,KernelWorkspace& workspace) {
    // Row-aligned fast path. The 16-entry table covers two 2-bit weights.
    // Tables depend on x and are regenerated on every call, never cached stale.
    const auto pairs=cols/2;workspace.pairs.resize(pairs*16);
    for(std::size_t j=0;j<pairs;++j) {
        const float a[4]={0,x[j*2],-x[j*2],0};const float z[4]={0,x[j*2+1],-x[j*2+1],0};
        for(unsigned k=0;k<16;++k)workspace.pairs[j*16+k]=a[k&3]+z[k>>2];
    }
    for(std::size_t r=0;r<rows;++r){const auto* row=p+r*(cols/4);float sum0=0,sum1=0;
        for(std::size_t j=0;j<cols/4;++j){auto code=row[j];sum0+=workspace.pairs[j*32+(code&15u)];sum1+=workspace.pairs[j*32+16+(code>>4)];}
        y[r]=(sum0+sum1)*s[r]+b[r];}
}
#if EDGEAI_X86_TARGET
__attribute__((target("avx2"))) float hsum(__m256 v) {
    __m128 lo=_mm256_castps256_ps128(v),hi=_mm256_extractf128_ps(v,1);lo=_mm_add_ps(lo,hi);
    lo=_mm_hadd_ps(lo,lo);lo=_mm_hadd_ps(lo,lo);return _mm_cvtss_f32(lo);
}
__attribute__((target("avx2"))) void avx(const std::uint8_t* p,const float* s,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y) {
    const __m256i shifts=_mm256_setr_epi32(0,2,4,6,8,10,12,14),mask=_mm256_set1_epi32(3);
    const __m256i one=_mm256_set1_epi32(1),two=_mm256_set1_epi32(2);
    for(std::size_t r=0;r<rows;++r){auto* row=p+r*(cols/4);__m256 sum=_mm256_setzero_ps();std::size_t c=0;
        for(;c+8<=cols;c+=8){std::uint16_t packed;std::memcpy(&packed,row+c/4,2);
            auto codes=_mm256_and_si256(_mm256_srlv_epi32(_mm256_set1_epi32(packed),shifts),mask);
            auto xv=_mm256_loadu_ps(x+c);auto pos=_mm256_and_ps(xv,_mm256_castsi256_ps(_mm256_cmpeq_epi32(codes,one)));
            auto neg=_mm256_and_ps(xv,_mm256_castsi256_ps(_mm256_cmpeq_epi32(codes,two)));
            sum=_mm256_add_ps(sum,_mm256_sub_ps(pos,neg));}
        float total=hsum(sum);for(;c<cols;++c){auto code=(row[c/4]>>((c%4)*2))&3u;if(code==1)total+=x[c];else if(code==2)total-=x[c];}
        y[r]=total*s[r]+b[r];}
}
__attribute__((target("avx2"))) void dense_avx(const float* w,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y) {
    for(std::size_t r=0;r<rows;++r){auto* row=w+r*cols;__m256 sum=_mm256_setzero_ps();std::size_t c=0;
        for(;c+8<=cols;c+=8)sum=_mm256_add_ps(sum,_mm256_mul_ps(_mm256_loadu_ps(row+c),_mm256_loadu_ps(x+c)));
        float total=hsum(sum)+b[r];for(;c<cols;++c)total+=row[c]*x[c];y[r]=total;}
}
#endif
}
void ternary_kernel(const std::uint8_t* p,const float* s,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y,Kernel requested,KernelWorkspace* workspace) {
    auto k=select_kernel(rows,cols,requested);
    if(k==Kernel::Lookup){KernelWorkspace local;lookup(p,s,b,rows,cols,x,y,workspace?*workspace:local);return;}
#if EDGEAI_X86_TARGET
    if(k==Kernel::Avx2){avx(p,s,b,rows,cols,x,y);return;}
#endif
    scalar(p,s,b,rows,cols,x,y);
}
void dense_kernel(const float* w,const float* b,std::size_t rows,std::size_t cols,const float* x,float* y,Kernel requested) {
    if(requested==Kernel::Avx2 && !avx2_available())throw std::runtime_error("AVX2 unavailable");
#if EDGEAI_X86_TARGET
    if((requested==Kernel::Auto&&avx2_available())||requested==Kernel::Avx2){dense_avx(w,b,rows,cols,x,y);return;}
#endif
    for(std::size_t r=0;r<rows;++r){float s=b[r];for(std::size_t c=0;c<cols;++c)s+=w[r*cols+c]*x[c];y[r]=s;}
}
}
