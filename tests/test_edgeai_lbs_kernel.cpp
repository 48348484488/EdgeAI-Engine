#include "edgeai_lbs_kernel.hpp"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <random>

// Independent reference reproduces the original per-influence LBS loops.
static void reference(const float* matrices, const std::uint16_t* indices,
                      const float* weights, int count, const float* p,
                      const float* n, float* outP, float* outN) {
    for (int row = 0; row < 3; ++row) outP[row] = outN[row] = 0.f;
    for (int k = 0; k < count; ++k) {
        if (weights[k] <= 0.f) continue;
        const float* m = matrices + 16 * indices[k];
        for (int row = 0; row < 3; ++row) {
            outP[row] += weights[k] * (m[4*row]*p[0] + m[4*row+1]*p[1] +
                                      m[4*row+2]*p[2] + m[4*row+3]);
            outN[row] += weights[k] * (m[4*row]*n[0] + m[4*row+1]*n[1] +
                                      m[4*row+2]*n[2]);
        }
    }
    const float norm = std::sqrt(outN[0]*outN[0] +
                                 outN[1]*outN[1] + outN[2]*outN[2]);
    if (norm > 1.e-7f) for (int i = 0; i < 3; ++i) outN[i] /= norm;
}
int main() {
    std::mt19937 rng(20261030);
    std::uniform_real_distribution<float> rnd(-1.f, 1.f);
    std::uniform_real_distribution<float> weight(0.f, 1.f);
    float matrices[16*16] = {};
    for (int b = 0; b < 16; ++b) {
        const float theta = rnd(rng)*3.14159265f;
        float c=std::cos(theta),s=std::sin(theta);
        float* m=matrices+16*b;
        m[0]=c; m[1]=-s; m[2]=0; m[3]=rnd(rng)*20;
        m[4]=s; m[5]=c; m[6]=0; m[7]=rnd(rng)*20;
        m[8]=0; m[9]=0; m[10]=1; m[11]=rnd(rng)*20;
        m[15]=1;
    }
    float largestPosition=0,largestNormal=0;
    for (int sample=0;sample<100000;++sample) {
        const int count=1+(sample%8);
        std::uint16_t indices[8]; float weights[8];
        float sum=0;
        for(int k=0;k<count;++k) {
            indices[k]=std::uint16_t(rng()%16);
            weights[k]=(sample%11==0 && k==0)?0.f:weight(rng);
            sum+=weights[k];
        }
        if (sum>0) for(int k=0;k<count;++k) weights[k]/=sum;
        float p[3]={rnd(rng)*50,rnd(rng)*50,rnd(rng)*50};
        float n[3]={rnd(rng),rnd(rng),rnd(rng)};
        float a[3],b[3],c[3],d[3];
        reference(matrices,indices,weights,count,p,n,a,b);
        edgeai_lbs::skin_vertex(matrices,indices,weights,count,p,n,c,d);
        for(int k=0;k<3;++k){
            largestPosition=std::max(largestPosition,std::abs(a[k]-c[k]));
            largestNormal=std::max(largestNormal,std::abs(b[k]-d[k]));
            assert(std::isfinite(c[k]) && std::isfinite(d[k]));
            assert(std::abs(a[k]-c[k])<1.e-4f);
            assert(std::abs(b[k]-d[k])<1.e-4f);
        }
    }
    std::printf("LBS_DIFFERENTIAL_PASS cases=100000 max_position_delta=%.9g max_normal_delta=%.9g\n",
                largestPosition,largestNormal);
}
