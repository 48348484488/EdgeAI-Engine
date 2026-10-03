#include "edgeai/TransformerBackend.hpp"
#include <cstring>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
template<class F>void reject(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}CHECK(caught);}
int main(){using namespace edgeai;
    ByteBPE tok(std::vector<ByteBPE::Pair>{},true);
    CHECK(tok.vocab_size()==259);CHECK(tok.bos_id()==256);CHECK(tok.response_id()==257);CHECK(tok.eos_id()==258);
    CHECK(tok.encode_prompt("")==std::vector<std::uint32_t>({256,257}));
    std::string all;for(int n=0;n<256;++n)all+=char(n);
    CHECK(tok.decode(tok.encode_prompt(all))==all);CHECK(tok.piece(258).empty());reject([&]{tok.piece(259);});
    auto m=make_transformer_demo(8,12,4);m.tokenizer=tok;m.embedding.resize(259*8);
    DenseMatrix output(259,8);output.bias(256)=100;output.bias(257)=90;output.bias(258)=80;m.output=MixedMatrix(output);
    CHECK(m.valid());m.save("instruction-test.edge");
    auto loaded=TransformerModel::load("instruction-test.edge");CHECK(loaded.tokenizer.has_eos());CHECK(is_transformer_file("instruction-test.edge"));
    CHECK(loaded.config.blocks==1);CHECK(loaded.blocks_data.size()==1);
    TransformerBackend b(loaded,Kernel::Scalar);CHECK(b.infer("anything",Budget{1,128,1,1}).text.empty());
    CHECK(b.tokens_seen()==tok.encode_prompt("anything").size());
    std::ifstream in("instruction-test.edge",std::ios::binary);std::string raw((std::istreambuf_iterator<char>(in)),{});
    CHECK(raw.substr(0,7)=="EDGEAI7");
    const std::vector<std::size_t> truncations{0u,8u,32u,raw.size()-1};\n    for(std::size_t n:truncations){std::ofstream o("instruction-bad.edge",std::ios::binary);o.write(raw.data(),n);o.close();reject([&]{TransformerModel::load("instruction-bad.edge");});}
    {std::string bad=raw;bad[32]=char(0xff);bad[33]=char(0xff);bad[34]=char(0xff);bad[35]=char(0x7f);
     std::ofstream o("instruction-bad.edge",std::ios::binary);o.write(bad.data(),bad.size());o.close();reject([&]{TransformerModel::load("instruction-bad.edge");});}
    {std::ofstream o("instruction-bad.edge",std::ios::binary);o<<raw<<"junk";o.close();reject([&]{TransformerModel::load("instruction-bad.edge");});}
    std::remove("instruction-test.edge");std::remove("instruction-bad.edge");std::cout<<"instruction framing, EOS, roundtrip, malformed data passed\n";
}
