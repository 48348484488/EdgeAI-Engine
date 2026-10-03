#include "edgeai/Engine.hpp"
#include "edgeai/Calculator.hpp"
#include "edgeai/Router.hpp"
#include "edgeai/CodeSearch.hpp"
#include "edgeai/TextTools.hpp"
#include <sstream>
#include <cctype>
namespace edgeai {
Engine::Engine(Mode mode,std::string memory_path,BackendPtr backend):hardware_(detect_hardware()),scheduler_(mode),memory_(std::move(memory_path)),backend_(backend?backend:std::make_shared<NullBackend>()){}
void Engine::set_backend(BackendPtr backend){ backend_=backend?backend:std::make_shared<NullBackend>(); }
void Engine::set_code_root(std::string root){ auto index=std::make_unique<CodeIndex>(root); code_root_=std::move(root); code_index_=std::move(index); }
Response Engine::ask(const std::string& text){
    auto r=route(text); auto budget=scheduler_.budget_for(text);
    if(r.kind==RouteKind::CodeSearch){
        if(code_root_.empty()) return {"Defina --code-root PASTA para buscar codigo.",r.kind,false,0,0.0};
        code_index_->refresh();
        return {format_code_result(code_index_->search(r.payload,budget.max_memory_hits)),r.kind,false,0,0.0};
    }
    if(r.kind==RouteKind::Calculator){
        try { return {format_number(calculate(r.payload)),r.kind,false,0,1.0}; }
        catch(const std::exception& error) { return {std::string("Erro no cálculo: ")+error.what(),r.kind,false,0,0.0}; }
    }
    if(r.kind==RouteKind::TextCopy || r.kind==RouteKind::SymbolicExpression)
        return {r.payload,r.kind,false,0,1.0};
    if(r.kind==RouteKind::TextUppercase){
        std::string out=r.payload;
        for(char& c:out){
            unsigned char u=static_cast<unsigned char>(c);
            if(u>='a'&&u<='z') c=static_cast<char>(u-'a'+'A');
        }
        return {out,r.kind,false,0,1.0};
    }
    if(r.kind==RouteKind::TextReverse)
        return {reverse_utf8_codepoints(r.payload),r.kind,false,0,1.0};
    if(r.kind==RouteKind::MemoryAdd){ memory_.add(r.payload); return {"Memória salva.",r.kind,false,0,1.0}; }
    if(r.kind==RouteKind::MemorySearch){ auto hits=memory_.search(r.payload,budget.max_memory_hits); if(hits.empty()) return {"Nada encontrado.",r.kind,false,0,1.0}; std::ostringstream o; for(std::size_t i=0;i<hits.size();++i){ if(i)o<<'\n'; o<<hits[i]; } return {o.str(),r.kind,false,0,1.0}; }
    auto out=backend_->infer(r.payload,budget); out.route=RouteKind::Neural; out.neural_used=true; return out;
}
}
