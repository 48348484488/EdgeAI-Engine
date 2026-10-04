#pragma once
#include "Backend.hpp"
#include "BoundedMemory.hpp"
#include "LowResourceLimits.hpp"
#include "TransformerBackend.hpp"
#include <memory>
#include <string>

namespace edgeai {
struct LowResourceConfig {
    LowResourceLimits limits;
    std::string model_path;
    std::string memory_path;
    unsigned threads = 1u;
};

class LowResourceEngine {
public:
    explicit LowResourceEngine(LowResourceConfig config);
    Response ask(const std::string& prompt);
    const LowResourceLimits& limits() const noexcept { return config_.limits; }
    std::size_t model_file_bytes() const noexcept { return model_file_bytes_; }
    std::size_t model_weight_bytes() const noexcept { return model_weight_bytes_; }
    std::size_t state_payload_bytes() const noexcept { return state_payload_bytes_; }
    std::size_t numeric_working_bytes() const noexcept { return numeric_working_bytes_; }
    std::size_t memory_store_bytes() const noexcept { return memory_ ? memory_->bytes() : 0; }
private:
    LowResourceConfig config_;
    std::shared_ptr<TransformerBackend> backend_;
    std::unique_ptr<BoundedMemory> memory_;
    std::size_t model_file_bytes_ = 0;
    std::size_t model_weight_bytes_ = 0;
    std::size_t state_payload_bytes_ = 0;
    std::size_t numeric_working_bytes_ = 0;
};
}
