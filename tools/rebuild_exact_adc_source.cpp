/* PC-only reconstruction using unchanged installed C kernels. No device APIs. */
#include <cstring>
#include "peak_core.h"
#include "current_core.h"
#include "observer_current_window.h"
#include "observer_applied_voltage.h"

extern "C" __declspec(dllexport) int rebuild_exact(const unsigned char*bytes,
    ow_bin*out,float*values,float phase){
 pc_blob blob;memcpy(&blob,bytes,sizeof(blob));
 const pc_header&h=blob.header;
 if(h.schema!=3||!(h.flags&PC_EXACT)||h.count!=60)return -1;
 unsigned pos=h.trigger_slot>=24?h.trigger_slot-24:h.trigger_slot+36;
 ow_state accumulator={};accumulator.n=8;accumulator.last=blob.samples[pos].cycles;
 accumulator.previous_center=accumulator.last-8U*10624U;
 cm_core zero={};memcpy(zero.offset,h.offset,sizeof(h.offset));
 ma_geometry geometry={h.arr,(unsigned)h.arr-128U,771,112,240,229};
 float old_a=0,old_b=0;
 for(unsigned k=0;k<25;++k,pos=pc_next(pos)){
  const pc_raw&r=blob.samples[pos];
  uint16_t a=r.packed[0]|((r.packed[1]&15U)<<8);
  uint16_t b=(r.packed[1]>>4)|(r.packed[2]<<4),ccr[4];
  uint64_t encoded=0;for(unsigned i=0;i<7;++i)encoded|=(uint64_t)r.packed[3+i]<<(8U*i);
  for(unsigned i=0;i<4;++i)ccr[i]=(uint16_t)((encoded>>(13U*i))&8191U);
  unsigned pair=(r.meta>>9)&3U;int16_t counts[3];
  if((r.meta>>11)!=1U||!cm_reconstruct(&zero,pair,a,b,counts))return -2;
  const float scale=(float)(3.30/(4095.0*0.04*2.1));
  float ia=counts[0]*scale,ib=(ia+2.f*(counts[1]*scale))*.5773502692f,va,vb;
  if(ma_applied_voltage(&geometry,ccr,h.arr,r.meta&511U,ia,ib,&va,&vb))return -3;
  values[4*k]=ia;values[4*k+1]=ib;values[4*k+2]=va;values[4*k+3]=vb;
  /* phase<0 exactly reproduces installed right-endpoint ZOH. Other values
   * are explicitly offline timing sensitivities, not calibrated firmware. */
  float avg_a=phase<0?va:old_a*(1.f-phase)+va*phase;
  float avg_b=phase<0?vb:old_b*(1.f-phase)+vb*phase;
  old_a=va;old_b=vb;
  if(k){
   int rc=ow_push_pair(&accumulator,r.cycles,31875U,ia,ib,avg_a,avg_b,out,pair);
   if(rc!=(k==8||k==24))return -4;
  }
 }
 return 0;
}
