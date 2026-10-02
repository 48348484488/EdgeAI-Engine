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
    std::remove("transformer-test.edge");std::remove("transformer-bad.edge");
    std::cout<<"Transformer bounded cache, reset, finite forward, serialization and rejection passed\n";
}
