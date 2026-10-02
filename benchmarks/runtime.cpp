#include "edgeai/HybridBackend.hpp"
#include "edgeai/TransformerBackend.hpp"
#include <chrono>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
template<class Backend>void run_benchmark(Backend&b,std::size_t tokens,const std::string&name){
    for(int i=0;i<128;++i)b.step(static_cast<unsigned char>(i));b.reset();double checksum=0;
    auto start=std::chrono::steady_clock::now();auto cpu_start=std::clock();
    for(std::size_t i=0;i<tokens;++i){auto&z=b.step(static_cast<unsigned char>(i%256));checksum+=z[i%256];}
    double cpu=double(std::clock()-cpu_start)/CLOCKS_PER_SEC;
    double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    if(!std::isfinite(checksum))throw std::runtime_error("nonfinite forward output");
    std::cout<<std::setprecision(12)<<"{\"tokens\":"<<tokens<<",\"seconds\":"<<sec
      <<",\"cpu_seconds\":"<<cpu<<",\"requested_kernel\":\""<<name<<"\",\"byte_steps_per_second\":"<<tokens/sec
      <<",\"weights_bytes\":"<<b.model().weight_bytes()<<",\"state_payload_bytes\":"<<b.model().state_payload_bytes()
      <<",\"numeric_working_bytes\":"<<b.numeric_working_bytes()<<",\"checksum\":"<<checksum
      <<",\"energy_joules\":null,\"note\":\"teacher-forced byte steps, not useful answers per second; model load and warmup excluded from step timer\"}\n";
}
int main(int argc,char**argv){try{
    if(argc<2||argc>4){std::cerr<<"usage: edgeai_runtime_benchmark model.edge [tokens] [auto|scalar|lookup2|avx2]\n";return 2;}
    std::string count=argc>2?argv[2]:"20000";
    if(count.empty()||count.find_first_not_of("0123456789")!=std::string::npos)throw std::invalid_argument("tokens must be an unsigned integer");
    std::size_t tokens=std::stoul(count);
    if(tokens==0||tokens>1000000)throw std::invalid_argument("tokens in 1..1000000");
    std::string name=argc>3?argv[3]:"auto";edgeai::Kernel kernel=edgeai::Kernel::Auto;
    if(name=="scalar")kernel=edgeai::Kernel::Scalar;else if(name=="lookup2")kernel=edgeai::Kernel::Lookup;
    else if(name=="avx2")kernel=edgeai::Kernel::Avx2;else if(name!="auto")throw std::invalid_argument("unknown kernel");
    if(edgeai::is_transformer_file(argv[1])){edgeai::TransformerBackend b(argv[1],kernel);if(b.model().tokenizer.has_bos())throw std::invalid_argument("use edgeai_text_eval or edgeai_generate for EDGEAI6 same-text benchmarks");run_benchmark(b,tokens,name);}
    else{edgeai::HybridBackend b(argv[1],kernel);run_benchmark(b,tokens,name);}
    return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
