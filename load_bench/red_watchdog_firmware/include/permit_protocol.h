#pragma once
#include "lease.h"
#include <string.h>

#define RNR_IMAGE_ID "RNRWD_AT32F403RC_20261122"

// Pure state machine, compiled into both the MCU image and the native tests.
struct PermitProtocol {
  Lease lease;
  bool identified=false,latched=false;
  void stop(){lease.stop();latched=true;}
  bool permit(uint32_t now){
    bool was=lease.active;
    bool result=lease.permit(now);
    if(was&&!result)latched=true;
    return identified&&!latched&&result;
  }
  bool issue(uint32_t now){
    permit(now);
    if(!identified||latched)return false;
    lease.issue(now);return true;
  }
  // Return 1=ID, 2=OFF, 3=OK, 0=no reply. Values are fixed width hex.
  int receive(const char *input,uint32_t now,uint32_t &value){
    permit(now);
    if(!strcmp(input,"HELLO")){
      lease.stop();identified=true;latched=false;return 1;
    }
    if(!strcmp(input,"STOP")){stop();value=0;return 2;}
    if(!identified||latched)return 0;
    if(strlen(input)!=17||strncmp(input,"ACK ",4)||input[12]!=' '){stop();return 0;}
    uint32_t nonce=0;uint16_t received=0;
    for(unsigned i=4;i<17;++i){
      if(i==12)continue;
      unsigned x;
      if(input[i]>='0'&&input[i]<='9')x=input[i]-'0';
      else if(input[i]>='A'&&input[i]<='F')x=input[i]-'A'+10;
      else{stop();return 0;}
      if(i<12)nonce=(nonce<<4)|x;else received=uint16_t((received<<4)|x);
    }
    char body[13];memcpy(body,input,12);body[12]=0;
    if(lease_crc(body)!=received){stop();return 0;}
    if(!lease.reply(nonce,now)){stop();return 0;}
    value=nonce;return 3;
  }
};
