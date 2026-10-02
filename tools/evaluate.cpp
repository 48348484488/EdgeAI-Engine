#include "edgeai/HybridBackend.hpp"
#include "edgeai/TransformerBackend.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
namespace {
std::uint32_t u32(std::istream&i){unsigned char b[4]{};i.read(reinterpret_cast<char*>(b),4);if(!i)throw std::runtime_error("truncated block header");return std::uint32_t(b[0])|(std::uint32_t(b[1])<<8)|(std::uint32_t(b[2])<<16)|(std::uint32_t(b[3])<<24);}
std::vector<std::vector<std::uint8_t>> read_blocks(const std::string&path){
    std::ifstream i(path,std::ios::binary);if(!i)throw std::runtime_error("cannot open blocks");
    char magic[8]{};i.read(magic,8);if(!i||std::memcmp(magic,"EDGBLK1\0",8)!=0)throw std::runtime_error("invalid block format");
    auto count=u32(i);if(count==0||count>1000000)throw std::runtime_error("invalid block count");
    std::vector<std::vector<std::uint8_t>> blocks;std::size_t total=0;
    for(std::uint32_t n=0;n<count;++n){auto size=u32(i);total+=size+1;if(!size||size>4096||total>128ull*1024*1024)throw std::runtime_error("block input limits exceeded");
        std::vector<std::uint8_t> raw(size+1);i.read(reinterpret_cast<char*>(raw.data()),raw.size());if(!i)throw std::runtime_error("truncated block payload");blocks.push_back(std::move(raw));}
    if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing block bytes");return blocks;
}
template<class Backend>void evaluate(Backend&b,const std::vector<std::vector<std::uint8_t>>&blocks){
    double nll=0;std::size_t total=0,correct=0;auto start=std::chrono::steady_clock::now();
    for(const auto&raw:blocks){b.reset();for(std::size_t j=0;j+1<raw.size();++j){const auto&z=b.step(raw[j]);auto best=std::max_element(z.begin(),z.end());double sum=0;
        for(float v:z){if(!std::isfinite(v))throw std::runtime_error("nonfinite logits");sum+=std::exp(double(v)-double(*best));}
        nll+=std::log(sum)+double(*best)-double(z[raw[j+1]]);correct+=std::size_t(best-z.begin())==raw[j+1];++total;}}
    double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    std::cout<<std::setprecision(14)<<"{\"blocks\":"<<blocks.size()<<",\"targets\":"<<total<<",\"correct\":"<<correct<<",\"nll_sum\":"<<nll<<",\"bits_per_byte\":"<<nll/(total*std::log(2.))<<",\"accuracy\":"<<double(correct)/total<<",\"seconds\":"<<seconds<<",\"reset_between_blocks\":true}\n";
}
}
int main(int argc,char**argv){try{
    if(argc!=3){std::cerr<<"usage: edgeai_evaluate model.edge blocks.bin\n";return 2;}auto blocks=read_blocks(argv[2]);
    if(edgeai::is_transformer_file(argv[1])){edgeai::TransformerBackend b(argv[1]);if(b.model().tokenizer.has_bos())throw std::invalid_argument("use edgeai_text_eval for EDGEAI6; legacy metric excludes initial byte");evaluate(b,blocks);}
    else if(edgeai::is_hybrid_file(argv[1])){edgeai::HybridBackend b(argv[1]);evaluate(b,blocks);}
    else throw std::invalid_argument("evaluation supports EDGEAI3/4/5, not legacy EDGEAI2");return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
