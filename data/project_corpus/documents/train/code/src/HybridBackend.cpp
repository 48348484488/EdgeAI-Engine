#include "edgeai/HybridBackend.hpp"
#include "edgeai/TernaryBackend.hpp"
#include <algorithm>
#include <cmath>
#include <memory>
#include <numeric>
#include <stdexcept>
namespace edgeai { namespace {
HybridModel checked_model(HybridModel m){if(!m.valid())throw std::invalid_argument("invalid hybrid model");return m;}
float sigmoid(float x){return x>=0?1/(1+std::exp(-x)):std::exp(x)/(1+std::exp(x));}
void norm(const std::vector<float>& x,std::vector<float>& y){float m=std::accumulate(x.begin(),x.end(),0.f)/x.size(),v=0;for(float z:x)v+=(z-m)*(z-m);float inv=1/std::sqrt(v/x.size()+1e-5f);for(std::size_t j=0;j<x.size();++j)y[j]=(x[j]-m)*inv;}
void unit(std::vector<float>& x){float sum=0;for(float z:x)sum+=z*z;float n=std::max(1e-6f,std::sqrt(sum));for(float& z:x)z/=n;}
// Terminal rendering is separate from model feedback. Invalid UTF-8 is replaced.
std::string display_text(const std::string& raw){std::string out;for(std::size_t i=0;i<raw.size();){unsigned char c=raw[i];if(c<128){out+=c==9||c==10||(c>=32&&c!=127)?char(c):' ';++i;continue;}std::size_t n=c>=0xc2&&c<=0xdf?2:c>=0xe0&&c<=0xef?3:c>=0xf0&&c<=0xf4?4:0;bool ok=n&&i+n<=raw.size();for(std::size_t j=1;ok&&j<n;++j)ok=(static_cast<unsigned char>(raw[i+j])&0xc0)==0x80;
 if(ok&&n>=3){auto b=static_cast<unsigned char>(raw[i+1]);ok=!(c==0xe0&&b<0xa0)&&!(c==0xed&&b>=0xa0)&&!(c==0xf0&&b<0x90)&&!(c==0xf4&&b>=0x90);}if(ok){out.append(raw,i,n);i+=n;}else{out+="\xef\xbf\xbd";++i;}}return out;}
}
HybridBackend::HybridBackend(HybridModel m,Kernel kernel):model_(checked_model(std::move(m))),kernel_(kernel),delta_(model_.config.key_dim,model_.config.dim),local_(model_.config.key_dim,model_.config.dim,model_.config.window),emb_(model_.config.dim),norm_(model_.config.dim),q_(model_.config.key_dim),k_(model_.config.key_dim),v_(model_.config.dim),long_(model_.config.dim),near_(model_.config.dim),mix_(model_.config.dim),proj_(model_.config.dim),h_(model_.config.dim),up_(model_.config.hidden),down_(model_.config.dim),logits_(256),gates_(3){if(!model_.valid())throw std::invalid_argument("invalid HybridModel");select_kernel(model_.config.dim,model_.config.dim,kernel_);}
HybridBackend::HybridBackend(const std::string& path,Kernel k):HybridBackend(HybridModel::load(path),k){}
void HybridBackend::reset(){delta_.reset();local_.reset();tokens_seen_=0;std::fill(logits_.begin(),logits_.end(),0);}
const std::vector<float>& HybridBackend::step(std::uint8_t token){
 const auto& c=model_.config;std::copy_n(model_.embedding.data()+std::size_t(token)*c.dim,c.dim,emb_.data());norm(emb_,norm_);
 auto mv=[&](const MixedMatrix& a,const std::vector<float>& x,std::vector<float>& y){a.matvec_into(x.data(),x.size(),y.data(),y.size(),kernel_,&workspace_);};
 mv(model_.query,norm_,q_);mv(model_.key,norm_,k_);mv(model_.value,norm_,v_);unit(q_);unit(k_);
 model_.gates.matvec_into(norm_.data(),norm_.size(),gates_.data(),3,kernel_==Kernel::Lookup?Kernel::Scalar:kernel_);
 delta_.update(k_,v_,sigmoid(c.decay_logit+gates_[0]),sigmoid(c.write_logit+gates_[1]));local_.push(k_,v_);delta_.read(q_,long_);local_.read(q_,near_);
 float gate=sigmoid(c.mix_logit+gates_[2]);for(std::size_t j=0;j<c.dim;++j)mix_[j]=gate*long_[j]+(1-gate)*near_[j];mv(model_.project,mix_,proj_);for(std::size_t j=0;j<c.dim;++j)h_[j]=emb_[j]+proj_[j];
 for(std::size_t t=0;t<c.loops;++t){norm(h_,norm_);mv(model_.up,norm_,up_);for(float& z:up_)z=z*sigmoid(z);mv(model_.down,up_,down_);for(std::size_t j=0;j<c.dim;++j)h_[j]+=.5f*down_[j];}
 norm(h_,norm_);model_.output.matvec_into(norm_.data(),norm_.size(),logits_.data(),logits_.size(),kernel_==Kernel::Lookup?Kernel::Scalar:kernel_);++tokens_seen_;return logits_;
}
std::size_t HybridBackend::numeric_working_bytes()const{auto c=model_.config;return model_.state_payload_bytes()+4ull*(10*c.dim+2*c.key_dim+c.hidden+256+c.window+3)+workspace_.bytes();}
Response HybridBackend::infer(const std::string& prompt,const Budget& b){
 if(!b.max_context_chars||b.max_loops<model_.config.loops)throw std::invalid_argument("budget cannot execute this model's trained depth");
 reset();std::size_t begin=prompt.size()>b.max_context_chars?prompt.size()-b.max_context_chars:0;
 if(prompt.empty())step('\n');else for(std::size_t i=begin;i<prompt.size();++i)step(static_cast<std::uint8_t>(static_cast<unsigned char>(prompt[i])));
 std::string raw;double conf=0;std::size_t depth=0;
 for(std::size_t t=0;t<model_.config.max_generate;++t){auto best=std::max_element(logits_.begin(),logits_.end());float mx=*best;double total=0;for(float z:logits_)total+=std::exp(double(z-mx));conf=1/total;auto token=static_cast<std::uint8_t>(best-logits_.begin());raw+=static_cast<char>(token);depth+=model_.config.loops;if(token=='\n'&&t>8)break;if(t+1<model_.config.max_generate)step(token);}
 return {display_text(raw),RouteKind::Neural,true,depth,conf};
}
BackendPtr load_backend(const std::string& path){if(is_hybrid_file(path))return std::make_shared<HybridBackend>(path);return std::make_shared<TernaryBackend>(path);}
}
