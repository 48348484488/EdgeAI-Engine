#include "edgeai/Memory.hpp"
#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <unordered_set>
#include <stdexcept>
namespace edgeai {
static std::vector<std::string> words(std::string s){
    for(char& c:s){ unsigned char u=(unsigned char)c; if(c>='A'&&c<='Z') c=char(c+32); if(!(std::isalnum(u)||u>=128)) c=' '; }
    std::istringstream in(s); std::vector<std::string> out; std::string w; while(in>>w) out.push_back(w); return out;
}
LocalMemory::LocalMemory(std::string path):path_(std::move(path)){ load(); }
void LocalMemory::load(){ items_.clear(); if(path_==":memory:")return; std::ifstream f(path_); std::string line; while(std::getline(f,line)) if(!line.empty()) items_.push_back(line); }
void LocalMemory::add(const std::string& text){ if(text.empty())return; if(path_!=":memory:"){ std::ofstream f(path_,std::ios::app); f<<text<<'\n'; f.flush(); if(!f)throw std::runtime_error("failed to persist memory"); } items_.push_back(text); }
std::vector<std::string> LocalMemory::search(const std::string& query,std::size_t limit) const{
    auto qw=words(query); std::unordered_set<std::string> qs(qw.begin(),qw.end());
    struct Sc{double score; std::size_t i;}; std::vector<Sc> scores;
    for(std::size_t i=0;i<items_.size();++i){ auto iw=words(items_[i]); std::unordered_set<std::string> is(iw.begin(),iw.end()); double hit=0; for(auto& q:qs) if(is.count(q)) hit+=1; if(hit>0) scores.push_back({hit/(1.0+0.05*is.size()),i}); }
    std::sort(scores.begin(),scores.end(),[](auto&a,auto&b){return a.score>b.score;});
    std::vector<std::string> out; for(std::size_t n=0;n<scores.size()&&n<limit;++n) out.push_back(items_[scores[n].i]); return out;
}
}
