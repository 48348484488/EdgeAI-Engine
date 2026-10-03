#include "edgeai/TextTools.hpp"
#include <algorithm>
#include <stdexcept>
#include <string>
#include <vector>
namespace edgeai {
std::string reverse_utf8_codepoints(const std::string& text){
    std::vector<std::string> codepoints;
    for(std::size_t i=0;i<text.size();){
        const unsigned char c=static_cast<unsigned char>(text[i]);
        std::size_t n=0;
        if(c<0x80)n=1;
        else if(c>=0xc2&&c<=0xdf)n=2;
        else if(c>=0xe0&&c<=0xef)n=3;
        else if(c>=0xf0&&c<=0xf4)n=4;
        else throw std::invalid_argument("invalid UTF-8 lead byte");
        if(i+n>text.size())throw std::invalid_argument("truncated UTF-8");
        for(std::size_t j=1;j<n;++j)
            if((static_cast<unsigned char>(text[i+j])&0xc0)!=0x80)
                throw std::invalid_argument("invalid UTF-8 continuation");
        if(n>=3){
            const unsigned char b=static_cast<unsigned char>(text[i+1]);
            if((c==0xe0&&b<0xa0)||(c==0xed&&b>=0xa0)||
               (c==0xf0&&b<0x90)||(c==0xf4&&b>=0x90))
                throw std::invalid_argument("invalid UTF-8 scalar");
        }
        codepoints.emplace_back(text.substr(i,n));
        i+=n;
    }
    std::reverse(codepoints.begin(),codepoints.end());
    std::string out;
    out.reserve(text.size());
    for(const auto& cp:codepoints)out+=cp;
    return out;
}
}
