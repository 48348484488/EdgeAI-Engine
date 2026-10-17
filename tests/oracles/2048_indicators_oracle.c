/* Test oracle constructed AFTER binary-only code generation, not used by the lifter.
 * Upstream: Frost-Phoenix/2048-cli src/draw.c (MIT)
 * Commit: 53f4da8249cbe9bce17e0daefbd7903f4a4684be
 * Copyright (c) 2023 Frost-Phoenix. SPDX-License-Identifier: MIT
 * Full license: see 2048_MIT_LICENSE.txt in this directory.
 */
#include <stdio.h>
#define SET_TEXT_COLOR(X) printf("\033[1;3%dm", X)
#define MOVE_CURSOR(R,C) printf("\033[%d;%dH", R,C)
#define RESET_FORMATING printf("\033[0m")
typedef enum {BLACK,RED,GREEN,YELLOW,BLUE,MAGENTA,CYAN,WHITE} Color;
void print_indicators(void) {
    printf("%*s",25,"↑\n");
    printf("%*s",30,"← ↓ →");
    MOVE_CURSOR(24,2);
    SET_TEXT_COLOR(CYAN);
    printf("B");
    RESET_FORMATING;
    printf("ack");
    MOVE_CURSOR(25,2);
    SET_TEXT_COLOR(GREEN);
    printf("R");
    RESET_FORMATING;
    printf("estart");
    MOVE_CURSOR(25,39);
    SET_TEXT_COLOR(RED);
    printf("Q");
    RESET_FORMATING;
    printf("uit");
    printf("\n");
}
int main(void){print_indicators();return 0;}
