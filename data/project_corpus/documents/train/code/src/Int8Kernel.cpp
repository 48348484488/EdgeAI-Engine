#include "edgeai/Kernels.hpp"
#include <cstring>
#include <stdexcept>
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__)) && !defined(EDGEAI_DISABLE_SIMD)
#define EDGEAI_INT8_AVX 1
#include <immintrin.h>
#else
#define EDGEAI_INT8_AVX 0
#endif
namespace edgeai {
namespace {
#if EDGEAI_INT8_AVX
__attribute__((target("avx2"))) void int8_avx(
    const std::int8_t*w,const float*s,const float*b,std::size_t rows,
    std::size_t cols,const float*x,float*y){
    for(std::size_t r=0;r<rows;++r){
        const auto*row=w+r*cols;__m256 sum=_mm256_setzero_ps();std::size_t c=0;
        for(;c+8<=cols;c+=8){
            __m128i raw=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(row+c));
            __m256 weights=_mm256_cvtepi32_ps(_mm256_cvtepi8_epi32(raw));
            sum=_mm256_add_ps(sum,_mm256_mul_ps(weights,_mm256_loadu_ps(x+c)));
        }
        __m128 h=_mm_add_ps(_mm256_castps256_ps128(sum),_mm256_extractf128_ps(sum,1));
        h=_mm_hadd_ps(h,h);h=_mm_hadd_ps(h,h);float total=_mm_cvtss_f32(h);
        for(;c<cols;++c)total+=float(row[c])*x[c];
        y[r]=total*s[r]+b[r];
    }
}
#endif
}
void int8_kernel(const std::int8_t*w,const float*s,const float*b,
                 std::size_t rows,std::size_t cols,const float*x,float*y,Kernel requested){
    if(requested==Kernel::Avx2&&!avx2_available())throw std::runtime_error("AVX2 unavailable");
#if EDGEAI_INT8_AVX
    if(requested==Kernel::Avx2||(requested==Kernel::Auto&&avx2_available())){
        int8_avx(w,s,b,rows,cols,x,y);return;
    }
#endif
    // Lookup is a ternary-only algorithm; use scalar for an explicit lookup request.
    for(std::size_t r=0;r<rows;++r){float total=0;for(std::size_t c=0;c<cols;++c)total+=float(w[r*cols+c])*x[c];y[r]=total*s[r]+b[r];}
}
}
