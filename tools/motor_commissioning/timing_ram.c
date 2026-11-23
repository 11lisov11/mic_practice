/* CPU-only timing fixture. No motor, GPIO, timer or ADC register access.
 * The only peripheral read is DWT CYCCNT. All samples below are synthetic.
 * Executed only on a discharged USB bench with firmware RAM/registers saved.
 */
#pragma GCC optimize ("O2","no-fast-math")
#include <identify_core.h>
static mi_state state;
typedef struct {uint32_t kind,late,frequency,initialization,first,max_step,min_step,steps,fault;} timing_row;
volatile struct {uint32_t magic,complete,rows,clock;timing_row row[8];} timing_result;
static inline uint32_t cycles(void){return *(volatile uint32_t*)0xe0001004;}
int bench_run(void){
 memset((void*)&timing_result,0,sizeof(timing_result));timing_result.magic=0x54494d45;timing_result.clock=170000000;
 ma_geometry g={5312,5184,771,112,240,229};ma_output output;
 for(unsigned k=0;k<8;k++){
  mi_config c={k+1,k<2?MI_DC:MI_AC,0,0,.06f,12.23f,3000,1,{0,0,0},.025f,{0,0},0};
  unsigned late=k%2;float freq=k<2?0:k<4?1:k<6?50:200;
  if(k>=2){c.frequency=freq;c.amplitude=.2f;c.duration_ms=(uint32_t)ceilf(1000*(mi_settle_cycles(&c)+5)/freq)+1;c.calibration_crc=mi_cal_crc(&c);}
  memset(&state,0,sizeof(state));uint32_t begin=cycles();int okay=mi_begin(&state,&c,0);uint32_t init=cycles()-begin;
  timing_row row={c.kind,late,(uint32_t)freq,init,0,0,UINT32_MAX,0,0};
  if(!okay){row.fault=MI_BAD_CONFIG;timing_result.row[k]=row;continue;}
  state.response=c.amplitude;
  for(unsigned n=0;n<256;n++){
   mi_sample sample;memset(&sample,0,sizeof(sample));sample.valid=1;sample.arr=5312;sample.bus=320;
   float offset=late?(c.kind==MI_DC?2.6f:(mi_settle_cycles(&c)+.1f)/freq):.1f;
   sample.cycles=(uint32_t)(offset*170000000)+n*10624;sample.epoch=n+1;
   float phase=6.2831853072f*freq*sample.cycles/170000000;
   sample.ia=c.kind==MI_DC?c.amplitude:c.amplitude*sinf(phase);
   for(unsigned j=0;j<3;j++)sample.ccr[j]=2656;
   begin=cycles();int rc=mi_step(&state,&g,&sample,sample.cycles+32,170000000,&output);uint32_t elapsed=cycles()-begin;
   if(!n)row.first=elapsed;
   if(elapsed>row.max_step)row.max_step=elapsed;
   if(elapsed<row.min_step)row.min_step=elapsed;
   row.steps++;
   if(rc!=MI_OK){row.fault=(uint32_t)rc;break;}
  }
  timing_result.row[k]=row;timing_result.rows=k+1;
 }
 timing_result.complete=1;return 0;
}
