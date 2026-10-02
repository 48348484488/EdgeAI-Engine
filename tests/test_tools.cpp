#include "edgeai/Engine.hpp"
#include "edgeai/Calculator.hpp"
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
int main(){using namespace edgeai;CHECK(calculate("-2^2")==-4);CHECK(calculate("2^3^2")==512);CHECK(std::abs(calculate("2^-3")-.125)<1e-9);bool caught=false;try{calculate("4 % 0");}catch(const std::exception&){caught=true;}CHECK(caught);
 Engine e(Mode::Eco,":memory:",std::make_shared<EchoReasonerBackend>());auto r=e.ask("1 / 0");CHECK(!r.neural_used);CHECK(r.text.find("Erro")!=std::string::npos);
 caught=false;try{LocalMemory memory("/__edgeai_missing_directory__/file.txt");memory.add("teste");}catch(const std::exception&){caught=true;}CHECK(caught);
 std::cout<<"deterministic tool errors/precedence checks passed\n";}
