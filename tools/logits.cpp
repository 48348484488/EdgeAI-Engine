#include "edgeai/HybridBackend.hpp"
#include "edgeai/TransformerBackend.hpp"
#include "edgeai/TernaryBackend.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
int main(int argc,char**argv){try{
 if(argc<4){std::cerr<<"usage: edgeai_logits model.edge input.bin logits.f32 [auto|scalar|lookup2|avx2]\n";return 2;}
 edgeai::Kernel k=edgeai::Kernel::Auto;std::string name=argc>4?argv[4]:"auto";if(name=="scalar")k=edgeai::Kernel::Scalar;else if(name=="lookup2")k=edgeai::Kernel::Lookup;else if(name=="avx2")k=edgeai::Kernel::Avx2;else if(name!="auto")throw std::invalid_argument("unknown kernel");
 std::ifstream in(argv[2],std::ios::binary);if(!in)throw std::runtime_error("cannot open input");in.seekg(0,std::ios::end);if(in.tellg()>1024*1024)throw std::runtime_error("trace input limit is 1MiB");in.seekg(0);std::string bytes((std::istreambuf_iterator<char>(in)),{});std::ofstream out(argv[3],std::ios::binary);if(!out)throw std::runtime_error("cannot open trace output");
 if(edgeai::is_transformer_file(argv[1])){edgeai::TransformerBackend b(argv[1],k);for(auto c:b.model().tokenizer.encode_prompt(bytes)){const auto& z=b.step(c);out.write(reinterpret_cast<const char*>(z.data()),static_cast<std::streamsize>(z.size()*4));}}
 else if(edgeai::is_hybrid_file(argv[1])){edgeai::HybridBackend b(argv[1],k);for(unsigned char c:bytes){const auto& z=b.step(c);out.write(reinterpret_cast<const char*>(z.data()),static_cast<std::streamsize>(z.size()*4));}}
 else{edgeai::TernaryBackend b(argv[1],k);std::vector<float> state(b.model().config.dim,0);for(unsigned char c:bytes){auto z=b.forward_token(c,state);out.write(reinterpret_cast<const char*>(z.data()),static_cast<std::streamsize>(z.size()*4));}}
 if(!out)throw std::runtime_error("trace write failed");return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
