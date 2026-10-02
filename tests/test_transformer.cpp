#include "edgeai/TransformerBackend.hpp"
#include "edgeai/HybridBackend.hpp"
#include "edgeai/Text.hpp"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
template<class F>void rejected(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}CHECK(caught);}
int main(){using namespace edgeai;
    CHECK(display_utf8(std::string("\x1b\xc0\xaf",3))==std::string(" \xef\xbf\xbd\xef\xbf\xbd"));
    CHECK(display_utf8("ação\n")=="ação\n");
    CHECK(display_utf8(std::string("\xf0\x9f",2))==std::string("\xef\xbf\xbd\xef\xbf\xbd"));
    auto m=make_transformer_demo(16,23,7);CHECK(m.valid());
    auto multi=make_transformer_demo(16,23,7,2);CHECK(multi.valid());
    CHECK(multi.config.blocks==2);CHECK(multi.blocks_data.size()==2);
    CHECK(multi.state_payload_bytes()==2*m.state_payload_bytes());
    CHECK(multi.parameter_count()>m.parameter_count());CHECK(multi.weight_bytes()>m.weight_bytes());
    multi.save("transformer-multi.edge");
    auto multi_loaded=TransformerModel::load("transformer-multi.edge");
    CHECK(multi_loaded.valid());CHECK(multi_loaded.config.blocks==2);CHECK(multi_loaded.blocks_data.size()==2);
    CHECK(multi_loaded.parameter_count()==multi.parameter_count());CHECK(multi_loaded.weight_bytes()==multi.weight_bytes());
    TransformerBackend multi_backend(multi_loaded,Kernel::Scalar);
    const auto multi_bytes=multi_backend.numeric_working_bytes();
    std::vector<float> multi_first;
    for(unsigned i=0;i<40;++i){
        auto z=multi_backend.step(i%256);for(float v:z)CHECK(std::isfinite(v));if(i==0)multi_first=z;
        auto sizes=multi_backend.block_cache_sizes();CHECK(sizes.size()==2);for(auto n:sizes)CHECK(n<=7);
    }
    auto wrapped=multi_backend.block_cache_sizes();CHECK(wrapped[0]==7&&wrapped[1]==7);
    multi_backend.reset();auto reset_sizes=multi_backend.block_cache_sizes();CHECK(reset_sizes==std::vector<std::size_t>({0,0}));
    CHECK(multi_backend.step(0)==multi_first);
    TransformerBackend single_backend(m,Kernel::Scalar);CHECK(multi_bytes>single_backend.numeric_working_bytes());
    auto altered=multi_loaded;
    altered.blocks_data[1].project=MixedMatrix(DenseMatrix(16,16));
    TransformerBackend altered_backend(altered,Kernel::Scalar);auto original_logits=multi_backend.step(1);auto altered_logits=altered_backend.step(1);
    CHECK(original_logits!=altered_logits);
    std::ifstream multi_in("transformer-multi.edge",std::ios::binary);std::string multi_raw((std::istreambuf_iterator<char>(multi_in)),{});
    CHECK(multi_raw.substr(0,7)=="EDGEAI8");
    auto corrupt_blocks=[&](std::uint32_t count){
        std::string bad=multi_raw;for(int j=0;j<4;++j)bad[32+j]=char((count>>(8*j))&0xff);
        std::ofstream o("transformer-bad.edge",std::ios::binary);o.write(bad.data(),bad.size());o.close();
        rejected([&]{TransformerModel::load("transformer-bad.edge");});
    };
    corrupt_blocks(0);corrupt_blocks(9);
    for(auto n:{0ul,8ul,36ul,multi_raw.size()-1}){std::ofstream o("transformer-bad.edge",std::ios::binary);o.write(multi_raw.data(),n);o.close();rejected([&]{TransformerModel::load("transformer-bad.edge");});}
    {std::ofstream o("transformer-bad.edge",std::ios::binary);o<<multi_raw<<"extra";o.close();rejected([&]{TransformerModel::load("transformer-bad.edge");});}
    rejected([&]{make_transformer_demo(16,23,7,0);});rejected([&]{make_transformer_demo(16,23,7,9);});
    m.save("transformer-test.edge");auto reloaded=TransformerModel::load("transformer-test.edge");
    CHECK(reloaded.weight_bytes()==m.weight_bytes());CHECK(reloaded.parameter_count()==m.parameter_count());
    TransformerBackend a(m,Kernel::Scalar),b(reloaded,Kernel::Scalar);
    std::vector<float> first;
    const auto bytes=a.numeric_working_bytes();
    for(unsigned i=0;i<700;++i){auto z=a.step(i%256);auto w=b.step(i%256);CHECK(z==w);
        for(float v:z)CHECK(std::isfinite(v));if(!i)first=z;
        CHECK(a.cache_size()<=7);CHECK(a.numeric_working_bytes()==bytes);
    }
    CHECK(a.tokens_seen()==700);a.reset();CHECK(a.tokens_seen()==0);CHECK(a.cache_size()==0);CHECK(a.step(0)==first);
    CHECK(load_backend("transformer-test.edge")->name().find("transformer")!=std::string::npos);
    CHECK(a.infer("teste",Budget{8,128,3,1}).loops_used==1);
    auto bad=m;bad.config.dim=15;CHECK(!bad.valid());rejected([&]{TransformerBackend broken(bad);});
    bad=m;bad.embedding[0]=std::numeric_limits<float>::quiet_NaN();CHECK(!bad.valid());
    std::ifstream in("transformer-test.edge",std::ios::binary);std::string raw((std::istreambuf_iterator<char>(in)),{});
    for(auto n:{0ul,8ul,30ul,raw.size()-1}){std::ofstream o("transformer-bad.edge",std::ios::binary);o.write(raw.data(),n);o.close();rejected([&]{TransformerModel::load("transformer-bad.edge");});}
    {std::ofstream o("transformer-bad.edge",std::ios::binary);o<<raw<<"extra";o.close();rejected([&]{TransformerModel::load("transformer-bad.edge");});}
    rejected([&]{make_transformer_demo(7,9,2);});
    std::remove("transformer-test.edge");std::remove("transformer-multi.edge");std::remove("transformer-bad.edge");
    std::cout<<"Transformer bounded cache, reset, finite forward, serialization and rejection passed\n";
}
