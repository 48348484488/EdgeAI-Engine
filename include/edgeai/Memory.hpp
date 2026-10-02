#pragma once
#include <cstddef>
#include <string>
#include <vector>
namespace edgeai {
class LocalMemory {
public:
    explicit LocalMemory(std::string path = "edgeai_memory.txt");
    void add(const std::string& text);
    std::vector<std::string> search(const std::string& query, std::size_t limit = 5) const;
    std::size_t size() const { return items_.size(); }
private:
    std::string path_;
    std::vector<std::string> items_;
    void load();
};
}
