#include "edgeai/TransformerModel.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
int main(int argc,char**argv){try{
    if(argc!=3){std::cerr<<"usage: edgeai_tokenize model.edge input.bin\n";return 2;}
    auto m=edgeai::TransformerModel::load(argv[1]);std::ifstream in(argv[2],std::ios::binary);if(!in)throw std::runtime_error("cannot read tokenizer input");
    in.seekg(0,std::ios::end);if(in.tellg()>1024*1024)throw std::runtime_error("tokenizer CLI input limit 1 MiB");in.seekg(0);
    std::string raw((std::istreambuf_iterator<char>(in)),{});auto ids=m.tokenizer.encode_prompt(raw);
    if(m.tokenizer.decode(ids)!=raw)throw std::runtime_error("tokenizer roundtrip failed");
    std::cout<<"{\"vocab_size\":"<<m.tokenizer.vocab_size()<<",\"raw_bytes\":"<<raw.size()<<",\"ids\":[";
    for(std::size_t i=0;i<ids.size();++i){if(i)std::cout<<',';std::cout<<ids[i];}std::cout<<"]}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
