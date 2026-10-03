#pragma once
#include <cstddef>
#include <string>
namespace edgeai {
enum class Mode { Eco, Balanced, Max };
enum class RouteKind { Calculator, MemoryAdd, MemorySearch, Neural, CodeSearch, TextCopy, TextUppercase, TextReverse, SymbolicExpression };
inline const char* route_name(RouteKind kind){
    switch(kind){
        case RouteKind::Calculator:return "calculator";
        case RouteKind::MemoryAdd:return "memory_add";
        case RouteKind::MemorySearch:return "memory_search";
        case RouteKind::Neural:return "neural";
        case RouteKind::CodeSearch:return "code_search";
        case RouteKind::TextCopy:return "text_copy";
        case RouteKind::TextUppercase:return "text_uppercase";
        case RouteKind::TextReverse:return "text_reverse";
        case RouteKind::SymbolicExpression:return "symbolic_expression";
    }
    return "unknown";
}
struct Route { RouteKind kind; std::string payload; double confidence; };
struct Budget { std::size_t max_loops; std::size_t max_context_chars; std::size_t max_memory_hits; unsigned threads; };
struct Response { std::string text; RouteKind route; bool neural_used; std::size_t loops_used; double confidence; };
}
