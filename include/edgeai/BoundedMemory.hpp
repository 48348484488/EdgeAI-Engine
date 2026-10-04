#pragma once
#include <cstddef>
#include <string>
#include <vector>

namespace edgeai {
enum class MemoryAddResult { Added, EvictedOldest, RejectedTooLarge };

class BoundedMemory {
public:
    BoundedMemory(std::string path, std::size_t max_entries, std::size_t max_bytes);
    MemoryAddResult add(const std::string& text);
    std::vector<std::string> search(const std::string& query, std::size_t limit) const;
    std::size_t size() const noexcept { return items_.size(); }
    std::size_t bytes() const noexcept { return bytes_; }
private:
    void load();
    void persist() const;
    std::string path_;
    std::size_t max_entries_;
    std::size_t max_bytes_;
    std::size_t bytes_ = 0;
    std::vector<std::string> items_;
};
}
