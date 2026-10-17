/* Extracted verbatim from Frost-Phoenix/2048-cli src/board.c @
 * 53f4da8249cbe9bce17e0daefbd7903f4a4684be (MIT), only after
 * emitting the stripped ARM64 C++ candidate files.
 */
#include <stdint.h>
#include <stdlib.h>
typedef uint32_t u32;
#define SIZE 4
void board_add_piece(u32 board[SIZE][SIZE]);
void board_init(u32 board[SIZE][SIZE]) {
    for (u32 i = 0; i < SIZE; i++) {
        for (u32 j = 0; j < SIZE; j++) {
            board[i][j] = 0;
        }
    }
    board_add_piece(board);
    board_add_piece(board);
}
void board_add_piece(u32 board[SIZE][SIZE]) {
    u32 len = SIZE * SIZE;
    u32 valid_cells[len][2];
    u32 k = 0;
    for (u32 i = 0; i < SIZE; i++) {
        for (u32 j = 0; j < SIZE; j++) {
            if (board[i][j] != 0) continue;
            valid_cells[k][0] = i;
            valid_cells[k][1] = j;
            k++;
        }
    }
    u32 cell = rand() % k;
    u32 r = valid_cells[cell][0];
    u32 c = valid_cells[cell][1];
    board[r][c] = (1 + (rand() % 10 == 0)) * 2;
}
