#pragma once
#include "MixedMatrix.hpp"
#include "ByteBPE.hpp"
#include <cstdint>
#include <string>
#include <vector>
namespace edgeai {
struct TransformerConfig {
    std::uint32_t dim=64,hidden=96,window=64,max_generate=128;
    float rope_base=10000.f;
};
struct TransformerModel {
    TransformerConfig config;
    ByteBPE tokenizer;
    std::vector<float> embedding;
    MixedMatrix query,key,value,project,up,down,output;
    bool valid()const;
    std::size_t weight_bytes()const;
    std::size_t parameter_count()const;
    std::size_t state_payload_bytes()const;
    void save(const std::string& path)const;
    static TransformerModel load(const std::string& path);
};
bool is_transformer_file(const std::string& path);
TransformerModel make_transformer_demo(std::uint32_t dim=16,std::uint32_t hidden=24,std::uint32_t window=8);
}
