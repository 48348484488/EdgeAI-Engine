#include "edgeai/TransformerBackend.hpp"
#include "edgeai/Text.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
namespace edgeai { namespace {
TransformerModel checked(TransformerModel m){if(!m.valid())throw std::invalid_argument("invalid Transformer model");return m;}
void normalize(const std::vector<float>&x,std::vector<float>&y){float mean=std::accumulate(x.begin(),x.end(),0.f)/x.size(),var=0;for(float z:x)var+=(z-mean)*(z-mean);float inv=1/std::sqrt(var/x.size()+1e-5f);for(std::size_t j=0;j<x.size();++j)y[j]=(x[j]-mean)*inv;}
float sigmoid(float x){return x>=0?1/(1+std::exp(-x)):std::exp(x)/(1+std::exp(x));}
}
TransformerBackend::BlockRuntime::BlockRuntime(std::size_t dim,std::size_t hidden,std::size_t window):
    norm(dim),q(dim),k(dim),v(dim),near(dim),projected(dim),h(dim),up(hidden),down(dim),
    keys(window*dim),values(window*dim),scores(window){}
TransformerBackend::TransformerBackend(TransformerModel m,Kernel k):
    model_(checked(std::move(m))),kernel_(k),emb_(model_.config.dim),final_norm_(model_.config.dim),
    logits_(model_.tokenizer.vocab_size()),freq_(model_.config.dim/2){
    select_kernel(model_.config.dim,model_.config.dim,kernel_);
    runtime_.reserve(model_.config.blocks);
    for(std::uint32_t i=0;i<model_.config.blocks;++i)
        runtime_.emplace_back(model_.config.dim,model_.config.hidden,model_.config.window);
    for(std::size_t j=0;j<freq_.size();++j)
        freq_[j]=static_cast<float>(std::pow(double(model_.config.rope_base),-2.*j/model_.config.dim));
}
TransformerBackend::TransformerBackend(const std::string&p,Kernel k):TransformerBackend(TransformerModel::load(p),k){}
void TransformerBackend::reset(){
    tokens_seen_=0;std::fill(logits_.begin(),logits_.end(),0);
    for(auto&r:runtime_){r.next=0;r.used=0;}
}
std::size_t TransformerBackend::cache_size()const{
    std::size_t value=0;for(const auto&r:runtime_)value=std::max(value,r.used);return value;
}
std::vector<std::size_t> TransformerBackend::block_cache_sizes()const{
    std::vector<std::size_t> out;out.reserve(runtime_.size());for(const auto&r:runtime_)out.push_back(r.used);return out;
}
const std::vector<float>&TransformerBackend::step(std::uint32_t token){
    if(token>=model_.tokenizer.vocab_size())throw std::out_of_range("token out of model vocabulary");
    const auto&c=model_.config;
    if(tokens_seen_>=16777216)throw std::runtime_error("reset required before RoPE position exceeds FP32 exact-integer range");
    auto mv=[&](const MixedMatrix&m,const std::vector<float>&x,std::vector<float>&y){m.matvec_into(x.data(),x.size(),y.data(),y.size(),kernel_,&workspace_);};
    std::copy_n(model_.embedding.data()+std::size_t(token)*c.dim,c.dim,emb_.data());
    const std::vector<float>*input=&emb_;
    for(std::size_t bi=0;bi<runtime_.size();++bi){
        auto&r=runtime_[bi];const auto&block=model_.blocks_data[bi];
        normalize(*input,r.norm);
        mv(block.query,r.norm,r.q);mv(block.key,r.norm,r.k);mv(block.value,r.norm,r.v);
        for(std::size_t j=0;j<freq_.size();++j){
            float angle=static_cast<float>(tokens_seen_)*freq_[j],cs=std::cos(angle),sn=std::sin(angle);
            for(auto*x:{&r.q,&r.k}){float a=(*x)[2*j],b=(*x)[2*j+1];(*x)[2*j]=a*cs-b*sn;(*x)[2*j+1]=a*sn+b*cs;}
        }
        std::copy(r.k.begin(),r.k.end(),r.keys.begin()+r.next*c.dim);
        std::copy(r.v.begin(),r.v.end(),r.values.begin()+r.next*c.dim);
        r.next=(r.next+1)%c.window;r.used=std::min(r.used+1,std::size_t(c.window));
        float mx=-std::numeric_limits<float>::infinity();const float scale=1/std::sqrt(float(c.dim));
        for(std::size_t t=0;t<r.used;++t){
            auto slot=(r.next+c.window-r.used+t)%c.window;float z=0;
            for(std::size_t j=0;j<c.dim;++j)z+=r.q[j]*r.keys[slot*c.dim+j];
            r.scores[t]=z*scale;mx=std::max(mx,r.scores[t]);
        }
        float sum=0;for(std::size_t t=0;t<r.used;++t){r.scores[t]=std::exp(r.scores[t]-mx);sum+=r.scores[t];}
        std::fill(r.near.begin(),r.near.end(),0);
        for(std::size_t t=0;t<r.used;++t){
            auto slot=(r.next+c.window-r.used+t)%c.window;float wt=r.scores[t]/sum;
            for(std::size_t j=0;j<c.dim;++j)r.near[j]+=wt*r.values[slot*c.dim+j];
        }
        mv(block.project,r.near,r.projected);
        for(std::size_t j=0;j<c.dim;++j)r.h[j]=(*input)[j]+r.projected[j];
        normalize(r.h,r.norm);mv(block.up,r.norm,r.up);for(auto&z:r.up)z*=sigmoid(z);mv(block.down,r.up,r.down);
        for(std::size_t j=0;j<c.dim;++j)r.h[j]+=.5f*r.down[j];
        input=&r.h;
    }
    normalize(*input,final_norm_);mv(model_.output,final_norm_,logits_);
    for(float z:logits_)if(!std::isfinite(z))throw std::runtime_error("nonfinite Transformer output; invalid numeric range");
    ++tokens_seen_;return logits_;
}
std::size_t TransformerBackend::numeric_working_bytes()const{
    std::size_t n=emb_.size()+final_norm_.size()+logits_.size()+freq_.size();
    for(const auto&r:runtime_)for(const auto*p:{&r.norm,&r.q,&r.k,&r.v,&r.near,&r.projected,&r.h,&r.up,&r.down,&r.keys,&r.values,&r.scores})n+=p->size();
    return n*sizeof(float)+workspace_.bytes();
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
