#pragma once
#include <cstddef>
#include <string>
#include <vector>
namespace edgeai {
struct SearchLimits {
    std::size_t max_files=2000, max_file_bytes=256*1024, max_total_bytes=8*1024*1024;
    std::size_t max_lines=100000, max_depth=20;
};
struct CodeHit {
    std::string path, text;
    std::size_t match_line=0, start_line=0, end_line=0;
    double score=0;
};
struct CodeSearchResult {
    std::vector<CodeHit> hits;
    std::size_t scanned_files=0, scanned_bytes=0, skipped_files=0;
    bool partial=false, neural_used=false;
    std::string method="lexical-source-lines";
};
// Bounded read-only snapshot. Reconstruct after file edits; no on-disk index.
class CodeIndex {
public:
    explicit CodeIndex(const std::string& root, SearchLimits limits={});
    CodeSearchResult search(const std::string& query, std::size_t limit=5,
                            std::size_t context=2) const;
private:
    struct Source {std::string path;std::vector<std::string> lines;};
    std::vector<Source> sources_;
    CodeSearchResult stats_;
};
std::string format_code_result(const CodeSearchResult& result);
std::string code_result_json(const CodeSearchResult& result);
}
