#ifndef MIC_BUS_CLEAR_WIRE_H
#define MIC_BUS_CLEAR_WIRE_H
#include "encoder_wire.h"
static inline bool bc_packet_valid(const uint8_t*p,uint32_t peer,bool off){
  if(!off||peer!=EW_PEER||p[0]!=0x55||p[1]!=0xaa||p[2]!=0xde||p[3]!=1||
     !uv3_crc_ok(p)||ew_u32(p+6)!=EW_PEER||p[4]<1||p[4]>6||p[5]>9||
     p[10]>3||p[11]>3||p[12]>3||p[13]||ew_u32(p+14)>25000U)return false;
  if(p[4]<=2 && p[12]!=3)return false;
  if(p[4]==1 && p[5]!=0)return false;
  if(p[4]==2 && !p[5])return false;
  for(unsigned n=26;n<39;n++)if(p[n])return false;
  return true;
}
#endif
