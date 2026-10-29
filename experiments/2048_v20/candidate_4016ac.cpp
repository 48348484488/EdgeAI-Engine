// EdgeAI experimental source-blind candidate; NOT ARM64 runtime validated.
#include <cstdlib>
#include <cstdint>
extern "C" int __printf_chk(int, const char*, ...);
extern "C" void recovered_4011cc(unsigned);
extern "C" [[noreturn]] void recovered_4016ac(int) {
  static const unsigned char s0[] = {0x1b, 0x5b, 0x31, 0x3b, 0x33, 0x25, 0x64, 0x6d, 0x00};
  static const unsigned char s1[] = {0x25, 0x2a, 0x73, 0x0a, 0x00};
  static const unsigned char s2[] = {0x54, 0x45, 0x52, 0x4d, 0x49, 0x4e, 0x41, 0x54, 0x45, 0x44, 0x00};
  static const unsigned char s3[] = {0x1b, 0x5b, 0x30, 0x6d, 0x00};
  __printf_chk(2, reinterpret_cast<const char*>(s0), 1);
  __printf_chk(2, reinterpret_cast<const char*>(s1), 26, reinterpret_cast<const char*>(s2));
  __printf_chk(2, reinterpret_cast<const char*>(s3));
  recovered_4011cc(1u);
  std::exit(0);
}
