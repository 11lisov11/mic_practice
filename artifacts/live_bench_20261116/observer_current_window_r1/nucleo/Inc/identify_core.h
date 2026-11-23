#ifndef MIC_IDENTIFY_CORE_H
#define MIC_IDENTIFY_CORE_H
/* Bounded, fixed-spatial-axis commissioning. This kernel cannot enable outputs,
 * acknowledge faults, change calibration, or write peripheral registers.
 * Every invocation receives a REAL accepted current/active-CCR sample from the
 * original ADC epoch guard. Only an explicit ordinary protected START can run it.
 */
#include "motor_control.h"
#include "uart_v3_transport.h"
enum { MI_DC=1,MI_AC=2,MI_BINS=64,MI_HEADER=128,MI_RECORD=24,
       MI_BYTES=MI_HEADER+MI_BINS*MI_RECORD,MI_PAGES=(MI_BYTES+23)/24 };
enum { MI_OK=0,MI_COMPLETE=1,MI_BAD_CURRENT=2,MI_STALE=3,MI_BUS=4,
       MI_WINDOW=5,MI_EXTERNAL_STOP=6,MI_BAD_CONFIG=7,MI_OVERRUN=8,MI_NO_RESPONSE=9 };
typedef struct {
  uint32_t run_id,kind;float frequency,axis,amplitude,rs;uint32_t duration_ms;
  float gain,drop[3],knee,offset[2];uint32_t calibration_crc;
} mi_config;
typedef char mi_config_is_60[(sizeof(mi_config)==60)?1:-1];
typedef struct {uint32_t cycles,epoch;float ia,ib,bus;uint16_t ccr[3],arr;uint8_t valid;} mi_sample;
typedef struct {float sum[9];uint32_t n;} mi_bin;
typedef struct {
  mi_config config;ma_controller modulation;
  mi_bin bins[MI_BINS];uint8_t bytes[MI_BYTES];uint32_t crc;
  uint32_t start,accepted,rejected,last_epoch,last_sample,finish,cycles_complete,config_crc;
  float integral,voltage_amplitude,current_energy,current_sin,current_cos,response;uint32_t current_n,last_cycle;
  float peak,min_bus,max_bus,axis_cos,axis_sin;uint32_t settle_cycles;uint8_t active,done,fault,ready;
} mi_state;
static inline uint32_t mi_cal_crc(const mi_config*c){return uv3_crc32c((const uint8_t*)&c->gain,7*4);}
static inline unsigned mi_settle_cycles(const mi_config*c){return (unsigned)fmaxf(3,ceilf(c->frequency));}
static inline int mi_config_valid(const mi_config*c){
  if(!c->run_id||(c->kind!=MI_DC&&c->kind!=MI_AC)||!isfinite(c->axis)||c->axis<0||c->axis>=6.283186f||
    !isfinite(c->amplitude)||fabsf(c->amplitude)<.025f||fabsf(c->amplitude)>.30f||
    !isfinite(c->rs)||c->rs<=0||c->rs>100||c->duration_ms>10000)return 0;
  if(c->kind==MI_DC)return c->frequency==0&&c->duration_ms>=2000;
  if(!isfinite(c->frequency)||c->frequency<1||c->frequency>200||c->amplitude<0||
     !isfinite(c->gain)||c->gain<.95f||c->gain>1.05f||
     !isfinite(c->knee)||c->knee<.002f||c->knee>.15f)return 0;
  for(unsigned i=0;i<3;i++)if(!isfinite(c->drop[i])||c->drop[i]<0||c->drop[i]>15)return 0;
  for(unsigned i=0;i<2;i++)if(!isfinite(c->offset[i])||fabsf(c->offset[i])>2)return 0;
  const float need_ms=1000.f*(mi_settle_cycles(c)+5)/c->frequency;
  return c->duration_ms>=need_ms&&c->calibration_crc==mi_cal_crc(c);
}
static inline int mi_begin(mi_state*s,const mi_config*c,uint32_t now){
  if(s->active||s->ready||!mi_config_valid(c))return 0;
  memset(s,0,sizeof(*s));s->config=*c;s->config_crc=uv3_crc32c((const uint8_t*)c,sizeof(*c));
  s->active=1;s->start=now;s->last_epoch=UINT32_MAX;s->min_bus=INFINITY;
  s->axis_cos=cosf(c->axis);s->axis_sin=sinf(c->axis);
  s->settle_cycles=mi_settle_cycles(c);
  s->voltage_amplitude=fminf(24,fabsf(c->amplitude)*c->rs);return 1;
}
static inline void mi_stop(mi_state*s,uint8_t fault,uint32_t now){
  if(!s->active)return;
  s->active=0;s->done=1;s->fault=fault;s->finish=now;
}
static inline float mi_shape(float i,float knee){return i/(fabsf(i)+knee);}
/* Inputs are finite by the preceding configuration/current checks. */
static inline float mi_clip(float x,float lo,float hi){return x<lo?lo:x>hi?hi:x;}
/* Centered placement for the bounded measurement vector. Same pulse limits and
 * exact all-three-leg planner as ma_modulate; no adaptive search or libm round
 * calls are needed in this measurement mode. Reject rather than move an unsafe
 * centered vector. The separate adaptive motor algorithm remains unchanged. */
