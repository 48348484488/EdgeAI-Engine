// EdgeAI V23: host-side semantic candidate for the 2048 main loop 0x401758-0x401988.
// Transcribed from the SHA-pinned AArch64 disassembly, NOT automatically lifted and
// NOT yet validated against original ARM64 execution. External calls are injected.
#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <stdexcept>

namespace edgeai_2048_v23 {
using Board = std::array<std::uint8_t, 64>;  // Four 16-byte q-register lanes.
struct Hooks {
    std::function<void()> startup;
    std::function<void(Board&)> reset_board;
    std::function<void(std::uint32_t)> print_score;
    std::function<void(Board&)> render_board;
    std::function<void()> render_finish;
    std::function<int()> read_key;
    // The four functions at 0x400e0c/0x400e68/0x400f08/0x400eb8.
    std::array<std::function<std::uint32_t(Board&, std::uint32_t&)>, 4> move;
    std::function<void(Board&)> spawn_tile;
    std::function<std::uint32_t(Board&)> check_first;
    std::function<std::uint32_t(Board&)> check_second;
    std::function<void()> on_first_false;
    std::function<void()> on_second_true;
    std::function<void(unsigned)> terminal_mode;
};

// max_reads is a host test guard only; original getchar loop is unbounded.
// Returns 0 on a binary-observed exit, 2 when test budget is exhausted.
int candidate_401758(const Hooks& h, std::size_t max_reads) {
    if (!h.startup || !h.reset_board || !h.print_score || !h.render_board ||
        !h.render_finish || !h.read_key || !h.spawn_tile || !h.check_first ||
        !h.check_second || !h.on_first_false || !h.on_second_true ||
        !h.terminal_mode) throw std::invalid_argument("missing hook");
    for (const auto& f : h.move) if (!f) throw std::invalid_argument("missing move hook");
    Board board{}, scratch{}, backup{};
    std::uint32_t score = 0;
    h.startup();
    h.reset_board(board);
    backup = board;  // 0x401798..0x4017a4: 64-byte SIMD copy.
    h.print_score(score);
    h.render_board(board);
    h.render_finish();
    for (std::size_t reads = 0; reads < max_reads; ++reads) {
        const auto key = static_cast<std::uint32_t>(h.read_key()) & 0xffu;
        if ((key & 0xbfu) == 27u) continue;  // 0x401858..0x401864
        if ((key & 0xdfu) == 81u) { h.terminal_mode(1); return 0; }
        if ((key & 0xdfu) == 82u) {  // R/r: 0x4017cc
            score = 0;
            h.reset_board(board);
            h.print_score(score);
            h.print_score(score);
            h.render_board(board);
            h.render_finish();
            continue;
        }
        if (key == 98u) {  // lowercase b only: 0x4017f8
            board = backup;
            h.print_score(score);
            h.render_board(board);
            h.render_finish();
            continue;
        }
        scratch = board;  // 0x401888..0x401894
        std::uint32_t changed = 0;
        switch (key) {
            case 65u: changed = h.move[0](board, score); break; // 0x400e0c
            case 66u: changed = h.move[1](board, score); break; // 0x400e68
            case 67u: changed = h.move[2](board, score); break; // 0x400f08
            case 68u: changed = h.move[3](board, score); break; // 0x400eb8
            default: continue;
        }
        if (!(changed & 1u)) continue;
        backup = scratch;  // 0x4018e0..0x4018ec: 64-byte SIMD copy.
        h.spawn_tile(board);
        h.print_score(score);
        h.render_board(board);
        h.render_finish();
        if (h.check_first(board) & 1u) {
            if (!(h.check_second(board) & 1u)) continue;
            h.on_second_true();
        } else {
            h.on_first_false();
        }
        h.render_board(board);
        h.render_finish();
        h.terminal_mode(1);
        return 0;
    }
    return 2;
}
}  // namespace edgeai_2048_v23
