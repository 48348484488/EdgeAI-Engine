#include "edgeai/LowResourceEngine.hpp"
#include "edgeai/Calculator.hpp"
#include "edgeai/Router.hpp"
#include "edgeai/TextTools.hpp"
#include "edgeai/TransformerBackend.hpp"
#include <cctype>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace edgeai { namespace {
std::uint32_t read_u32(std::ifstream& in) {
    unsigned char b[4]{}; in.read(reinterpret_cast<char*>(b), 4);
    if (!in) throw std::invalid_argument("truncated model header");
    return std::uint32_t(b[0]) | (std::uint32_t(b[1]) << 8) | (std::uint32_t(b[2]) << 16) | (std::uint32_t(b[3]) << 24);
}
std::shared_ptr<TransformerBackend> load_checked_backend(const LowResourceConfig& config, std::size_t& bytes,
        std::size_t& weights, std::size_t& state, std::size_t& working) {
    if (!config.threads || config.threads > config.limits.max_threads)
        throw std::invalid_argument("threads must be between 1 and the configured maximum");
    const std::filesystem::path path(config.model_path);
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec))
        throw std::invalid_argument("model is missing or is not a regular file");
    const auto raw_size = std::filesystem::file_size(path, ec);
    if (ec || raw_size > config.limits.max_model_bytes)
        throw std::invalid_argument("model exceeds the low-resource byte limit");
    bytes = static_cast<std::size_t>(raw_size);
    if (!is_transformer_file(path.string()))
        throw std::invalid_argument("model is not a supported transformer file");
    std::ifstream header(path, std::ios::binary);
    char magic[8]{}; header.read(magic, 8);
    const auto version = read_u32(header), dim = read_u32(header), hidden = read_u32(header), window = read_u32(header);
    (void)hidden; (void)read_u32(header); (void)read_u32(header);
    const auto blocks = version == 8 ? read_u32(header) : 1u;
    if (!dim || !window || !blocks) throw std::invalid_argument("invalid model dimensions");
    if (dim > SIZE_MAX / 8u / window / blocks) throw std::invalid_argument("model state size overflow");
    state = std::size_t(8u) * dim * window * blocks;
    constexpr std::size_t process_reserve = 8u * 1024u * 1024u;
    if (bytes > config.limits.max_rss_bytes || state > config.limits.max_rss_bytes - bytes ||
        bytes + state > config.limits.max_rss_bytes - process_reserve)
        throw std::invalid_argument("model declared working set exceeds the RSS budget");
    auto model = TransformerModel::load(path.string());
    weights = model.weight_bytes();
    auto backend = std::make_shared<TransformerBackend>(std::move(model), Kernel::Auto);
    working = backend->numeric_working_bytes();
    if (weights + state + working > config.limits.max_rss_bytes - process_reserve)
        throw std::invalid_argument("model runtime working set exceeds the RSS budget");
    return backend;
}
}

LowResourceEngine::LowResourceEngine(LowResourceConfig config)
    : config_(std::move(config)) {
    backend_ = load_checked_backend(config_, model_file_bytes_, model_weight_bytes_, state_payload_bytes_, numeric_working_bytes_);
    memory_ = std::make_unique<BoundedMemory>(config_.memory_path, config_.limits.max_memory_entries, config_.limits.max_memory_bytes);
}

Response LowResourceEngine::ask(const std::string& prompt) {
    if (prompt.size() > config_.limits.max_prompt_bytes)
        throw std::invalid_argument("prompt exceeds the low-resource byte limit");
    const auto selected = route(prompt);
    if (selected.kind == RouteKind::CodeSearch)
        return {"Code search is unavailable in the low-resource runtime.", selected.kind, false, 0, 1.0};
    if (selected.kind == RouteKind::Calculator) {
        try { return {format_number(calculate(selected.payload)), selected.kind, false, 0, 1.0}; }
        catch (const std::exception& error) { return {std::string("Calculation error: ") + error.what(), selected.kind, false, 0, 0.0}; }
    }
    if (selected.kind == RouteKind::TextCopy || selected.kind == RouteKind::SymbolicExpression)
        return {selected.payload, selected.kind, false, 0, 1.0};
    if (selected.kind == RouteKind::TextUppercase) {
        auto output = selected.payload;
        for (char& c : output) if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
        return {output, selected.kind, false, 0, 1.0};
    }
    if (selected.kind == RouteKind::TextReverse)
        return {reverse_utf8_codepoints(selected.payload), selected.kind, false, 0, 1.0};
    if (selected.kind == RouteKind::MemoryAdd) {
        const auto result = memory_->add(selected.payload);
        const char* text = result == MemoryAddResult::RejectedTooLarge ? "Memory entry rejected: limit exceeded." : "Memory saved.";
        return {text, selected.kind, false, 0, result == MemoryAddResult::RejectedTooLarge ? 0.0 : 1.0};
    }
    if (selected.kind == RouteKind::MemorySearch) {
        const auto hits = memory_->search(selected.payload, 8);
        if (hits.empty()) return {"Nothing found.", selected.kind, false, 0, 1.0};
        std::ostringstream out;
        for (std::size_t i = 0; i < hits.size(); ++i) { if (i) out << '\n'; out << hits[i]; }
        return {out.str(), selected.kind, false, 0, 1.0};
    }
    auto output = backend_->infer(selected.payload, Budget{1, 4096, 8, config_.threads});
    output.route = RouteKind::Neural;
    output.neural_used = true;
    return output;
}
}