static inline int mi_modulate(const ma_geometry*g,float va,float vb,float bus,ma_output*out){
  if(!g->arr||g->arr>65535||g->latest>=g->arr||g->settle>=g->arr||g->acquire>=g->arr||
     g->min_pulse*2>=g->arr||!isfinite(va)||!isfinite(vb)||!isfinite(bus)||bus<30||bus>350)return MA_BUS;
  const float phase[3]={va,-.5f*va+.8660254038f*vb,-.5f*va-.8660254038f*vb};
  float hi=phase[0],lo=phase[0];
  for(unsigned i=0;i<3;i++){
    if(!isfinite(phase[i]))return MA_BUS;
    if(phase[i]>hi)hi=phase[i];
    if(phase[i]<lo)lo=phase[i];
  }
  const float z=-.5f*(hi+lo),scale=g->arr/bus;uint32_t cc[3];
  for(unsigned i=0;i<3;i++){
    float count=.5f*g->arr+(phase[i]+z)*scale;
    if(!isfinite(count)||count<0||count>g->arr)return MA_WINDOW;
    cc[i]=(uint32_t)(count+.5f);
    if(cc[i]<g->min_pulse||cc[i]>g->arr-g->min_pulse)return MA_WINDOW;
  }
  mic_current_window_plan p=mic_plan_current_window(cc[0],cc[1],cc[2],g->latest,g->settle,g->acquire);
  if(!p.valid)return MA_WINDOW;
  out->shift=0;out->trigger=p.trigger;out->pair=p.pair;
  const float inv_arr=1.f/g->arr;
  for(unsigned i=0;i<3;i++){out->ccr[i]=cc[i];out->duty[i]=cc[i]*inv_arr;}
  float mean=(out->duty[0]+out->duty[1]+out->duty[2])/3;
  out->va=(out->duty[0]-mean)*bus;out->vb=(out->duty[1]-out->duty[2])*bus*.5773502692f;
  return MA_OK;
}
static inline void mi_loss(const mi_config*c,float ia,float ib,float*out){
  const float ip[3]={ia,-.5f*ia+.8660254038f*ib,-.5f*ia-.8660254038f*ib};
  float e[3];for(unsigned i=0;i<3;i++)e[i]=c->drop[i]*mi_shape(ip[i],c->knee);
  out[0]=(2*e[0]-e[1]-e[2])/3;out[1]=(e[1]-e[2])*.5773502692f;
}
static inline void mi_voltage(const mi_config*c,const mi_sample*x,float*v){
  float mean=(x->ccr[0]+x->ccr[1]+x->ccr[2])/(3.f*x->arr);
  v[0]=(x->ccr[0]/(float)x->arr-mean)*x->bus;
  v[1]=(x->ccr[1]-(float)x->ccr[2])/x->arr*x->bus*.5773502692f;
  v[2]=v[0];v[3]=v[1];
  if(c->kind==MI_AC){
    float loss[2];mi_loss(c,x->ia,x->ib,loss);
    v[2]=c->gain*v[0]-loss[0]+c->offset[0];v[3]=c->gain*v[1]-loss[1]+c->offset[1];
  }
}
/* Capture uses the sample's own timestamp/active compares, never next CCRs.
 * Phase bins average all measured cycles; averaged sin/cos are retained for LS,
 * so nonuniform ADC instants do not become fictitious uniform samples.
 */
