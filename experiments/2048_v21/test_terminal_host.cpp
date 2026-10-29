// Host-only regression test for the V21 candidate; not original ARM64 parity.
#include <termios.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
extern "C" void recovered_4011cc(unsigned);
static int gets=0, sets=0, prints=0;
static termios original{};
static termios applied[3]{};
extern "C" int tcgetattr(int fd, termios *t) {
  if (fd!=0) std::abort();
  ++gets; *t=original; return 0;
}
extern "C" int tcsetattr(int fd, int act, const termios *t) {
  if (fd!=0 || act!=0 || sets>=3) std::abort();
  applied[sets++]=*t; return 0;
}
extern "C" int __printf_chk(int flag,const char *fmt,...) {
  if(flag!=2 || std::strcmp(fmt,"\x1b[?25h\x1b[m")) std::abort();
  ++prints; return 0;
}
static void require(bool b){if(!b)std::abort();}
int main() {
  std::memset(&original,0xA5,sizeof(original));
  original.c_lflag=15;
  recovered_4011cc(1);
  require(gets==0&&sets==0&&prints==0);
  recovered_4011cc(0);
  require(gets==1&&sets==1&&prints==0&&applied[0].c_lflag==5);
  recovered_4011cc(0);
  require(gets==1&&sets==1);
  recovered_4011cc(3);
  require(gets==1&&sets==2&&prints==1);
  require(std::memcmp(&applied[1],&original,sizeof(termios))==0);
  recovered_4011cc(1);
  require(gets==1&&sets==2&&prints==1);
  recovered_4011cc(2);
  require(gets==2&&sets==3&&prints==1&&applied[2].c_lflag==5);
  std::puts("terminal transitions OK");
}
