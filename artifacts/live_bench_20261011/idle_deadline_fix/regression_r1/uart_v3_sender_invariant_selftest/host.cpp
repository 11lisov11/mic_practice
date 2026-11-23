
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <array>
#include "uart_v3_transport.h"
float g_freq_ref=0, g_vdc=325, g_v_limit=0.577f*325, g_vf_v_per_hz=0.577f*325/50;
float g_vf_start_boost_v=6;
float clampf(float x,float a,float b){return x<a?a:(x>b?b:x);}
uint16_t q15_unit(float x){return static_cast<uint16_t>(clampf(x,0,1)*32767);}
constexpr float VF_START_BOOST_MIN_FREQ_HZ=0.1f;
constexpr float VF_START_BOOST_TAPER_HZ=10.0f;
static uint16_t bp_scalar_vmag_q15() {
  float freq_abs = fabsf(g_freq_ref);
  float boost_v = 0.0f;
  if (freq_abs >= VF_START_BOOST_MIN_FREQ_HZ) {
    float boost_taper = 1.0f - clampf(freq_abs / VF_START_BOOST_TAPER_HZ, 0.0f, 1.0f);
    boost_v = g_vf_start_boost_v * boost_taper;
  }
  float v_mag = (g_vf_v_per_hz * g_freq_ref) + boost_v;
  v_mag = clampf(v_mag, 0.0f, g_v_limit);
  // MODE_SCALAR uses alpha/beta magnitude in per-unit and then
  // maps it to duty with 0.5 + 0.5*v. Match the UNO Q voltage-domain SVM.
  float mag_pu = (g_vdc > 0.1f) ? ((2.0f * v_mag) / g_vdc) : 0.0f;
  return q15_unit(clampf(mag_pu, 0.0f, 0.95f));
}
using Frame=std::array<uint8_t,UV3_FRAME>;
Frame frame(uint8_t seq,uint16_t magnitude){
 Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=3;f[3]=1;f[4]=3;f[5]=seq;
 uint32_t frequency=5000;for(unsigned i=0;i<4;++i) f[6+i]=frequency>>(8*i);
 f[10]=magnitude;f[11]=magnitude>>8;uv3_seal(f.data());return f;
}
uv3_result feed(uv3_rx& rx,const Frame& f,uint32_t t,bool noise){
 uv3_result r=UV3_WAIT;for(unsigned i=0;i<f.size();++i)
  r=uv3_byte(&rx,f[i],noise&&i==10?UV3_NE:0,t+i/12);
 return r;
}
unsigned checks=0;
void check(bool value){++checks;if(!value)std::abort();}
int main(){
 unsigned legacy_reject=0,fixed_accept=0;
 for(unsigned trial=0;trial<1000;++trial){
  uv3_rx legacy{},fixed{};uv3_init(&legacy,true);uv3_init(&fixed,true);
  for(unsigned i=0;i<4;++i){
   g_freq_ref=.15f+.05f*i;
   Frame old=frame(static_cast<uint8_t>(trial+i),bp_scalar_vmag_q15());
   Frame corrected=frame(static_cast<uint8_t>(trial+i),0);
   check(feed(legacy,old,i*50,false)==UV3_READY);uv3_commit(&legacy,i*50+4,true,false,false);
   check(feed(fixed,corrected,i*50,false)==UV3_READY);uv3_commit(&fixed,i*50+4,true,false,false);
  }
  g_freq_ref=.35f;
  Frame old=frame(static_cast<uint8_t>(trial+4),bp_scalar_vmag_q15());
  Frame corrected=frame(static_cast<uint8_t>(trial+4),0);
  check(uv3_crc_ok(old.data())&&uv3_crc_ok(corrected.data()));
  check(feed(legacy,old,200,true)==UV3_NOISE_REJECTED);++legacy_reject;
  check(feed(fixed,corrected,200,true)==UV3_READY);++fixed_accept;
  uv3_commit(&fixed,204,true,false,false);
  corrected=frame(static_cast<uint8_t>(trial+5),0);corrected[8]^=1;
  check(feed(fixed,corrected,250,false)==UV3_BAD_CRC);
 }
 std::printf("{\"checks\":%u,\"legacy_intact_ne_rejected\":%u,\"canonical_intact_ne_accepted\":%u}",checks,legacy_reject,fixed_accept);
}
