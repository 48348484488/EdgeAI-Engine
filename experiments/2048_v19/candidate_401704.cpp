// EdgeAI: unvalidated source-blind C++ candidate; bounded AArch64 startup chain.
#include <cstdint>
#include <ctime>
#include <cstdlib>
#include <csignal>
extern "C" int __printf_chk(int, const char*, ...);
extern "C" void recovered_4011cc(unsigned);
extern "C" void recovered_4016ac(int);
extern "C" void recovered_401704() {
  static const unsigned char literal_0[] = {0x1b, 0x5b, 0x48, 0x1b, 0x5b, 0x4a, 0x00};
  __printf_chk(2, reinterpret_cast<const char*>(literal_0));
  static const unsigned char literal_1[] = {0x1b, 0x5b, 0x3f, 0x32, 0x35, 0x6c, 0x1b, 0x5b, 0x32, 0x4a, 0x00};
  __printf_chk(2, reinterpret_cast<const char*>(literal_1));
  const std::time_t seed = std::time(nullptr);
  std::srand(static_cast<unsigned>(seed));
  recovered_4011cc(0u);
  std::signal(2, recovered_4016ac);
}
