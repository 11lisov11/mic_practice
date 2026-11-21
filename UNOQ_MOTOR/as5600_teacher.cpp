// Current-only build: no Wire/I2C worker or GPIO recovery.
#include "as5600_teacher.h"
void as5600_teacher_begin() {}
As5600Sample as5600_teacher_snapshot(uint32_t) { return As5600Sample{}; }
bool as5600_diag_select(uint8_t) { return false; }
bool as5600_diag_ready() { return false; }
