#pragma once
#include <cstddef>
#include <cstdint>

namespace edgeai {
struct LowResourceLimits {
    std::size_t max_rss_bytes = 64u * 1024u * 1024u;
    std::size_t max_model_bytes = 16u * 1024u * 1024u;
    std::size_t max_memory_entries = 64u;
    std::size_t max_memory_bytes = 64u * 1024u;
    std::size_t max_prompt_bytes = 4096u;
    unsigned max_threads = 2u;
    std::uint64_t max_startup_ms = 2000u;
};
}
