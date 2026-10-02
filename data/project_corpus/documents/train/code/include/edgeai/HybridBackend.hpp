#pragma once
#include "Backend.hpp"
#include "HybridModel.hpp"
#include "HybridMemory.hpp"
#include <cstdint>
namespace edgeai {
class HybridBackend final:public IModelBackend{
public:
    explicit HybridBackend(HybridModel model,Kernel kernel=Kernel::Auto);
    explicit HybridBackend(const std::string& path,Kernel kernel=Kernel::Auto);
    std::string name()const override{return "edge-hybrid-delta-local-v0.3";}
    bool available()const override{return model_.valid();}
    Response infer(const std::string& prompt,const Budget& budget)override;
    // step updates sequence memory only; loops are readout depth, not extra tokens.
    const std::vector<float>& step(std::uint8_t token);
    void reset();
    const HybridModel& model()const{return model_;}
    std::size_t tokens_seen()const{return tokens_seen_;}
    std::size_t numeric_working_bytes()const;
private:
    HybridModel model_;Kernel kernel_;DeltaMemory delta_;LocalAttention local_;KernelWorkspace workspace_;
    std::vector<float> emb_,norm_,q_,k_,v_,long_,near_,mix_,proj_,h_,up_,down_,logits_,gates_;
    std::size_t tokens_seen_=0;
};
BackendPtr load_backend(const std::string& path);
}
