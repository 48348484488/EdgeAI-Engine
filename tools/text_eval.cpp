#include "edgeai/TransformerBackend.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <vector>
namespace {
using Clock=std::chrono::steady_clock;
double since(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
std::uint32_t u32(std::istream&i){unsigned char b[4]{};i.read(reinterpret_cast<char*>(b),4);if(!i)throw std::runtime_error("truncated raw block header");return std::uint32_t(b[0])|(std::uint32_t(b[1])<<8)|(std::uint32_t(b[2])<<16)|(std::uint32_t(b[3])<<24);}
}
int main(int argc,char**argv){try{
    if(argc!=3){std::cerr<<"usage: edgeai_text_eval model.edge input.rawblocks\n";return 2;}
    auto all=Clock::now();auto c0=std::clock();auto a=Clock::now();edgeai::TransformerBackend b(argv[1]);double load=since(a);
    if(!b.model().tokenizer.has_bos())throw std::runtime_error("use edgeai_evaluate for legacy models; raw-block evaluation requires BOS");
    std::ifstream in(argv[2],std::ios::binary);if(!in)throw std::runtime_error("cannot open raw blocks");char magic[8]{};in.read(magic,8);
    if(!in||std::memcmp(magic,"EDGRAW1\0",8))throw std::runtime_error("invalid raw block magic");auto count=u32(in);
    if(!count||count>65536)throw std::runtime_error("raw block count outside 1..65536");
    std::size_t bytes=0,targets=0,correct=0;double nll=0,tokenize=0,forward=0;
    for(std::uint32_t block=0;block<count;++block){auto n=u32(in);if(!n||n>4096||bytes+n>32*1024*1024)throw std::runtime_error("raw block limits exceeded");
        std::string raw(n,'\0');in.read(raw.data(),n);if(!in)throw std::runtime_error("truncated raw block");bytes+=n;
        a=Clock::now();auto ids=b.model().tokenizer.encode(raw,true);tokenize+=since(a);a=Clock::now();b.reset();
        for(std::size_t j=0;j+1<ids.size();++j){const auto&z=b.step(ids[j]);auto best=std::max_element(z.begin(),z.end());double sum=0;
            for(float v:z){if(!std::isfinite(v))throw std::runtime_error("nonfinite logits");sum+=std::exp(double(v)-double(*best));}
            nll+=std::log(sum)+double(*best)-double(z[ids[j+1]]);correct+=std::size_t(best-z.begin())==ids[j+1];++targets;}
        forward+=since(a);
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing raw block data");
    std::cout<<std::setprecision(14)<<"{\"blocks\":"<<count<<",\"raw_bytes\":"<<bytes<<",\"target_tokens\":"<<targets<<",\"nll_sum\":"<<nll<<",\"bits_per_byte\":"<<nll/(bytes*std::log(2.))
      <<",\"token_accuracy\":"<<double(correct)/targets<<",\"load_seconds\":"<<load<<",\"tokenization_seconds\":"<<tokenize<<",\"forward_and_scoring_seconds\":"<<forward<<",\"total_seconds\":"<<since(all)
      <<",\"cpu_seconds\":"<<double(std::clock()-c0)/CLOCKS_PER_SEC<<",\"weights_bytes\":"<<b.model().weight_bytes()<<",\"state_bytes\":"<<b.model().state_payload_bytes()<<",\"working_bytes\":"<<b.numeric_working_bytes()<<",\"bos_scored_as_byte\":false,\"energy_joules\":null}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
