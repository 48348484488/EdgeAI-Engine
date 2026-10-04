#include "edgeai/BoundedMemory.hpp"
#include "edgeai/LowResourceLimits.hpp"
#include <filesystem>
#include <fstream>
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace edgeai;
#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (false)

int main() {
    const LowResourceLimits limits;
    CHECK(limits.max_rss_bytes == 64u * 1024u * 1024u);
    CHECK(limits.max_model_bytes == 16u * 1024u * 1024u);
    CHECK(limits.max_threads == 2u);

    const auto path = std::filesystem::temp_directory_path() / ("edgeai-bounded-memory-" + std::to_string(reinterpret_cast<std::uintptr_t>(&limits)) + ".txt");
    std::error_code ec;
    std::filesystem::remove(path, ec);
    {
        std::ofstream out(path, std::ios::binary);
        out << std::string(1024 * 1024, 'x') << "\nnewest\n";
    }
    {
        BoundedMemory bounded_load(path.string(), 2, 12);
        CHECK(bounded_load.size() == 1);
        CHECK(bounded_load.search("newest", 1).size() == 1);
        CHECK(std::filesystem::file_size(path) <= 13);
    }
    std::filesystem::remove(path, ec);
    {
        BoundedMemory memory(path.string(), 2, 12);
        CHECK(memory.add("alpha") == MemoryAddResult::Added);
        CHECK(memory.add("beta") == MemoryAddResult::Added);
        CHECK(memory.add("gamma") == MemoryAddResult::EvictedOldest);
        CHECK(memory.size() == 2);
        CHECK(memory.bytes() == 9);
        const auto hits = memory.search("gamma", 1);
        CHECK(hits.size() == 1 && hits[0] == "gamma");
        CHECK(memory.add("this entry is too large") == MemoryAddResult::RejectedTooLarge);
        CHECK(memory.size() == 2);
    }
    {
        BoundedMemory reloaded(path.string(), 2, 12);
        CHECK(reloaded.size() == 2);
        CHECK(reloaded.search("beta", 2).front() == "beta");
    }
    std::filesystem::remove(path, ec);
    std::cout << "bounded memory checks passed\n";
}
