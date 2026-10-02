#pragma once
#include "Backend.hpp"
#include "EdgeModel.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace edgeai {

class TernaryBackend final : public IModelBackend {
public:
    explicit TernaryBackend(const std::string& model_path,Kernel kernel=Kernel::Auto);
    explicit TernaryBackend(EdgeModel model,Kernel kernel=Kernel::Auto);
    std::string name() const override { return "edge-ternary-2bit-v0.2"; }
    bool available() const override { return model_.valid(); }
    Response infer(const std::string& prompt, const Budget& budget) override;

    std::vector<float> forward_token(std::uint8_t token,std::vector<float>& recurrent_state) const;
    const EdgeModel& model() const { return model_; }
    std::size_t last_generated_tokens() const { return last_generated_tokens_; }

private:
    EdgeModel model_;
    Kernel kernel_;
    std::size_t last_generated_tokens_ = 0;

    void consume_token(std::uint8_t token, std::vector<float>& state) const;
    std::size_t reason(std::vector<float>& state, const Budget& budget, std::vector<float>& logits) const;
    void logits_for(const std::vector<float>& state, std::vector<float>& logits) const;
};

} // namespace edgeai
