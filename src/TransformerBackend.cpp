#include "edgeai/TransformerBackend.hpp"
#include "edgeai/Text.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
namespace edgeai { namespace {
TransformerModel checked(TransformerModel m){if(!m.valid())throw std::invalid_argument("invalid Transformer model");if(m.config.blocks!=1)throw std::invalid_argument("multi-block runtime requires v0.12 backend");return m;}
void normalize(const std::vector<float>&x,std::vector<float>&y){float mean=std::accumulate(x.begin(),x.end(),0.f)/x.size(),var=0;for(float z:x)var+=(z-mean)*(z-mean);float inv=1/std::sqrt(var/x.size()+1e-5f);for(std::size_t j=0;j<x.size();++j)y[j]=(x[j]-mean)*inv;}
float sigmoid(float x){return x>=0?1/(1+std::exp(-x)):std::exp(x)/(1+std::exp(x));}
}
TransformerBackend::TransformerBackend(TransformerModel m,Kernel k):model_(checked(std::move(m))),kernel_(k),emb_(model_.config.dim),norm_(model_.config.dim),q_(model_.config.dim),k_(model_.config.dim),v_(model_.config.dim),near_(model_.config.dim),projected_(model_.config.dim),h_(model_.config.dim),up_(model_.config.hidden),down_(model_.config.dim),logits_(model_.tokenizer.vocab_size()),keys_(model_.config.window*model_.config.dim),values_(keys_.size()),scores_(model_.config.window),freq_(model_.config.dim/2){
    select_kernel(model_.config.dim,model_.config.dim,kernel_);
    for(std::size_t j=0;j<freq_.size();++j)freq_[j]=static_cast<float>(std::pow(double(model_.config.rope_base),-2.*j/model_.config.dim));
}
TransformerBackend::TransformerBackend(const std::string&p,Kernel k):TransformerBackend(TransformerModel::load(p),k){}
void TransformerBackend::reset(){tokens_seen_=next_=used_=0;std::fill(logits_.begin(),logits_.end(),0);}
const std::vector<float>&TransformerBackend::step(std::uint32_t token){
    if(token>=model_.tokenizer.vocab_size())throw std::out_of_range("token out of model vocabulary");
    const auto&c=model_.config;
    if(tokens_seen_>=16777216)throw std::runtime_error("reset required before RoPE position exceeds FP32 exact-integer range");
    auto mv=[&](const MixedMatrix&m,const std::vector<float>&x,std::vector<float>&y){m.matvec_into(x.data(),x.size(),y.data(),y.size(),kernel_,&workspace_);};
    std::copy_n(model_.embedding.data()+std::size_t(token)*c.dim,c.dim,emb_.data());normalize(emb_,norm_);
    const auto&block=model_.blocks_data.front();
    mv(block.query,norm_,q_);mv(block.key,norm_,k_);mv(block.value,norm_,v_);
    for(std::size_t j=0;j<freq_.size();++j){float angle=static_cast<float>(tokens_seen_)*freq_[j],cs=std::cos(angle),sn=std::sin(angle);
        for(auto*x:{&q_,&k_}){float a=(*x)[2*j],b=(*x)[2*j+1];(*x)[2*j]=a*cs-b*sn;(*x)[2*j+1]=a*sn+b*cs;}}
    std::copy(k_.begin(),k_.end(),keys_.begin()+next_*c.dim);std::copy(v_.begin(),v_.end(),values_.begin()+next_*c.dim);
    next_=(next_+1)%c.window;used_=std::min(used_+1,std::size_t(c.window));
    float mx=-std::numeric_limits<float>::infinity();const float scale=1/std::sqrt(float(c.dim));
    for(std::size_t t=0;t<used_;++t){auto slot=(next_+c.window-used_+t)%c.window;float z=0;for(std::size_t j=0;j<c.dim;++j)z+=q_[j]*keys_[slot*c.dim+j];scores_[t]=z*scale;mx=std::max(mx,scores_[t]);}
    float sum=0;for(std::size_t t=0;t<used_;++t){scores_[t]=std::exp(scores_[t]-mx);sum+=scores_[t];}
    std::fill(near_.begin(),near_.end(),0);
    for(std::size_t t=0;t<used_;++t){auto slot=(next_+c.window-used_+t)%c.window;float wt=scores_[t]/sum;for(std::size_t j=0;j<c.dim;++j)near_[j]+=wt*values_[slot*c.dim+j];}
    mv(block.project,near_,projected_);for(std::size_t j=0;j<c.dim;++j)h_[j]=emb_[j]+projected_[j];
    normalize(h_,norm_);mv(block.up,norm_,up_);for(auto&z:up_)z*=sigmoid(z);mv(block.down,up_,down_);
    for(std::size_t j=0;j<c.dim;++j)h_[j]+=.5f*down_[j];
    normalize(h_,norm_);mv(model_.output,norm_,logits_);
    for(float z:logits_)if(!std::isfinite(z))throw std::runtime_error("nonfinite Transformer output; invalid numeric range");
    ++tokens_seen_;return logits_;
}
std::size_t TransformerBackend::numeric_working_bytes()const{
    std::size_t n=0;for(const auto*p:{&emb_,&norm_,&q_,&k_,&v_,&near_,&projected_,&h_,&up_,&down_,&logits_,&keys_,&values_,&scores_,&freq_})n+=p->size();return n*sizeof(float)+workspace_.bytes();
}
std::uint32_t TransformerBackend::greedy_token()const{
    const auto&tok=model_.tokenizer;std::uint32_t best=0;
    for(std::uint32_t id=1;id<logits_.size();++id){
        if(tok.has_bos()&&id==tok.bos_id())continue;
        if(tok.has_eos()&&id==tok.response_id())continue;
        if(logits_[id]>logits_[best])best=id;
    }
    return best;
}
Response TransformerBackend::infer(const std::string&prompt,const Budget&b){
    if(!b.max_context_chars||!b.max_loops)throw std::invalid_argument("budget cannot run Transformer");
    reset();
    const auto&tok=model_.tokenizer;
    auto raw_prompt=prompt.substr(prompt.size()>b.max_context_chars?prompt.size()-b.max_context_chars:0);
    auto ids=tok.encode_prompt(raw_prompt);
    if(ids.empty())ids.push_back('\n');
    for(auto t:ids)step(t);
    std::string raw;double confidence=0;
    for(std::size_t i=0;i<model_.config.max_generate;++i){
        auto token=greedy_token();double denom=0;
        for(std::size_t id=0;id<logits_.size();++id){
            if(tok.has_bos()&&id==tok.bos_id())continue;
            if(tok.has_eos()&&id==tok.response_id())continue;
            denom+=std::exp(double(logits_[id]-logits_[token]));
        }
        confidence=1/denom;
        if(tok.has_eos()&&token==tok.eos_id())break;
        raw+=tok.piece(token);
        if(!tok.has_eos()&&raw.find('\n')!=std::string::npos&&i>8)break;
        if(i+1<model_.config.max_generate)step(token);
    }
    return {display_utf8(raw),RouteKind::Neural,true,1,confidence};
}
}
