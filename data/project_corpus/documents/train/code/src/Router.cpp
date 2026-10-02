#include "edgeai/Router.hpp"
#include <algorithm>
#include <cctype>
namespace edgeai {
static std::string trim(std::string s) {
    auto ns=[](unsigned char c){return !std::isspace(c);};
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), ns));
    s.erase(std::find_if(s.rbegin(), s.rend(), ns).base(), s.end()); return s;
}
static std::string lower_ascii(std::string s){ for(char& c:s) if(c>='A'&&c<='Z') c=char(c+32); return s; }
static bool mathish(const std::string& s){
    bool digit=false;
    for(unsigned char c:s){
        if(std::isdigit(c)){digit=true; continue;}
        if(std::isspace(c) || std::string("+-*/().,%^").find(char(c))!=std::string::npos) continue;
        return false;
    }
    return digit;
}
Route route(const std::string& text){
    std::string raw=trim(text), low=lower_ascii(raw);
    const std::string remember="lembrar: ";
    if(low.rfind(remember,0)==0) return {RouteKind::MemoryAdd, trim(raw.substr(remember.size())),1.0};
    const std::string search1="buscar memoria: ", search2="buscar memória: ";
    if(low.rfind(search1,0)==0) return {RouteKind::MemorySearch,trim(raw.substr(search1.size())),1.0};
    if(low.rfind(search2,0)==0) return {RouteKind::MemorySearch,trim(raw.substr(search2.size())),1.0};
    std::string expr=raw;
    const char* prefixes[]={"calcule ","calcular ","compute ","quanto e ","quanto é "};
    for(auto p:prefixes){ std::string lp=p; if(low.rfind(lp,0)==0){ expr=trim(raw.substr(lp.size())); break; } }
    if(mathish(expr)) return {RouteKind::Calculator,expr,0.999};
    return {RouteKind::Neural,raw,0.5};
}
}
