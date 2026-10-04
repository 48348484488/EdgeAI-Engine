#include "edgeai/BoundedMemory.hpp"
#include "edgeai/AtomicFile.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <stdexcept>

namespace edgeai { namespace {
std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}
}

BoundedMemory::BoundedMemory(std::string path, std::size_t max_entries, std::size_t max_bytes)
    : path_(std::move(path)), max_entries_(max_entries), max_bytes_(max_bytes) {
    if (!max_entries_ || !max_bytes_) throw std::invalid_argument("memory limits must be positive");
    load();
}

void BoundedMemory::load() {
    if (path_.empty()) return;
    std::ifstream in(path_, std::ios::binary);
    std::string line;
    line.reserve(std::min<std::size_t>(max_bytes_, 4096));
    bool overflow = false, compact = false;
    char c = 0;
    auto accept = [&] {
        if (overflow || line.empty()) { compact = compact || overflow; line.clear(); overflow = false; return; }
        while (!items_.empty() && (items_.size() >= max_entries_ || bytes_ + line.size() > max_bytes_)) {
            bytes_ -= items_.front().size();
            items_.erase(items_.begin());
            compact = true;
        }
        if (bytes_ + line.size() <= max_bytes_) {
            bytes_ += line.size();
            items_.push_back(line);
        }
        line.clear();
    };
    while (in.get(c)) {
        if (c == '\n') { accept(); continue; }
        if (c == '\r') continue;
        if (!overflow) {
            if (line.size() == max_bytes_) { overflow = true; line.clear(); compact = true; }
            else line.push_back(c);
        }
    }
    if (overflow || !line.empty()) accept();
    in.close();
    if (compact) persist();
}

MemoryAddResult BoundedMemory::add(const std::string& text) {
    if (text.empty() || text.size() > max_bytes_) return MemoryAddResult::RejectedTooLarge;
    bool evicted = false;
    while (!items_.empty() && (items_.size() >= max_entries_ || bytes_ + text.size() > max_bytes_)) {
        bytes_ -= items_.front().size();
        items_.erase(items_.begin());
        evicted = true;
    }
    items_.push_back(text);
    bytes_ += text.size();
    persist();
    return evicted ? MemoryAddResult::EvictedOldest : MemoryAddResult::Added;
}

std::vector<std::string> BoundedMemory::search(const std::string& query, std::size_t limit) const {
    std::vector<std::string> hits;
    if (!limit) return hits;
    const auto needle = lower(query.substr(0, max_bytes_));
    hits.reserve(std::min(limit, items_.size()));
    for (const auto& item : items_) {
        if (lower(item).find(needle) != std::string::npos) {
            hits.push_back(item);
            if (hits.size() == limit) break;
        }
    }
    return hits;
}

void BoundedMemory::persist() const {
    if (path_.empty()) return;
    const std::filesystem::path target(path_);
    const auto temporary = target.string() + ".tmp";
    {
        std::ofstream out(temporary, std::ios::binary | std::ios::trunc);
        if (!out) throw std::runtime_error("cannot write bounded memory");
        for (const auto& item : items_) out << item << '\n';
        if (!out) throw std::runtime_error("cannot flush bounded memory");
    }
    atomic_replace(temporary, target);
}
}
