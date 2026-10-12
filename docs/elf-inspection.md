# Experimental ELF inspection

EdgeAI now includes a dependency-free, read-only Python tool for collecting
**named function symbols** from ELF executables and shared libraries.

Usage:

```bash
python3 tools/elf_inspect.py /path/to/libGame.so --max-functions 100
python3 -m unittest discover -s tests -p test_elf_inspect.py -v
```

JSON results contain architecture identifiers, ELF bitness and endianness,
entry point, SHA-256, function symbol names, addresses, sizes, symbol-table
source, and a truncation flag. Input is capped at 128 MiB.

**Scope:** This is not decompilation. It only inventories defined, named
STT_FUNC symbols from ELF symbol tables. Stripped functions are not recovered.
ELF symbol addresses may need relocation at runtime; ARM Thumb function
symbol values may encode the Thumb state bit. Extended section numbering is
not supported. No inspected code is executed. Process untrusted files in a
restricted environment.

Next targets: executable-section discovery, ARM/Thumb instruction decoding,
control-flow graph extraction, and behavior-validation tests. Each milestone
must have real-binary and synthetic-fixture regression evidence.

This experimental utility is separate from the low-resource C++ runtime and
does not establish neural model quality.
