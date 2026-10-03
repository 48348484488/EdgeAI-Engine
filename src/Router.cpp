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
static bool natural_sum(const std::string& raw,const std::string& low,
                        const std::string& prefix,const std::string& separator,
                        std::string& expression){
    if(low.rfind(prefix,0)!=0)return false;
    std::string tail=trim(raw.substr(prefix.size()));
    if(!tail.empty()&&tail.back()=='?')tail=trim(tail.substr(0,tail.size()-1));
    std::string low_tail=lower_ascii(tail);
    auto at=low_tail.find(separator);
    if(at==std::string::npos)return false;
    std::string left=trim(tail.substr(0,at)),right=trim(tail.substr(at+separator.size()));
    if(!mathish(left)||!mathish(right))return false;
    expression="("+left+")+("+right+")";
    return true;
}
Route route(const std::string& text){
    std::string raw=trim(text), low=lower_ascii(raw);
    for(const std::string p:{"buscar codigo:","buscar código:","/code "}) if(low.rfind(p,0)==0) return {RouteKind::CodeSearch,trim(raw.substr(p.size())),1.0};
    const std::string remember="lembrar: ";
    if(low.rfind(remember,0)==0) return {RouteKind::MemoryAdd, trim(raw.substr(remember.size())),1.0};
    const std::string search1="buscar memoria: ", search2="buscar memória: ";
    if(low.rfind(search1,0)==0) return {RouteKind::MemorySearch,trim(raw.substr(search1.size())),1.0};
    if(low.rfind(search2,0)==0) return {RouteKind::MemorySearch,trim(raw.substr(search2.size())),1.0};
    std::string expr=raw;
    const char* prefixes[]={"calcule ","calcular ","calculate ","compute ","what is ","quanto e ","quanto é ","add:","some:"};
    for(auto p:prefixes){ std::string lp=p; if(low.rfind(lp,0)==0){ expr=trim(raw.substr(lp.size())); break; } }
    if(!expr.empty()&&expr.back()=='?')expr=trim(expr.substr(0,expr.size()-1));
    std::string natural;
    if(natural_sum(raw,low,"what is the sum of "," and ",natural) ||
       natural_sum(raw,low,"quanto vale a soma de "," e ",natural))
        return {RouteKind::Calculator,natural,0.999};
    if(mathish(expr)) return {RouteKind::Calculator,expr,0.999};

    const char* copy_prefixes[]={"copy exactly: ","copie exatamente: ","repeat exactly: ","repita exatamente: ","repeat unchanged: ","repita sem alterar: "};
    for(auto p:copy_prefixes){
        std::string lp=p;
        if(low.rfind(lp,0)==0){
            std::string payload=trim(raw.substr(lp.size()));
            if(!payload.empty()) return {RouteKind::TextCopy,payload,1.0};
        }
    }

    const char* upper_prefixes[]={"uppercase: ","maiusculas: ","maiúsculas: ","convert to uppercase: ","convert to capital letters: ","converta para maiusculas: ","converta para maiúsculas: "};
    for(auto p:upper_prefixes){
        std::string lp=p;
        if(low.rfind(lp,0)==0){
            std::string payload=trim(raw.substr(lp.size()));
            if(!payload.empty()) return {RouteKind::TextUppercase,payload,1.0};
        }
    }

    const char* reverse_prefixes[]={"reverse: ","inverta: ","reverse exactly: ","inverta exatamente: "};
    for(auto p:reverse_prefixes){
        std::string lp=p;
        if(low.rfind(lp,0)==0){
            std::string payload=trim(raw.substr(lp.size()));
            if(!payload.empty()) return {RouteKind::TextReverse,payload,1.0};
        }
    }

    const char* expression_prefixes[]={"expression for x ","expressao para x ","expressão para x ","return only x ","retorne apenas x ","return only the python expression x ","retorne apenas a expressao python x ","retorne apenas a expressão python x "};
    for(auto p:expression_prefixes){
        std::string lp=p;
        if(low.rfind(lp,0)==0){
            std::string tail=trim(raw.substr(lp.size()));
            while(!tail.empty()&&(tail.back()==':'||tail.back()=='.'||tail.back()=='?'))tail=trim(tail.substr(0,tail.size()-1));
            if(tail.size()>=2 && std::string("+-*").find(tail[0])!=std::string::npos){
                std::string rhs=trim(tail.substr(1));
                bool digits=!rhs.empty()&&std::all_of(rhs.begin(),rhs.end(),[](unsigned char c){return std::isdigit(c);});
                if(digits) return {RouteKind::SymbolicExpression,std::string("x")+tail[0]+rhs,1.0};
            }
        }
    }

    return {RouteKind::Neural,raw,0.5};
}
}
