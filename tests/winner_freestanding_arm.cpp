// Freestanding ARM32 Linux EABI winner differential harness. No libc, no GCC.
extern "C" volatile int board[9];
extern "C" int original_winner(void);
extern "C" int winner(void);

static unsigned int random_state = 0x9e3779b9u;
static unsigned int count_cases = 0;
static unsigned int count_mismatches = 0;

static inline int linux_write(unsigned fd, const char* buffer, unsigned length) {
    register unsigned r0 asm("r0") = fd;
    register const char* r1 asm("r1") = buffer;
    register unsigned r2 asm("r2") = length;
    register unsigned r7 asm("r7") = 4;
    asm volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return static_cast<int>(r0);
}

__attribute__((noreturn)) static inline void linux_exit(unsigned code) {
    register unsigned r0 asm("r0") = code;
    register unsigned r7 asm("r7") = 1;
    asm volatile("svc #0" : : "r"(r0), "r"(r7) : "memory");
    __builtin_unreachable();
}

static void write_literal(const char* text, unsigned size) { (void)linux_write(1, text, size); }
static void write_unsigned(unsigned n) {
    char digits[12];
    unsigned len = 0;
    do {
        digits[len++] = static_cast<char>('0' + n % 10u);
        n /= 10u;
    } while (n);
    for (unsigned k = 0; k < len/2; ++k) {
        char tmp = digits[k];
        digits[k] = digits[len-1-k];
        digits[len-1-k] = tmp;
    }
    (void)linux_write(1, digits, len);
}

static unsigned next_random() {
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

static void check(const int value[9]) {
    for (unsigned j=0; j<9; ++j) board[j]=value[j];
    int expected = original_winner();
    int actual = winner();
    bool ok = expected == actual;
    for (unsigned j=0; j<9; ++j) if (board[j] != value[j]) ok = false;
    ++count_cases;
    if (!ok) ++count_mismatches;
}

extern "C" __attribute__((noreturn)) void _start() {
    int value[9] = {};
    for (unsigned state=0; state<19683u; ++state) {
        unsigned n=state;
        for (unsigned j=0; j<9; ++j) { value[j]=static_cast<int>(n % 3u); n/=3u; }
        check(value);
    }
    static const int edges[4] = {(-2147483647-1), -1, 3, 2147483647};
    for (unsigned edge=0; edge<4; ++edge) {
        for (unsigned j=0; j<9; ++j) value[j]=edges[edge];
        check(value);
    }
    for (unsigned k=0; k<65536u; ++k) {
        for (unsigned j=0; j<9; ++j) value[j]=static_cast<int>(next_random());
        check(value);
    }
    static const char prefix[] = "{\"tested_cases\":";
    static const char middle[] = ",\"mismatches\":";
    static const char passed[] = ",\"passed\":true}\n";
    static const char failed[] = ",\"passed\":false}\n";
    write_literal(prefix, sizeof(prefix)-1);
    write_unsigned(count_cases);
    write_literal(middle, sizeof(middle)-1);
    write_unsigned(count_mismatches);
    if (count_mismatches==0) write_literal(passed, sizeof(passed)-1);
    else write_literal(failed, sizeof(failed)-1);
    linux_exit(count_mismatches ? 1u : 0u);
}
