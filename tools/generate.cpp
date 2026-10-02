#include "edgeai/TransformerBackend.hpp"
#include <algorithm>
#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
using Clock=std::chrono::steady_clock;
double seconds(Clock::time_point a){return std::chrono::duration<double>(Clock::now()-a).count();}
int main(int argc,char**argv){try{
    if(argc<4||argc>5){std::cerr<<"usage: edgeai_generate model.edge prompt.bin output.bin [max_tokens]\n";return 2;}
    std::string n=argc==5?argv[4]:"32";if(n.empty()||n.find_first_not_of("0123456789")!=std::string::npos)throw std::invalid_argument("max_tokens must be integer");auto count=std::stoul(n);if(count<1||count>4096)throw std::invalid_argument("max_tokens in 1..4096");
    auto all=Clock::now();auto cpu=std::clock();auto t=Clock::now();edgeai::TransformerBackend b(argv[1]);double load=seconds(t);
    std::ifstream in(argv[2],std::ios::binary);if(!in)throw std::runtime_error("cannot open prompt");in.seekg(0,std::ios::end);if(in.tellg()>1024*1024)throw std::runtime_error("prompt limit 1 MiB");in.seekg(0);std::string prompt((std::istreambuf_iterator<char>(in)),{});
    t=Clock::now();const auto&tok=b.model().tokenizer;auto ids=tok.encode_prompt(prompt);if(ids.empty())ids.push_back('\n');double tokenization=seconds(t);
    t=Clock::now();std::vector<float> z;for(auto id:ids)z=b.step(id);double prefill=seconds(t);
    t=Clock::now();std::string raw;bool stopped=false;std::size_t generated=0;count=std::min(count,static_cast<unsigned long>(b.model().config.max_generate));
    for(std::size_t i=0;i<count;++i){auto id=b.greedy_token();++generated;if(tok.has_eos()&&id==tok.eos_id()){stopped=true;break;}raw+=tok.piece(id);if(i+1<count)z=b.step(id);}
    double generation=seconds(t);std::ofstream out(argv[3],std::ios::binary);if(!out)throw std::runtime_error("cannot open generation output");out.write(raw.data(),raw.size());if(!out)throw std::runtime_error("generation output write failed");
    std::cout<<std::setprecision(14)<<"{\"prompt_bytes\":"<<prompt.size()<<",\"prefill_tokens_including_bos\":"<<ids.size()<<",\"generated_tokens\":"<<generated<<",\"stopped_on_eos\":"<<(stopped?"true":"false")<<",\"stop_reason\":\""<<(stopped?"eos":"length")<<"\",\"generated_bytes\":"<<raw.size()<<",\"load_seconds\":"<<load<<",\"tokenization_seconds\":"<<tokenization<<",\"prefill_seconds\":"<<prefill<<",\"generation_seconds\":"<<generation<<",\"total_seconds\":"<<seconds(all)<<",\"cpu_seconds\":"<<double(std::clock()-cpu)/CLOCKS_PER_SEC<<",\"energy_joules\":null}\n";
    return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
