#pragma once
#include <stdint.h>
struct RpcRoutePolicy {
  uint32_t last_attempt=0,attempts=0,failures=0,last_reply=0,renewed=0;
  bool due(uint32_t now,bool local_pwm,bool outputs,bool remote_pwm,bool ready) {
    if(local_pwm||outputs||remote_pwm||!ready||(uint32_t)(now-last_attempt)<5000U)return false;
    last_attempt=now;__atomic_fetch_add(&attempts,1U,__ATOMIC_RELAXED);return true;
  }
  void finish(uint32_t now,uint8_t cmd,uint8_t get){
    if(!cmd||!get)__atomic_fetch_add(&failures,1U,__ATOMIC_RELAXED);
    else __atomic_store_n(&last_reply,now,__ATOMIC_RELAXED);
    if(cmd==1||get==1)__atomic_fetch_add(&renewed,1U,__ATOMIC_RELAXED);
  }
};
