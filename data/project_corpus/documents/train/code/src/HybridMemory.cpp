#include "edgeai/HybridMemory.hpp"
#include "edgeai/Binary.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace edgeai {
namespace {
void vec_check(const std::vector<float>& x,std::size_t n){if(x.size()!=n||!binary::finite(x.data(),x.size()))throw std::invalid_argument("memory vector shape/nonfinite value");}
}
DeltaMemory::DeltaMemory(std::size_t k,std::size_t v):kd_(k),vd_(v),state_(binary::count(k,v),0),prediction_(v,0){}
void DeltaMemory::reset(){std::fill(state_.begin(),state_.end(),0);std::fill(prediction_.begin(),prediction_.end(),0);}
void DeltaMemory::update(const std::vector<float>& k,const std::vector<float>& v,float a,float beta){
    vec_check(k,kd_);vec_check(v,vd_);
    if(!std::isfinite(a)||!std::isfinite(beta)||a<0||a>1||beta<0||beta>1)throw std::invalid_argument("memory gates must be in [0,1]");
    float norm=0;for(float z:k)norm+=z*z;if(norm>1.001f)throw std::invalid_argument("delta keys must have norm <= 1");
    std::fill(prediction_.begin(),prediction_.end(),0);
    for(std::size_t i=0;i<kd_;++i)for(std::size_t j=0;j<vd_;++j){auto& z=state_[i*vd_+j];z*=a;prediction_[j]+=k[i]*z;}
    for(std::size_t i=0;i<kd_;++i)for(std::size_t j=0;j<vd_;++j)state_[i*vd_+j]+=beta*k[i]*(v[j]-prediction_[j]);
}
void DeltaMemory::read(const std::vector<float>& q,std::vector<float>& out)const{
    vec_check(q,kd_);if(out.size()!=vd_)throw std::invalid_argument("memory output shape");std::fill(out.begin(),out.end(),0);
    for(std::size_t i=0;i<kd_;++i)for(std::size_t j=0;j<vd_;++j)out[j]+=q[i]*state_[i*vd_+j];
}
LocalAttention::LocalAttention(std::size_t k,std::size_t v,std::size_t w):kd_(k),vd_(v),window_(w),keys_(binary::count(k,w),0),values_(binary::count(v,w),0),scores_(w,0){}
void LocalAttention::reset(){next_=0;used_=0;std::fill(keys_.begin(),keys_.end(),0);std::fill(values_.begin(),values_.end(),0);}
void LocalAttention::push(const std::vector<float>& k,const std::vector<float>& v){vec_check(k,kd_);vec_check(v,vd_);std::copy(k.begin(),k.end(),keys_.begin()+next_*kd_);std::copy(v.begin(),v.end(),values_.begin()+next_*vd_);next_=(next_+1)%window_;used_=std::min(used_+1,window_);}
void LocalAttention::read(const std::vector<float>& q,std::vector<float>& out){
    vec_check(q,kd_);if(out.size()!=vd_)throw std::invalid_argument("attention output shape");std::fill(out.begin(),out.end(),0);if(!used_)return;
    float mx=-std::numeric_limits<float>::infinity();const float temperature=std::sqrt(float(kd_));
    for(std::size_t t=0;t<used_;++t){auto slot=(next_+window_-used_+t)%window_;float score=0;for(std::size_t j=0;j<kd_;++j)score+=q[j]*keys_[slot*kd_+j];scores_[t]=score*temperature;mx=std::max(mx,scores_[t]);}
    float sum=0;for(std::size_t t=0;t<used_;++t){scores_[t]=std::exp(scores_[t]-mx);sum+=scores_[t];}
    for(std::size_t t=0;t<used_;++t){auto slot=(next_+window_-used_+t)%window_;float w=scores_[t]/sum;for(std::size_t j=0;j<vd_;++j)out[j]+=w*values_[slot*vd_+j];}
}
}
