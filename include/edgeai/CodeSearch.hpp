#pragma once
#include <cstddef>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>
namespace edgeai {
struct SearchLimits {
    std::size_t max_files=2000, max_file_bytes=256*1024, max_total_bytes=8*1024*1024;
    std::size_t max_lines=100000, max_depth=20, max_index_entries=500000;
};
struct CodeHit {
    std::string path, text;
    std::size_t match_line=0, start_line=0, end_line=0;
    double score=0;
};
struct CodeSearchResult {
    std::vector<CodeHit> hits;
    std::size_t scanned_files=0, scanned_bytes=0, skipped_files=0;
    std::size_t content_bytes_read=0, reused_files=0, reindexed_files=0;
    std::size_t candidate_lines=0, total_lines=0, index_entries=0, revision=0;
    bool partial=false, neural_used=false;
    std::string method="lexical-source-lines";
};
// Bounded in-memory snapshot. refresh() verifies full contents, not timestamps.
// search() alone reads the current snapshot; Engine/batch refresh before queries.
// No disk index, filesystem watcher, semantic parser, or thread-safety guarantee.
class CodeIndex {
public:
    explicit CodeIndex(const std::string& root, SearchLimits limits={});
    void refresh();
    CodeSearchResult search(const std::string& query, std::size_t limit=5,
                            std::size_t context=2) const;
private:
    struct Source {
        std::string path, raw;
        std::vector<std::string> lines;
        std::set<std::string> path_terms;
        std::unordered_map<std::string,std::vector<std::size_t>> postings;
        std::size_t entries=0;
    };
    std::string root_;
    SearchLimits limits_;
    std::vector<std::shared_ptr<const Source>> sources_;
    CodeSearchResult stats_;
};
std::string format_code_result(const CodeSearchResult& result);
std::string code_result_json(const CodeSearchResult& result);
}
