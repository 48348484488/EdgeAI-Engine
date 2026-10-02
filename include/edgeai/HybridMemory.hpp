#pragma once
#include <cstddef>
#include <vector>
namespace edgeai {
// State is key_dim x value_dim; normalized keys are required for stable updates.
class DeltaMemory {
public:
    DeltaMemory(std::size_t key_dim,std::size_t value_dim);
    void reset();
    void update(const std::vector<float>& key,const std::vector<float>& value,float decay,float strength);
    void read(const std::vector<float>& query,std::vector<float>& out) const;
    std::size_t storage_bytes() const { return state_.size()*sizeof(float); }
private:
    std::size_t kd_,vd_;std::vector<float> state_,prediction_;
};
// Causal sliding-window softmax attention. A full ring overwrites its oldest entry.
class LocalAttention {
public:
    LocalAttention(std::size_t key_dim,std::size_t value_dim,std::size_t window);
    void reset();
    void push(const std::vector<float>& key,const std::vector<float>& value);
    void read(const std::vector<float>& query,std::vector<float>& out);
    std::size_t size() const { return used_; }
    std::size_t storage_bytes() const { return (keys_.size()+values_.size())*sizeof(float); }
private:
    std::size_t kd_,vd_,window_,next_=0,used_=0;
    std::vector<float> keys_,values_,scores_;
};
}
