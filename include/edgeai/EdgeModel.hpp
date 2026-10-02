#pragma once
#include "Ternary.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace edgeai {

struct EdgeModelConfig {
    std::uint32_t vocab_size = 256;
    std::uint32_t dim = 64;
    std::uint32_t hidden_dim = 128;
    std::uint32_t default_loops = 2;
    std::uint32_t max_generate = 96;
    float early_exit_confidence = 0.92f;
};

class EdgeModel {
public:
    EdgeModelConfig config;
    std::vector<float> embedding; // vocab_size x dim, FP32 in v0.2
    TernaryMatrix wx;             // dim x dim
    TernaryMatrix wh;             // dim x dim
    TernaryMatrix reason_up;      // hidden_dim x dim
    TernaryMatrix reason_down;    // dim x hidden_dim
    DenseMatrix output;           // vocab_size x dim, FP32 in v0.2

    bool valid() const;
    std::size_t parameter_count() const;
    std::size_t resident_weight_bytes() const;
    std::size_t fp32_equivalent_bytes() const;
    double compression_ratio_vs_fp32() const;

    void save(const std::string& path) const;
    static EdgeModel load(const std::string& path);
};

EdgeModel make_demo_edge_model(std::uint32_t dim = 32, std::uint32_t hidden_dim = 64);

} // namespace edgeai
