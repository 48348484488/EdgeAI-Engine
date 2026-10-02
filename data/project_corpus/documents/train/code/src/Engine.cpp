#include "edgeai/Engine.hpp"
#include "edgeai/Calculator.hpp"
#include "edgeai/Router.hpp"
#include <sstream>
namespace edgeai {
Engine::Engine(Mode mode,std::string memory_path,BackendPtr backend):hardware_(detect_hardware()),scheduler_(mode),memory_(std::move(memory_path)),backend_(backend?backend:std::make_shared<NullBackend>()){}
void Engine::set_backend(BackendPtr backend){ backend_=backend?backend:std::make_shared<NullBackend>(); }
Response Engine::ask(const std::string& text){
    auto r=route(text); auto budget=scheduler_.budget_for(text);
    if(r.kind==RouteKind::Calculator){
        try { return {format_number(calculate(r.payload)),r.kind,false,0,1.0}; }
        catch(const std::exception& error) { return {std::string("Erro no cálculo: ")+error.what(),r.kind,false,0,0.0}; }
    }
    if(r.kind==RouteKind::MemoryAdd){ memory_.add(r.payload); return {"Memória salva.",r.kind,false,0,1.0}; }
    if(r.kind==RouteKind::MemorySearch){ auto hits=memory_.search(r.payload,budget.max_memory_hits); if(hits.empty()) return {"Nada encontrado.",r.kind,false,0,1.0}; std::ostringstream o; for(std::size_t i=0;i<hits.size();++i){ if(i)o<<'\n'; o<<hits[i]; } return {o.str(),r.kind,false,0,1.0}; }
    auto out=backend_->infer(r.payload,budget); out.route=RouteKind::Neural; out.neural_used=true; return out;
}
}
