#include "edgeai/LowResourceEngine.hpp"
#include "edgeai/TransformerModel.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace edgeai;
#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (false)
template<class F> void rejected(F f) { bool caught=false; try { f(); } catch (...) { caught=true; } CHECK(caught); }

int main() {
    const auto temp = std::filesystem::temp_directory_path();
    const auto model = temp / "edgeai-low-resource-test.edge";
    const auto memory = temp / "edgeai-low-resource-memory.txt";
    make_transformer_demo(8, 12, 4).save(model.string());
    std::error_code ec;
    std::filesystem::remove(memory, ec);

    LowResourceConfig config;
    config.model_path = model.string();
    config.memory_path = memory.string();
    config.threads = 1;
    LowResourceEngine engine(config);
    auto answer = engine.ask("2+2");
    CHECK(answer.route == RouteKind::Calculator && answer.text == "4" && !answer.neural_used);
    answer = engine.ask("uppercase: weak pc");
    CHECK(answer.text == "WEAK PC" && !answer.neural_used);
    answer = engine.ask("/code router");
    CHECK(answer.route == RouteKind::CodeSearch && !answer.neural_used);
    CHECK(answer.text.find("unavailable") != std::string::npos);
    answer = engine.ask("explain entropy briefly");
    CHECK(answer.route == RouteKind::Neural && answer.neural_used);
    CHECK(engine.model_weight_bytes() > 0);
    CHECK(engine.state_payload_bytes() > 0);
    CHECK(engine.numeric_working_bytes() > 0);
    rejected([&] { engine.ask(std::string(4097, 'x')); });

    auto too_many = config; too_many.threads = 3;
    rejected([&] { LowResourceEngine invalid(too_many); });
    auto missing = config; missing.model_path += ".missing";
    rejected([&] { LowResourceEngine invalid(missing); });
    const auto corrupt = temp / "edgeai-low-resource-corrupt.edge";
    { std::ofstream out(corrupt, std::ios::binary); out << "bad"; }
    auto bad = config; bad.model_path = corrupt.string();
    rejected([&] { LowResourceEngine invalid(bad); });
    const auto huge_state = temp / "edgeai-low-resource-huge-state.edge";
    make_transformer_demo(256, 4, 4096, 8).save(huge_state.string());
    bad.model_path = huge_state.string();
    rejected([&] { LowResourceEngine invalid(bad); });
    const auto oversized = temp / "edgeai-low-resource-oversized.edge";
    { std::ofstream out(oversized, std::ios::binary); out.seekp(17 * 1024 * 1024); out.put('\0'); }
    bad.model_path = oversized.string();
    rejected([&] { LowResourceEngine invalid(bad); });

    std::filesystem::remove(model, ec);
    std::filesystem::remove(memory, ec);
    std::filesystem::remove(corrupt, ec);
    std::filesystem::remove(oversized, ec);
    std::filesystem::remove(huge_state, ec);
    std::cout << "low-resource engine checks passed\n";
}
