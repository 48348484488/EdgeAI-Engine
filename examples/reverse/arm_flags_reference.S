.syntax unified
.arm
.text

.global sub_flag_guard
.type sub_flag_guard, %function
sub_flag_guard:
    mov r1, #1
    subs r1, r1, #1
    beq .Lsub_ok
    mov r0, #7
    bx lr
.Lsub_ok:
    mov r0, #3
    bx lr
.size sub_flag_guard, .-sub_flag_guard

.global unsigned_flag_guard
.type unsigned_flag_guard, %function
unsigned_flag_guard:
    mov r1, #9
    cmp r1, #8
    bhi .Lgreater
    mov r0, #0
    bx lr
.Lgreater:
    mov r0, #1
    bx lr
.size unsigned_flag_guard, .-unsigned_flag_guard

.global shifted_flag_guard
.type shifted_flag_guard, %function
shifted_flag_guard:
    mov r1, #8
    lsrs r1, r1, #1
    beq .Lshift_zero
    mov r0, #4
    bx lr
.Lshift_zero:
    mov r0, #0
    bx lr
.size shifted_flag_guard, .-shifted_flag_guard

.global start
.type start, %function
start:
    bl sub_flag_guard
    bl unsigned_flag_guard
    b shifted_flag_guard
.size start, .-start
