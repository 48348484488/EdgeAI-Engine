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
    try {
    using namespace edgeai;
    Engine e(Mode::Eco,":memory:",std::make_shared<EchoReasonerBackend>());
    auto a=e.ask("253 * 719");CHECK(!a.neural_used&&a.text=="181907");CHECK(e.ask("(10 + 5) * 3").text=="45");
    CHECK(!e.ask("Add: 40 + 41").neural_used&&e.ask("Add: 40 + 41").text=="81");
    CHECK(!e.ask("Some: 40 + 41").neural_used&&e.ask("Some: 40 + 41").text=="81");
    CHECK(!e.ask("What is the sum of 42 and 47?").neural_used&&e.ask("What is the sum of 42 and 47?").text=="89");
    CHECK(!e.ask("Quanto vale a soma de 42 e 47?").neural_used&&e.ask("Quanto vale a soma de 42 e 47?").text=="89");
    CHECK(e.ask("Add: apples").neural_used);
    CHECK(!e.ask("Copy exactly: edge").neural_used&&e.ask("Copy exactly: edge").text=="edge");
    CHECK(!e.ask("Copie exatamente: teste").neural_used&&e.ask("Copie exatamente: teste").text=="teste");
    CHECK(!e.ask("Uppercase: edge ai").neural_used&&e.ask("Uppercase: edge ai").text=="EDGE AI");
    CHECK(!e.ask("Maiusculas: edge").neural_used&&e.ask("Maiusculas: edge").text=="EDGE");
    CHECK(!e.ask("Expression for x + 57:").neural_used&&e.ask("Expression for x + 57:").text=="x+57");
    CHECK(!e.ask("Expressao para x * 58:").neural_used&&e.ask("Expressao para x * 58:").text=="x*58");
    CHECK(e.ask("Uppercase this paragraph please").neural_used);
    CHECK(!e.ask("Calculate 42 + 47").neural_used&&e.ask("Calculate 42 + 47").text=="89");
    CHECK(!e.ask("What is 42 + 47?").neural_used&&e.ask("What is 42 + 47?").text=="89");
    CHECK(!e.ask("Subtract 17 from 42").neural_used&&e.ask("Subtract 17 from 42").text=="25");
    CHECK(!e.ask("Subtraia 17 de 42").neural_used&&e.ask("Subtraia 17 de 42").text=="25");
    CHECK(!e.ask("Multiply 12 by 7").neural_used&&e.ask("Multiply 12 by 7").text=="84");
    CHECK(!e.ask("Multiplique 12 por 7").neural_used&&e.ask("Multiplique 12 por 7").text=="84");
    CHECK(!e.ask("Divide 84 by 7").neural_used&&e.ask("Divide 84 by 7").text=="12");
    CHECK(!e.ask("Divida 84 por 7").neural_used&&e.ask("Divida 84 por 7").text=="12");
    CHECK(e.ask("Subtract apples from oranges").neural_used);
    CHECK(e.ask("Multiply effort by focus").neural_used);
    CHECK(e.ask("Divide the work by teams").neural_used);
    CHECK(!e.ask("Repeat exactly: edge").neural_used&&e.ask("Repeat exactly: edge").text=="edge");
    CHECK(!e.ask("Repita exatamente: teste").neural_used&&e.ask("Repita exatamente: teste").text=="teste");
    CHECK(!e.ask("Convert to uppercase: edge ai").neural_used&&e.ask("Convert to uppercase: edge ai").text=="EDGE AI");
    CHECK(!e.ask("Converta para maiusculas: edge").neural_used&&e.ask("Converta para maiusculas: edge").text=="EDGE");
    CHECK(!e.ask("Return only x + 57").neural_used&&e.ask("Return only x + 57").text=="x+57");
    CHECK(!e.ask("Retorne apenas x * 58").neural_used&&e.ask("Retorne apenas x * 58").text=="x*58");
    CHECK(!e.ask("Reverse: abcdef").neural_used&&e.ask("Reverse: abcdef").text=="fedcba");
    CHECK(!e.ask("Inverta: teste").neural_used&&e.ask("Inverta: teste").text=="etset");
    CHECK(!e.ask(u8"Reverse: café🙂").neural_used&&e.ask(u8"Reverse: café🙂").text==u8"🙂éfac");
    e.ask("lembrar: pesos ternarios economizam memoria");CHECK(e.ask("buscar memoria: ternarios").text.find("ternarios")!=std::string::npos);
    TernaryMatrix t(2,4);t.set_scale(0,2);t.set_scale(1,.5f);t.set(0,0,1);t.set(0,1,-1);t.set(0,3,1);t.set(1,0,-1);t.set(1,2,1);std::vector<float>x{1,2,3,4};auto y=t.matvec(x);CHECK(std::fabs(y[0]-6.0f)<1e-5f);CHECK(std::fabs(y[1]-1.0f)<1e-5f);CHECK(t.packed_bytes()==2);
    auto m=make_demo_edge_model(16,32);CHECK(m.valid());CHECK(m.compression_ratio_vs_fp32()>1.0);const std::string p="test_demo.edge";m.save(p);auto m2=EdgeModel::load(p);CHECK(m2.valid());CHECK(m2.parameter_count()==m.parameter_count());
    Engine n(Mode::Eco,":memory:",std::make_shared<TernaryBackend>(m2));auto r=n.ask("teste do backend neural");CHECK(r.neural_used);CHECK(r.loops_used>=1);CHECK(!r.text.empty());std::remove(p.c_str());
    std::cout<<"all tests passed\n";
    return 0;
    } catch(const std::exception& error) {
        std::cerr<<"edgeai_tests failure: "<<error.what()<<"\n";
        return 1;
    }
}
