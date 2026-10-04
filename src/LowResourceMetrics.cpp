#include "edgeai/LowResourceMetrics.hpp"
#include "edgeai/AtomicFile.hpp"
#include <filesystem>
#include <fstream>
#include <stdexcept>

namespace edgeai {
void write_metrics_json(const std::string& path, const LowResourceMetrics& m) {
    if (path.empty()) return;
    const auto temporary = path + ".tmp";
    std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot write metrics");
    out << "{\n"
        << "  \"schema\": \"edgeai.low-resource.metrics.v1\",\n"
        << "  \"platform\": \"" << m.platform << "\",\n"
        << "  \"startup_ms\": " << m.startup_ms << ",\n"
        << "  \"peak_rss_bytes\": " << m.peak_rss_bytes << ",\n"
        << "  \"model_file_bytes\": " << m.model_file_bytes << ",\n"
        << "  \"model_weight_bytes\": " << m.model_weight_bytes << ",\n"
        << "  \"state_payload_bytes\": " << m.state_payload_bytes << ",\n"
        << "  \"numeric_working_bytes\": " << m.numeric_working_bytes << ",\n"
        << "  \"memory_store_bytes\": " << m.memory_store_bytes << ",\n"
        << "  \"threads\": " << m.threads << ",\n"
        << "  \"requests\": " << m.requests << "\n}\n";
    out.close();
    if (!out) throw std::runtime_error("cannot flush metrics");
    atomic_replace(temporary, path);
}
}
