#pragma once
#include "as5600_i2c_reader.h"

namespace encdiag {
// STM32U585 ISR masks; verified against the pinned CMSIS header in selftest.
constexpr uint32_t TXIS=1U<<1, RXNE=1U<<2, NACKF=1U<<4, STOPF=1U<<5;
constexpr uint32_t TC=1U<<6, BERR=1U<<8, ARLO=1U<<9, OVR=1U<<10, BUSY=1U<<15;
constexpr Cause BUS_ERROR=static_cast<Cause>(8), ARBITRATION=static_cast<Cause>(9);
constexpr Cause OVERRUN=static_cast<Cause>(10), BUS_BUSY=static_cast<Cause>(11);
struct PollResult {
  Result transfer;
  uint32_t error_isr=0, final_isr=0;
  bool controller_reset=false;
};

// Sole owner of this peripheral. IRQs/control remain runnable; no bus-clear
// clocks, OTP/config writes, retransmission, or invalid samples as valid data.
template<class Io> class PollReader {
 public:
  explicit PollReader(Io &io):io_(io) {}
  PollResult read(uint8_t bytes[3]) {
    r_=PollResult{}; begin_=io_.now_us();
    for(unsigned i=0;i<3;++i) bytes[i]=0;
    r_.transfer.stage=BUS_IDLE;
    uint32_t isr=io_.status();
    if ((isr&BUSY) || !io_.lines_high()) fail(BUS_BUSY,isr);
    else {
      io_.clear(); io_.begin_write();
      if (wait(TXIS,ADDRESS_WRITE)) {
        io_.write_data(0x0b);
        if (wait(TC,REGISTER)) {
          io_.begin_read();
          for(unsigned i=0;i<3;++i) {
            if (!wait(RXNE,i==0 ? ADDRESS_READ : static_cast<Stage>(DATA0+i))) break;
            bytes[i]=io_.read_data();
          }
          if (r_.transfer.cause==NONE && wait(STOPF,STOP)) io_.clear();
        }
      }
    }
    r_.final_isr=io_.status();
    if (r_.transfer.cause!=NONE) {
      // Abort only our peripheral. Do not clock or claim to repair a slave.
      // Preserves the ISR cause before reset, and never retries this sample.
      io_.reset(); r_.controller_reset=true;
      for(unsigned i=0;i<3;++i) bytes[i]=0;
    } else r_.transfer.stage=OK;
    r_.transfer.duration_us=uint32_t(io_.now_us()-begin_);
    return r_;
  }
 private:
  bool fail(Cause cause,uint32_t isr) {
    r_.transfer.cause=cause; r_.error_isr=isr; return false;
  }
  bool wait(uint32_t mask,Stage stage) {
    r_.transfer.stage=stage;
    for (;;) {
      uint32_t isr=io_.status();
      // Errors have precedence over a simultaneously asserted ready flag.
      if(isr&ARLO) return fail(ARBITRATION,isr);
      if(isr&BERR) return fail(BUS_ERROR,isr);
      if(isr&OVR) return fail(OVERRUN,isr);
      if(isr&NACKF) return fail(NACK,isr);
      if(uint32_t(io_.now_us()-begin_)>=3000) return fail(DEADLINE,isr);
      if(isr&mask) return true;
      io_.wait_step();
    }
  }
  Io &io_; PollResult r_; uint32_t begin_=0;
};
} // namespace encdiag