static inline int mi_step(mi_state*s,const ma_geometry*g,const mi_sample*x,
                        uint32_t now,uint32_t clock,ma_output*out){
  memset(out,0,sizeof(*out));if(!s->active)return s->done?MI_COMPLETE:MI_BAD_CONFIG;
  const float t=(float)(uint32_t)(now-s->start)/clock;
  if(t>=s->config.duration_ms*.001f){mi_stop(s,0,now);return MI_COMPLETE;}
  uint8_t fault=0;
  const float current_sq=x->ia*x->ia+x->ib*x->ib;
  if(!x->valid||!isfinite(x->ia)||!isfinite(x->ib)||!x->arr||
    (uint32_t)(now-x->cycles)>clock*3U/16000U)fault=MI_STALE;
  else if(!isfinite(x->bus)||x->bus<30||x->bus>350)fault=MI_BUS;
  else if(!(current_sq<=.45f*.45f))fault=MI_BAD_CURRENT;
  if(fault){s->rejected++;mi_stop(s,fault,now);return fault;}
  const mi_config*c=&s->config;const float ca=s->axis_cos,sa=s->axis_sin;
  const float directed=x->ia*ca+x->ib*sa;
  s->response+=(directed-s->response)*(.0000625f/.1f);
  float phase=0,sv=0,requested=0;
  if(c->kind==MI_DC){
    if(t>1.25f&&s->response*(c->amplitude>0?1:-1)<.2f*fabsf(c->amplitude)){
      mi_stop(s,MI_NO_RESPONSE,now);return MI_NO_RESPONSE;
    }
    const float target=c->amplitude*fminf(1,t/.25f),error=target-directed;
    float raw=c->rs*target+5.f*error+s->integral;
    requested=mi_clip(raw,-24,24);
    s->integral+=1.f/16000*(100*error+20*(requested-raw));
    s->integral=mi_clip(s->integral,-24,24);
  }else{
    const float cycle_position=c->frequency*t;
    unsigned cycle=(unsigned)cycle_position,settle=s->settle_cycles;
    phase=6.2831853072f*(cycle_position-cycle);sv=sinf(phase);
    if(cycle!=s->last_cycle){
      if(s->current_n){
        float measured=2*hypotf(s->current_sin,s->current_cos)/s->current_n;
        if(cycle>=3&&measured<c->amplitude*.1f){mi_stop(s,MI_NO_RESPONSE,now);return MI_NO_RESPONSE;}
        if(cycle<settle){
          float gain=mi_clip(c->amplitude/(measured>.005f?measured:.005f),.7f,1.4f);
          s->voltage_amplitude=mi_clip(s->voltage_amplitude*gain,.25f,24);
        }
      }
      s->current_energy=0;s->current_sin=s->current_cos=0;s->current_n=0;s->last_cycle=cycle;
    }
    s->current_energy+=directed*directed;s->current_sin+=directed*sv;s->current_cos+=directed*cosf(phase);s->current_n++;
    requested=s->voltage_amplitude*sv;
  }
  float va=requested*ca,vb=requested*sa;
  if(c->kind==MI_AC){
    float loss[2];mi_loss(c,x->ia,x->ib,loss);
    va=(va+loss[0]-c->offset[0])/c->gain;vb=(vb+loss[1]-c->offset[1])/c->gain;
  }
  int rc=mi_modulate(g,va,vb,x->bus,out);
  if(rc){mi_stop(s,MI_WINDOW,now);return MI_WINDOW;}
  out->valid=1;
  if(x->epoch!=s->last_epoch){
    s->last_epoch=x->epoch;s->last_sample=x->cycles;
    if(current_sq>s->peak*s->peak)s->peak=sqrtf(current_sq);
    if(x->bus<s->min_bus)s->min_bus=x->bus;
    if(x->bus>s->max_bus)s->max_bus=x->bus;
    const float ts=(float)(uint32_t)(x->cycles-s->start)/clock;
    float record_phase=0;
    unsigned bin;
    int capture;
    if(c->kind==MI_DC){
      const float begin=c->duration_ms*.001f-.5f;
      capture=ts>=begin;bin=(unsigned)mi_clip((ts-begin)*MI_BINS/.5f,0,MI_BINS-1);
    }else{
      float cycles=c->frequency*ts;unsigned complete=(unsigned)cycles;
      record_phase=6.2831853072f*(cycles-complete);
      s->cycles_complete=complete;
      capture=complete>=s->settle_cycles&&complete<s->settle_cycles+5;
      bin=(unsigned)((cycles-complete)*MI_BINS);if(bin>=MI_BINS)bin=MI_BINS-1;
    }
    if(capture){
      float v[4];mi_voltage(c,x,v);mi_bin*b=&s->bins[bin];
      const float values[9]={x->ia,x->ib,v[0],v[1],v[2],v[3],sinf(record_phase),cosf(record_phase),ts*1.e6f};
      for(unsigned i=0;i<9;i++)b->sum[i]+=values[i];
      b->n++;s->accepted++;
    }
  }
  return MI_OK;
}
static inline void mi_put32(uint8_t*p,uint32_t value){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(8*i));}
static inline void mi_float(uint8_t*p,float value){uint32_t v;memcpy(&v,&value,4);mi_put32(p,v);}
static inline void mi_i16(uint8_t*p,float value){int16_t v=(int16_t)lroundf(ma_clip(value,-32767,32767));p[0]=(uint8_t)v;p[1]=(uint8_t)((uint16_t)v>>8);}
/* Main/OFF-only serialization. Does not erase an older pending result. */
static inline int mi_seal(mi_state*s,uint32_t build,uint32_t clock){
  if(s->active||!s->done||s->ready)return 0;
  uint8_t*p=s->bytes;memset(p,0,MI_BYTES);
  const uint32_t meta[12]={0x3144494D,1,build,s->config.run_id,s->config.kind,s->fault,!s->fault,s->accepted,s->rejected,MI_BINS,16000,clock};
  for(unsigned i=0;i<12;i++)mi_put32(p+4*i,meta[i]);
  mi_float(p+48,s->config.frequency);mi_float(p+52,s->config.axis);mi_float(p+56,s->config.amplitude);mi_float(p+60,s->config.rs);
  mi_put32(p+64,s->config.duration_ms);mi_put32(p+68,s->cycles_complete);
  mi_float(p+72,isfinite(s->min_bus)?s->min_bus:0);mi_float(p+76,s->max_bus);mi_float(p+80,s->peak);
  mi_put32(p+84,s->config_crc);mi_put32(p+88,s->config.calibration_crc);
  mi_put32(p+92,s->start);mi_put32(p+96,s->last_sample);mi_put32(p+100,1);mi_put32(p+104,1);
  for(unsigned k=0;k<MI_BINS;k++){
    mi_bin*b=&s->bins[k];uint8_t*r=p+MI_HEADER+k*MI_RECORD;
    r[0]=(uint8_t)b->n;r[1]=(uint8_t)(b->n>>8);
    if(!b->n)continue;
    const float n=(float)b->n;
    for(unsigned j=0;j<6;j++)mi_i16(r+2+2*j,b->sum[j]/n*(j<2?1000:100));
    mi_i16(r+14,b->sum[6]/n*32767);mi_i16(r+16,b->sum[7]/n*32767);
    mi_put32(r+20,(uint32_t)lroundf(b->sum[8]/n));
  }
  s->crc=uv3_crc32c(p,MI_BYTES);s->ready=1;return 1;
}
static inline int mi_ack(mi_state*s,uint32_t crc){
  if(s->active||!s->ready||s->crc!=crc)return 0;
  s->ready=0;s->done=0;return 1;
}
#endif
