#pragma once
#include "as5600_i2c_reader.h"
namespace encdiag {
constexpr uint32_t TXIS=1U<<1,RXNE=1U<<2,NACKF=1U<<4,STOPF=1U<<5;
constexpr uint32_t TC=1U<<6,BERR=1U<<8,ARLO=1U<<9,OVR=1U<<10,BUSY=1U<<15;
constexpr Cause BUS_ERROR=static_cast<Cause>(8),ARBITRATION=static_cast<Cause>(9);
constexpr Cause OVERRUN=static_cast<Cause>(10),BUS_BUSY=static_cast<Cause>(11);
struct PollResult {
  Result transfer;uint32_t error_isr=0,final_isr=0,post_isr=0,error_cr2=0,error_lines=0;
  uint32_t berr_events=0,first_berr_isr=0,first_berr_cr2=0,first_berr_lines=0;bool controller_reset=false,graceful_cleanup=false;
};
template<class Io> class PollReader {
 public:
  explicit PollReader(Io &io):io_(io){}
  PollResult read(uint8_t bytes[3]) {
    r_=PollResult{};begin_=io_.now_us();for(unsigned i=0;i<3;++i)bytes[i]=0;
    r_.transfer.stage=BUS_IDLE;
    const uint32_t first=io_.status();
    if((first&BUSY)||!io_.lines_high())fail(BUS_BUSY,first);
    else {
      io_.clear();io_.begin_write();
      if(wait(TXIS,ADDRESS_WRITE)) {
        io_.write_data(0x0b);
        if(wait(TC,REGISTER)) {
          io_.begin_read();
          for(unsigned i=0;i<3;++i){
            if(!wait(RXNE,i==0?ADDRESS_READ:static_cast<Stage>(DATA0+i)))break;
            bytes[i]=io_.read_data();
          }
          if(r_.transfer.cause==NONE&&wait(STOPF,STOP)){io_.clear();io_.quiesce();}
        }
      }
    }
    r_.final_isr=io_.status();
    if(r_.transfer.cause!=NONE){cleanup();for(unsigned i=0;i<3;++i)bytes[i]=0;}
    else r_.transfer.stage=OK;
    r_.post_isr=io_.status();r_.transfer.duration_us=uint32_t(io_.now_us()-begin_);
    return r_;
  }
 private:
  bool fail(Cause c,uint32_t s){r_.transfer.cause=c;r_.error_isr=s;r_.error_cr2=io_.control();r_.error_lines=io_.line_bits();return false;}
  bool expired(){return uint32_t(io_.now_us()-begin_)>=3000;}
  bool wait(uint32_t mask,Stage stage){
    r_.transfer.stage=stage;
    for(;;){
      uint32_t s=io_.status();
      if(s&ARLO)return fail(ARBITRATION,s);
      if(s&OVR)return fail(OVERRUN,s);
      if(s&NACKF)return fail(NACK,s);
      // ES0499 Rev12 section2.20.2, applies to U585 revisionU as well.
      // Log/clear BERR but do not abort an otherwise progressing master transfer.
      if(s&BERR){
        if(!r_.berr_events){r_.first_berr_isr=s;r_.first_berr_cr2=io_.control();r_.first_berr_lines=io_.line_bits();}
        if(r_.berr_events!=UINT32_MAX)++r_.berr_events;
        io_.clear_berr();
      }
      if(expired())return fail(DEADLINE,s);
      if(s&mask)return true;
      io_.wait_step();
    }
  }
  void cleanup(){
    const uint32_t began=io_.now_us();uint32_t s=r_.final_isr;
    if(r_.transfer.cause==NACK){
      // Give automatic STOP time to finish before clearing flags/CR2. No
      // successful sample or retry is created by this cleanup.
      while(!(s&(STOPF|ARLO))&&!expired()&&uint32_t(io_.now_us()-began)<120){io_.wait_step();s=io_.status();}
      if((s&STOPF)&&!(s&ARLO)&&!(s&BUSY)){io_.clear();io_.quiesce();r_.graceful_cleanup=true;return;}
    }else if(r_.transfer.cause==ARBITRATION||r_.transfer.cause==BUS_BUSY){
      // Never generate STOP after arbitration loss; this could disturb a
      // different bus owner. Wait boundedly for an already free bus instead.
      while(((s&BUSY)||!io_.lines_high())&&!expired()&&uint32_t(io_.now_us()-began)<120){io_.wait_step();s=io_.status();}
      if(!(s&BUSY)&&io_.lines_high()){io_.clear();io_.quiesce();r_.graceful_cleanup=true;return;}
    }
    io_.reset();r_.controller_reset=true;
  }
  Io &io_;PollResult r_;uint32_t begin_=0;
};
}
