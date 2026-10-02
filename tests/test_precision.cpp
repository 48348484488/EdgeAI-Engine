#include "edgeai/MixedMatrix.hpp"
#include "edgeai/HybridBackend.hpp"
#include <cmath>
#include <cstring>
#include <cstdio>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
using namespace edgeai;
template<class F> void rejected(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}CHECK(caught);}
int main(){
    for(auto cols:{1u,7u,13u,32u}){
        Int8Matrix m(7,cols); DenseMatrix reference(7,cols);
        std::vector<float>x(cols),out(7);
        for(unsigned c=0;c<cols;++c)x[c]=std::sin(float(c)*.7f);
        for(unsigned r=0;r<7;++r){
            float scale=.001f*(r+1),bias=.3f*r;
            m.set_scale(r,scale);m.set_bias(r,bias);reference.bias(r)=bias;
            for(unsigned c=0;c<cols;++c){int q=int((r*97+c*31)%255)-127;m.set(r,c,q);reference.weight(r,c)=q*scale;}
        }
        auto expected=reference.matvec(x);
        for(Kernel k:{Kernel::Scalar,Kernel::Auto,Kernel::Lookup}){
            m.matvec_into(x.data(),x.size(),out.data(),out.size(),k);
            for(unsigned r=0;r<7;++r)CHECK(std::abs(out[r]-expected[r])<2e-5f);
        }
        if(avx2_available()){
            m.matvec_into(x.data(),x.size(),out.data(),out.size(),Kernel::Avx2);
            for(unsigned r=0;r<7;++r)CHECK(std::abs(out[r]-expected[r])<2e-5f);
        }
        CHECK(m.storage_bytes()==7*cols+7*8);
        std::stringstream bytes(std::ios::in|std::ios::out|std::ios::binary);m.save(bytes);
        auto loaded=Int8Matrix::load(bytes);
        for(unsigned r=0;r<7;++r)for(unsigned c=0;c<cols;++c)CHECK(loaded.get(r,c)==m.get(r,c));
        rejected([&]{m.set(0,0,-128);});rejected([&]{m.set(0,0,128);});
        rejected([&]{m.set_scale(0,0);});rejected([&]{m.set_scale(0,-1);});
        rejected([&]{m.set_scale(0,std::numeric_limits<float>::infinity());});
        rejected([&]{m.set_bias(0,std::numeric_limits<float>::quiet_NaN());});
        rejected([&]{m.matvec_into(x.data(),cols-1,out.data(),out.size());});
        auto raw=bytes.str();
        for(std::size_t n=0;n<raw.size();++n){std::stringstream short_file(raw.substr(0,n));rejected([&]{Int8Matrix::load(short_file);});}
        auto bad=raw;bad[16]=char(128);std::stringstream invalid_code(bad);rejected([&]{Int8Matrix::load(invalid_code);});
        bad=raw;std::memset(&bad[16+7*cols],0,4);std::stringstream zero_scale(bad);rejected([&]{Int8Matrix::load(zero_scale);});
    }
    TernaryMatrix t(3,5);DenseMatrix d(3,5);Int8Matrix i(3,5);
    for(unsigned r=0;r<3;++r)for(unsigned c=0;c<5;++c){t.set(r,c,int(c%3)-1);d.weight(r,c)=float(c)-2;i.set(r,c,int(c)-2);}
    for(auto m:{MixedMatrix(t),MixedMatrix(d),MixedMatrix(i)}){
        std::stringstream stream(std::ios::in|std::ios::out|std::ios::binary);m.save(stream);
        auto copy=MixedMatrix::load(stream);CHECK(copy.kind()==m.kind());CHECK(copy.storage_bytes()==m.storage_bytes());
        CHECK(copy.matvec(std::vector<float>(5,1))==m.matvec(std::vector<float>(5,1)));
    }
    std::stringstream invalid(std::string("\xff\x00\x00\x00",4));rejected([&]{MixedMatrix::load(invalid);});
    rejected([&]{Int8Matrix(0,3);});rejected([&]{Int8Matrix(65536,65536);});
    auto model=make_hybrid_demo(16,8,4);
    model.query=DenseMatrix(8,16);model.key=Int8Matrix(8,16);model.output=Int8Matrix(256,16);
    CHECK(model.valid());model.save("precision-roundtrip.edge");
    auto loaded=HybridModel::load("precision-roundtrip.edge");
    CHECK(loaded.source_format_version==4);CHECK(loaded.query.kind()==Precision::Fp32);
    CHECK(loaded.key.kind()==Precision::Int8);CHECK(loaded.up.kind()==Precision::Ternary);
    CHECK(loaded.output.kind()==Precision::Int8);CHECK(loaded.weight_bytes()==model.weight_bytes());
    HybridBackend b(loaded);for(unsigned n=0;n<100;++n)for(float v:b.step(n))CHECK(std::isfinite(v));
    CHECK(load_backend("precision-roundtrip.edge")->available());std::remove("precision-roundtrip.edge");
    std::cout<<"INT8 and mixed dtype arithmetic, validation, serialization, integration passed\n";
}
