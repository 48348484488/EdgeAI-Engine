#include "edgeai/Engine.hpp"
#include "edgeai/EdgeModel.hpp"
#include "edgeai/Ternary.hpp"
#include "edgeai/TernaryBackend.hpp"
#include <stdexcept>
#define CHECK(x) do { if(!(x)) throw std::runtime_error("CHECK failed: " #x); } while(false)
#include <cmath>
#include <cstdio>
#include <iostream>
#include <memory>
int main(){
    using namespace edgeai;
    Engine e(Mode::Eco,":memory:",std::make_shared<EchoReasonerBackend>());
    auto a=e.ask("253 * 719");CHECK(!a.neural_used&&a.text=="181907");CHECK(e.ask("(10 + 5) * 3").text=="45");
    CHECK(!e.ask("Add: 40 + 41").neural_used&&e.ask("Add: 40 + 41").text=="81");
    CHECK(!e.ask("Some: 40 + 41").neural_used&&e.ask("Some: 40 + 41").text=="81");
    CHECK(!e.ask("What is the sum of 42 and 47?").neural_used&&e.ask("What is the sum of 42 and 47?").text=="89");
    CHECK(!e.ask("Quanto vale a soma de 42 e 47?").neural_used&&e.ask("Quanto vale a soma de 42 e 47?").text=="89");
    CHECK(e.ask("Add: apples").neural_used);
    e.ask("lembrar: pesos ternarios economizam memoria");CHECK(e.ask("buscar memoria: ternarios").text.find("ternarios")!=std::string::npos);
    TernaryMatrix t(2,4);t.set_scale(0,2);t.set_scale(1,.5f);t.set(0,0,1);t.set(0,1,-1);t.set(0,3,1);t.set(1,0,-1);t.set(1,2,1);std::vector<float>x{1,2,3,4};auto y=t.matvec(x);CHECK(std::fabs(y[0]-6.0f)<1e-5f);CHECK(std::fabs(y[1]-1.0f)<1e-5f);CHECK(t.packed_bytes()==2);
    auto m=make_demo_edge_model(16,32);CHECK(m.valid());CHECK(m.compression_ratio_vs_fp32()>1.0);const std::string p="test_demo.edge";m.save(p);auto m2=EdgeModel::load(p);CHECK(m2.valid());CHECK(m2.parameter_count()==m.parameter_count());
    Engine n(Mode::Eco,":memory:",std::make_shared<TernaryBackend>(m2));auto r=n.ask("teste do backend neural");CHECK(r.neural_used);CHECK(r.loops_used>=1);CHECK(!r.text.empty());std::remove(p.c_str());
    std::cout<<"all tests passed\n";
}
