#include "edgeai/TernaryBackend.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace edgeai {
namespace {
inline float silu(float x){return x/(1.0f+std::exp(-x));}
void normalize_inplace(std::vector<float>& x){
    if(x.empty()) return;
    float mean=std::accumulate(x.begin(),x.end(),0.0f)/float(x.size());
    float var=0.0f; for(float v:x){float d=v-mean;var+=d*d;}
    var/=float(x.size()); float inv=1.0f/std::sqrt(var+1e-5f);
    for(float&v:x)v=(v-mean)*inv;
}
float max_softmax_confidence(const std::vector<float>& z){
    if(z.empty()) return 0;
    float mx=*std::max_element(z.begin(),z.end()); double sum=0;
    for(float v:z) sum+=std::exp(double(v-mx));
    return float(1.0/sum); // max exp is 1
}
std::uint8_t argmax_byte(const std::vector<float>& logits){ return static_cast<std::uint8_t>(std::distance(logits.begin(),std::max_element(logits.begin(),logits.end()))); }
}

TernaryBackend::TernaryBackend(const std::string& p,Kernel kernel):TernaryBackend(EdgeModel::load(p),kernel){}
TernaryBackend::TernaryBackend(EdgeModel m,Kernel kernel):model_(std::move(m)),kernel_(kernel){if(!model_.valid())throw std::invalid_argument("invalid legacy model");select_kernel(model_.config.dim,model_.config.dim,kernel_);}

void TernaryBackend::consume_token(std::uint8_t tok,std::vector<float>& state) const {
    const std::size_t d=model_.config.dim; const float* emb=model_.embedding.data()+std::size_t(tok)*d;
    std::vector<float> x(d),a(d),b(d);for(std::size_t i=0;i<d;++i)x[i]=emb[i];
    model_.wx.matvec_into(x.data(),d,a.data(),d,kernel_);model_.wh.matvec_into(state.data(),d,b.data(),d,kernel_);
    for(std::size_t i=0;i<d;++i)state[i]=std::tanh(a[i]+b[i]);
}
void TernaryBackend::logits_for(const std::vector<float>& state,std::vector<float>& logits) const { model_.output.matvec_into(state.data(),state.size(),logits.data(),logits.size(),kernel_==Kernel::Lookup?Kernel::Scalar:kernel_); }
std::size_t TernaryBackend::reason(std::vector<float>& state,const Budget& budget,std::vector<float>& logits) const {
    const std::size_t d=model_.config.dim,h=model_.config.hidden_dim;
    if(budget.max_loops<model_.config.default_loops)throw std::invalid_argument("budget below trained loop count");
    const std::size_t limit=model_.config.default_loops;
    std::vector<float> norm(d),up(h),down(d);std::size_t used=0;
    for(std::size_t loop=0;loop<limit;++loop){
        norm=state;normalize_inplace(norm);model_.reason_up.matvec_into(norm.data(),d,up.data(),h,kernel_);for(float&v:up)v=silu(v);model_.reason_down.matvec_into(up.data(),h,down.data(),d,kernel_);for(std::size_t i=0;i<d;++i)state[i]+=0.5f*down[i];
        ++used; logits_for(state,logits);// No uncalibrated confidence-based early exit.
    }return used;
}
std::vector<float> TernaryBackend::forward_token(std::uint8_t token,std::vector<float>& state)const{
 if(state.size()!=model_.config.dim)throw std::invalid_argument("state dimension mismatch");
 consume_token(token,state);auto copy=state;std::vector<float> logits(256);Budget b{model_.config.default_loops,1,1,1};reason(copy,b,logits);return logits;
}
Response TernaryBackend::infer(const std::string& prompt,const Budget& budget){
    if(!budget.max_context_chars||budget.max_loops<model_.config.default_loops)throw std::invalid_argument("insufficient model budget");
    std::vector<float> state(model_.config.dim,0.0f),logits(model_.config.vocab_size);std::size_t begin=prompt.size()>budget.max_context_chars?prompt.size()-budget.max_context_chars:0;
    for(std::size_t i=begin;i<prompt.size();++i)consume_token(static_cast<std::uint8_t>(static_cast<unsigned char>(prompt[i])),state);
    const std::size_t max_tokens=std::min<std::size_t>(model_.config.max_generate,96);std::string out;out.reserve(max_tokens);std::size_t total_loops=0;float conf=0.0f;
    for(std::size_t t=0;t<max_tokens;++t){ auto readout=state; total_loops+=reason(readout,budget,logits);conf=max_softmax_confidence(logits);auto tok=argmax_byte(logits);if(tok=='\n'&&t>8)break; auto display=tok;if(display<9||(display>13&&display<32))display=' ';out.push_back(static_cast<char>(display));consume_token(tok,state); }
    last_generated_tokens_=out.size();if(out.empty())out="[modelo não gerou texto]";return {out,RouteKind::Neural,true,total_loops,double(conf)};
}
}
