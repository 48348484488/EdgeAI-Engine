#pragma once
#include "MixedMatrix.hpp"
#include <cstdint>
#include <string>
#include <vector>
namespace edgeai {
struct HybridConfig {
    std::uint32_t dim=32,hidden=64,key_dim=16,window=16,loops=1,max_generate=96;
    float decay_logit=4.0f,write_logit=1.0f,mix_logit=0.0f;
};
class HybridModel {
public:
    HybridConfig config;
    std::uint32_t source_format_version=4;
    std::vector<float> embedding;
    MixedMatrix query,key,value,project,up,down;
    DenseMatrix gates;
    MixedMatrix output;
    bool valid()const;
    std::size_t weight_bytes()const;
    std::size_t parameter_count()const;
    std::size_t state_payload_bytes()const;
    void save(const std::string& path)const;
    static HybridModel load(const std::string& path);
};
HybridModel make_hybrid_demo(std::uint32_t dim=32,std::uint32_t key_dim=16,std::uint32_t window=16);
bool is_hybrid_file(const std::string& path);
}
