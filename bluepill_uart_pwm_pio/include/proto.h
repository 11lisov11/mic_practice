#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FRAME_LEN 32

#define CMD_HDR0 0xAA
#define CMD_HDR1 0x55
#define RSP_HDR0 0x55
#define RSP_HDR1 0xAA

#define CMD_OFF_HDR0 0
#define CMD_OFF_HDR1 1
#define CMD_OFF_VER  2
#define CMD_OFF_FLAGS 3
#define CMD_OFF_MODE 4
#define CMD_OFF_SEQ 5
#define CMD_OFF_DU 6
#define CMD_OFF_DV 8
#define CMD_OFF_DW 10
#define CMD_OFF_RESERVED 12
#define CMD_OFF_EXT_FLAGS 14
#define CMD_OFF_EXT_DUTY_LO 15
#define CMD_OFF_EXT_DUTY_HI 16
#define CMD_OFF_EXT_RSV0 17
#define CMD_OFF_EXT_RSV1 18
#define CMD_OFF_EXT_RSV2 19
#define CMD_OFF_EXT_RSV3 20
#define CMD_OFF_EXT_RSV4 21
#define CMD_OFF_EXT_RSV5 22
#define CMD_OFF_EXT_RSV6 23
#define CMD_OFF_EXT_RSV7 24
#define CMD_OFF_EXT_RSV8 25
#define CMD_OFF_EXT_RSV9 26
#define CMD_OFF_EXT_RSV10 27
#define CMD_OFF_EXT_RSV11 28
#define CMD_OFF_EXT_RSV12 29
#define CMD_OFF_EXT_RSV13 30
#define CMD_OFF_CRC 31

// Optional service PWM extension. These bytes were reserved in protocol v0x02;
// older receivers ignore them, newer Blue Pill firmware uses them for the
// 3-pin cooling fan driver on PB3.
#define CMD_OFF_FAN_DUTY_LO CMD_OFF_EXT_RSV0
#define CMD_OFF_FAN_DUTY_HI CMD_OFF_EXT_RSV1

#define FLAG_ENABLE      0x01
#define FLAG_ESTOP       0x02
#define FLAG_DIAG_PWM    0x04
#define FLAG_CLEAR_FAULT 0x08
#define FLAG_VECTOR_ROTATE 0x10

#define MODE_OFF    0
#define MODE_DIAG   1
#define MODE_DUTY   2
#define MODE_SCALAR 3
#define MODE_VECTOR 4
#define MODE_FOC    5

// Extended flags (bytes 14..18)
// Reserved for protocol v0x02 compatibility. It has no GPIO assignment.
#define EXT_RESERVED_0  0x01
#define EXT_PFC_SYNC    0x02
#define EXT_BRAKE_PWM   0x04
#define EXT_PRECHARGE_RELAY 0x08

#define RSP_OFF_HDR0 0
#define RSP_OFF_HDR1 1
#define RSP_OFF_VER  2
#define RSP_OFF_STATUS 3
#define RSP_OFF_SEQ 4
#define RSP_OFF_GOOD_LO 5
#define RSP_OFF_GOOD_HI 6
#define RSP_OFF_BAD_LO 7
#define RSP_OFF_BAD_HI 8
#define RSP_OFF_FAULT 9
#define RSP_OFF_LAST_MODE 10
#define RSP_OFF_RESERVED 11
#define RSP_OFF_EXT_FLAGS 14
#define RSP_OFF_EXT_DUTY_LO 15
#define RSP_OFF_EXT_DUTY_HI 16
#define RSP_OFF_VBUS_RAW_LO 17
#define RSP_OFF_VBUS_RAW_HI 18
#define RSP_OFF_TEMP_RAW_LO 19
#define RSP_OFF_TEMP_RAW_HI 20
#define RSP_OFF_TEMP_FLAGS 21
#define RSP_OFF_EXT_RSV0 22
#define RSP_OFF_PHASE_A_RAW_LO 23
#define RSP_OFF_PHASE_A_RAW_HI 24
#define RSP_OFF_PHASE_B_RAW_LO 25
#define RSP_OFF_PHASE_B_RAW_HI 26
#define RSP_OFF_PHASE_C_RAW_LO 27
#define RSP_OFF_PHASE_C_RAW_HI 28
#define RSP_OFF_PHASE_FLAGS 29
#define RSP_OFF_EXT_RSV1 30
#define RSP_OFF_CRC 31

// Compact fan telemetry in previously reserved reply bytes.
// duty_q8: 0..255 mirrors the applied PB3 PWM duty.
// tach_x30: fan rpm / 30, saturated to 255 (0 means no tach pulses seen).
#define RSP_OFF_FAN_DUTY_Q8 RSP_OFF_EXT_RSV0
#define RSP_OFF_FAN_TACH_X30 RSP_OFF_EXT_RSV1

#define TEMP_FLAG_VALID 0x01
#define TEMP_FLAG_FAULT 0x02

#define PHASE_FLAG_VALID 0x01
#define PHASE_FLAG_C_VIRTUAL 0x02

#define STATUS_LINK_OK     0x01
#define STATUS_ENABLED     0x02
#define STATUS_ESTOP       0x04
#define STATUS_FAULT       0x08
#define STATUS_TIMEOUT     0x10
#define STATUS_PWM_ACTIVE  0x20

#define FAULT_OK        0
#define FAULT_ESTOP     1
#define FAULT_TIMEOUT   2
#define FAULT_BAD_CRC   3
#define FAULT_BAD_HDR   4
#define FAULT_INTERNAL  5
#define FAULT_OVERTEMP  6

uint8_t proto_crc_xor(const uint8_t *frame);
bool proto_cmd_crc_ok(const uint8_t *frame);
