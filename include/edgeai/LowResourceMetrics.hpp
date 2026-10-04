#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace edgeai {
struct LowResourceMetrics {
    std::string platform;
    std::uint64_t startup_ms = 0;
    std::size_t peak_rss_bytes = 0;
    std::size_t model_file_bytes = 0;
    std::size_t model_weight_bytes = 0;
    std::size_t state_payload_bytes = 0;
    std::size_t numeric_working_bytes = 0;
    std::size_t memory_store_bytes = 0;
    unsigned threads = 1;
    std::size_t requests = 0;
};
void write_metrics_json(const std::string& path, const LowResourceMetrics& metrics);
}
