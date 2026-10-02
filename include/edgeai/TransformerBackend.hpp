#pragma once
#include "Backend.hpp"
#include "TransformerModel.hpp"
namespace edgeai {
class TransformerBackend final:public IModelBackend {
public:
    explicit TransformerBackend(TransformerModel model,Kernel kernel=Kernel::Auto);
    explicit TransformerBackend(const std::string&path,Kernel kernel=Kernel::Auto);
    std::string name()const override{return "edge-transformer-rope-v0.12";}
    bool available()const override{return model_.valid();}
    Response infer(const std::string&prompt,const Budget&budget)override;
    const std::vector<float>& step(std::uint32_t token);
    void reset();
    std::uint32_t greedy_token()const;
    const TransformerModel& model()const{return model_;}
    std::size_t tokens_seen()const{return tokens_seen_;}
    std::size_t cache_size()const;
    std::vector<std::size_t> block_cache_sizes()const;
    std::size_t numeric_working_bytes()const;
private:
    struct BlockRuntime {
        std::vector<float> norm,q,k,v,near,projected,h,up,down,keys,values,scores;
        std::size_t next=0,used=0;
        BlockRuntime(std::size_t dim,std::size_t hidden,std::size_t window);
    };
    TransformerModel model_;Kernel kernel_;KernelWorkspace workspace_;
    std::vector<float> emb_,final_norm_,logits_,freq_;
    std::vector<BlockRuntime> runtime_;
    std::size_t tokens_seen_=0;
};
}
