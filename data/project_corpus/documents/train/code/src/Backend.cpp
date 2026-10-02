#include "edgeai/Backend.hpp"
#include <algorithm>
namespace edgeai {
Response NullBackend::infer(const std::string&, const Budget&){ return {"[nenhum backend neural carregado]",RouteKind::Neural,true,0,0.0}; }
Response EchoReasonerBackend::infer(const std::string& prompt,const Budget& budget){
    // Development backend used only to validate scheduler/backend integration.
    // It deliberately does not pretend to be a trained language model.
    std::size_t loops=std::max<std::size_t>(1,budget.max_loops);
    return {"[backend de desenvolvimento] entrada recebida: "+prompt,RouteKind::Neural,true,loops,0.1};
}
}
