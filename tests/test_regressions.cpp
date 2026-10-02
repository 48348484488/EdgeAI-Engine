#include "edgeai/Ternary.hpp"
#include "edgeai/TernaryBackend.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
using namespace edgeai;
void require(bool x,const char* msg){if(!x)throw std::runtime_error(msg);}
template<class F> void must_throw(F f,const char* msg){bool ok=false;try{f();}catch(const std::exception&){ok=true;}require(ok,msg);}
void legacy_state(){
 auto m=make_demo_edge_model(8,16);m.config.default_loops=1;m.config.max_generate=4;m.config.early_exit_confidence=1;
 auto backend=TernaryBackend(m);Budget b{1,512,1,1};std::string prompt="teste";
 auto r=backend.infer(prompt,b);std::vector<float> h(8,0);std::string expected;double confidence=0;
 auto consume=[&](unsigned char c){std::vector<float>x(m.embedding.begin()+c*8,m.embedding.begin()+(c+1)*8);auto a=m.wx.matvec(x),z=m.wh.matvec(h);for(int j=0;j<8;++j)h[j]=std::tanh(a[j]+z[j]);};
 for(unsigned char c:prompt)consume(c);
 for(int t=0;t<4;++t){auto q=h,n=h;float mean=std::accumulate(n.begin(),n.end(),0.f)/8,var=0;for(float x:n)var+=(x-mean)*(x-mean);float inv=1/std::sqrt(var/8+1e-5f);for(float& x:n)x=(x-mean)*inv;
 auto up=m.reason_up.matvec(n);for(float&x:up)x=x/(1+std::exp(-x));auto down=m.reason_down.matvec(up);for(int j=0;j<8;++j)q[j]+=.5f*down[j];auto z=m.output.matvec(q);float mx=*std::max_element(z.begin(),z.end());double s=0;for(float v:z)s+=std::exp(double(v-mx));confidence=1/s;auto c=std::distance(z.begin(),std::max_element(z.begin(),z.end()));if(c<9||(c>13&&c<32))c=32;expected+=static_cast<char>(c);consume(static_cast<unsigned char>(c));}
 std::cout<<"native_conf="<<r.confidence<<" reference_conf="<<confidence<<"\n";
 require(r.text==expected&&std::abs(r.confidence-confidence)<2e-6,"readout state leaked into recurrence (training/inference mismatch)");
}
int main(){int fail=0,pass=0;auto test=[&](const char* name,auto f){try{f();std::cout<<"PASS "<<name<<"\n";++pass;}catch(const std::exception&e){std::cout<<"FAIL "<<name<<": "<<e.what()<<"\n";++fail;}};
 test("legacy state parity",legacy_state);
 test("reject invalid ternary weight",[]{TernaryMatrix t(2,3);must_throw([&]{t.set(0,0,7);},"weight outside -1,0,1 accepted");});
 test("reject NaN scale",[]{TernaryMatrix t(2,3);must_throw([&]{t.set_scale(0,std::numeric_limits<float>::quiet_NaN());},"NaN scale accepted");});
 test("reject zero loops",[]{auto m=make_demo_edge_model(8,16);m.config.default_loops=0;require(!m.valid(),"zero loops model accepted");});
 std::cout<<"passed="<<pass<<" failed="<<fail<<"\n";return fail?1:0;}
