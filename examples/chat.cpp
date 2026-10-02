#include "edgeai/Engine.hpp"
#include "edgeai/HybridBackend.hpp"
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){try{
 std::string code_root,model_path,memory_path="edgeai_memory.txt",prompt;bool once=false;edgeai::Mode mode=edgeai::Mode::Balanced;
 for(int i=1;i<argc;++i){std::string a=argv[i];auto value=[&](){if(i+1>=argc)throw std::invalid_argument("missing argument after "+a);return std::string(argv[++i]);};
  if(a=="--mode"){auto v=value();if(v=="eco")mode=edgeai::Mode::Eco;else if(v=="balanced")mode=edgeai::Mode::Balanced;else if(v=="max")mode=edgeai::Mode::Max;else throw std::invalid_argument("mode: eco, balanced or max");}
  else if(a=="--code-root")code_root=value();
  else if(a=="--prompt"){prompt=value();once=true;}else if(a=="--memory")memory_path=value();
  else if(a=="--help"){std::cout<<"edgeai_chat [model.edge] [--mode eco|balanced|max] [--prompt TEXT] [--memory PATH] [--code-root PASTA]\nNo model: deterministic tools + development backend only.\n";return 0;}
  else if(a.rfind("--",0)==0||!model_path.empty())throw std::invalid_argument("unknown/duplicate argument: "+a);else model_path=a;}
 edgeai::BackendPtr backend=model_path.empty()?std::make_shared<edgeai::EchoReasonerBackend>():edgeai::load_backend(model_path);
 edgeai::Engine engine(mode,memory_path,backend);
 if(!code_root.empty())engine.set_code_root(code_root);
 auto answer=[&](const std::string& question){try{auto r=engine.ask(question);std::cout<<r.text<<"\n[neural="<<r.neural_used<<" loops="<<r.loops_used<<" token_score="<<r.confidence<<"]\n";}catch(const std::exception&e){std::cout<<"Erro: "<<e.what()<<"\n";}};
 if(once){auto r=engine.ask(prompt);std::cout<<r.text<<"\n[neural="<<r.neural_used<<" loops="<<r.loops_used<<" token_score="<<r.confidence<<"]\n";return 0;}
 std::cout<<"EdgeAI Engine v0.12 (model formats through EDGEAI8) | "<<engine.hardware().summary()<<" | backend="<<backend->name()<<"\nModelo experimental: nao e um assistente conversacional avancado.\nScore do token nao representa chance de a resposta estar correta.\nDigite 'sair' para fechar.\n";
 std::string s;while(std::cout<<"> "&&std::getline(std::cin,s)){if(s=="sair")break;answer(s);}return 0;
 }catch(const std::exception&e){std::cerr<<"Erro: "<<e.what()<<"\n";return 1;}}
