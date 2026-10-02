#include "edgeai/ByteBPE.hpp"
#include "edgeai/TransformerBackend.hpp"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <limits>
#include <algorithm>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
template<class F>void rejects(F f){bool ok=false;try{f();}catch(const std::exception&){ok=true;}CHECK(ok);}
int main(){using namespace edgeai;
    ByteBPE t({{97,97},{256,256}});CHECK(t.vocab_size()==259);CHECK(t.bos_id()==258);
    CHECK(t.encode("aaaaa")==std::vector<std::uint32_t>({257,97}));
    std::string raw;for(unsigned i=0;i<768;++i)raw+=char(i%256);CHECK(t.decode(t.encode(raw,true))==raw);
    CHECK(t.decode(t.encode("ação 🐈\n",true))=="ação 🐈\n");
    rejects([]{ByteBPE bad({{256,1}});});rejects([]{ByteBPE bad({{97,32}});});
    rejects([]{ByteBPE bad({{97,98},{97,98}});});rejects([&]{t.piece(999);});
    rejects([]{ByteBPE{}.bos_id();});
    auto m=make_transformer_demo(8,12,5);m.tokenizer=t;m.embedding.resize(t.vocab_size()*m.config.dim,.03f);m.output=MixedMatrix(DenseMatrix(t.vocab_size(),m.config.dim));CHECK(m.valid());
    m.save("bpe-test.edge");auto loaded=TransformerModel::load("bpe-test.edge");CHECK(loaded.tokenizer.encode("aaaaa",true)==t.encode("aaaaa",true));
    TransformerBackend a(m),b(loaded);for(unsigned i=0;i<500;++i){auto id=i%t.vocab_size();CHECK(a.step(id)==b.step(id));CHECK(a.cache_size()<=5);}
    rejects([&]{a.step(static_cast<std::uint32_t>(t.vocab_size()));});
    std::ifstream in("bpe-test.edge",std::ios::binary);std::string bytes((std::istreambuf_iterator<char>(in)),{});
    // Merge count at offset 32; reject allocation bombs before attempting allocation.
    bytes[32]=bytes[33]=bytes[34]=bytes[35]=char(255);
    {std::ofstream o("bpe-bad.edge",std::ios::binary);o<<bytes;}
    rejects([]{TransformerModel::load("bpe-bad.edge");});
    auto extreme=m;std::fill(extreme.embedding.begin(),extreme.embedding.end(),std::numeric_limits<float>::max());
    TransformerBackend extreme_backend(extreme);rejects([&]{extreme_backend.step(0);});
    std::remove("bpe-test.edge");std::remove("bpe-bad.edge");std::cout<<"BPE lossless, ranked, bounded, serialization and dynamic vocabulary passed\n";
}
