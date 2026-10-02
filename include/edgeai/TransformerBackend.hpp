#pragma once
#include "Backend.hpp"
#include "TransformerModel.hpp"
namespace edgeai {
class TransformerBackend final:public IModelBackend {
public:
    explicit TransformerBackend(TransformerModel model,Kernel kernel=Kernel::Auto);
    explicit TransformerBackend(const std::string&path,Kernel kernel=Kernel::Auto);
    std::string name()const override{return "edge-transformer-rope-v0.7";}
    bool available()const override{return model_.valid();}
    Response infer(const std::string&prompt,const Budget&budget)override;
    const std::vector<float>& step(std::uint32_t token);
    void reset();
    std::uint32_t greedy_token()const;
    const TransformerModel& model()const{return model_;}
    std::size_t tokens_seen()const{return tokens_seen_;}
    std::size_t cache_size()const{return used_;}
    std::size_t numeric_working_bytes()const;
private:
    TransformerModel model_;Kernel kernel_;KernelWorkspace workspace_;
    std::vector<float> emb_,norm_,q_,k_,v_,near_,projected_,h_,up_,down_,logits_,keys_,values_,scores_,freq_;
    std::size_t tokens_seen_=0,next_=0,used_=0;
};
}
