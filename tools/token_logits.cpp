// Explicit token trace for cross-language verification, including RESPONSE/EOS.
#include "edgeai/TransformerBackend.hpp"
#include "edgeai/Binary.hpp"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){try{
    if(argc<4||argc>5){std::cerr<<"usage: edgeai_token_logits model.edge ids.u32 logits.f32 [auto|scalar]\n";return 2;}
    edgeai::binary::little_endian();std::string k=argc==5?argv[4]:"auto";
    if(k!="auto"&&k!="scalar")throw std::invalid_argument("unsupported trace kernel");
    edgeai::TransformerBackend b(argv[1],k=="scalar"?edgeai::Kernel::Scalar:edgeai::Kernel::Auto);
    std::ifstream in(argv[2],std::ios::binary|std::ios::ate);
    if(!in)throw std::runtime_error("cannot open tokens");
    const auto length=in.tellg();
    if(length<=0||length>4096*4||length%4!=0)throw std::runtime_error("expected 1..4096 little-endian u32 tokens");
    in.seekg(0);std::ofstream out(argv[3],std::ios::binary);
    if(!out)throw std::runtime_error("cannot create trace");
    for(std::streamoff n=0;n<length;n+=4){
        std::uint32_t id=0;in.read(reinterpret_cast<char*>(&id),4);
        if(!in)throw std::runtime_error("truncated tokens");
        const auto&z=b.step(id);out.write(reinterpret_cast<const char*>(z.data()),std::streamsize(z.size()*sizeof(float)));
    }
    if(!out)throw std::runtime_error("trace write failed");return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
