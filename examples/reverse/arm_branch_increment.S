.syntax unified
.arm
.text
.global increment_guard
.type increment_guard, %function
increment_guard:
    add r1, r0, #1
    cmp r1, #8
    bne .Lreject
    mov r0, #3
    bx lr
.Lreject:
    mov r0, #17
    bx lr
.size increment_guard, .-increment_guard
.global start
.type start, %function
start:
    mov r0, #7
    b increment_guard
.size start, .-start
