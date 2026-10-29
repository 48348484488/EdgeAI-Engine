// EdgeAI V21: bounded candidate generated from SHA-pinned stripped ARM64 2048 ELF.
// NOT validated against original ARM64/QEMU; host tests cover normal termios calls.
#include <termios.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
static_assert(sizeof(termios) == 60, "unsupported host termios ABI");
static_assert(offsetof(termios, c_lflag) == 12, "unsupported c_lflag offset");
extern "C" int __printf_chk(int, const char*, ...);
namespace edgeai_terminal_4011cc {
static unsigned char flag = 1; // original .data at 0x420080
static termios saved{};        // original .bss at 0x420090
static const unsigned char restore_text[] = {0x1b, 0x5b, 0x3f, 0x32, 0x35, 0x68, 0x1b, 0x5b, 0x6d, 0x00};
}
extern "C" void recovered_4011cc(unsigned mode) {
  using namespace edgeai_terminal_4011cc;
  if ((mode & 1u) != 0u) {
    if ((flag & 1u) == 0u) {
      (void)tcsetattr(0, 0, &saved);
      __printf_chk(2, reinterpret_cast<const char*>(restore_text));
      flag = 1;
    }
  } else if ((flag & 1u) != 0u) {
    termios current; // original does not check tcgetattr errors
    (void)tcgetattr(0, &current);
    std::memcpy(&saved, &current, 60);
    current.c_lflag &= static_cast<tcflag_t>(~0xau);
    (void)tcsetattr(0, 0, &current);
    flag = 0;
  }
}
