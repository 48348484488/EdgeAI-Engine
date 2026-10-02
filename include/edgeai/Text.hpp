#pragma once
#include <string>
namespace edgeai {
// Sanitize terminal controls and malformed UTF-8; never use rendered bytes as model feedback.
inline std::string display_utf8(const std::string& raw){std::string out;for(std::size_t i=0;i<raw.size();){unsigned char c=raw[i];if(c<128){out+=c==9||c==10||(c>=32&&c!=127)?char(c):' ';++i;continue;}std::size_t n=c>=0xc2&&c<=0xdf?2:c>=0xe0&&c<=0xef?3:c>=0xf0&&c<=0xf4?4:0;bool ok=n&&i+n<=raw.size();for(std::size_t j=1;ok&&j<n;++j)ok=(static_cast<unsigned char>(raw[i+j])&0xc0)==0x80;
 if(ok&&n>=3){auto b=static_cast<unsigned char>(raw[i+1]);ok=!(c==0xe0&&b<0xa0)&&!(c==0xed&&b>=0xa0)&&!(c==0xf0&&b<0x90)&&!(c==0xf4&&b>=0x90);}if(ok){out.append(raw,i,n);i+=n;}else{out+="\xef\xbf\xbd";++i;}}return out;}
}
