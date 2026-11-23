#include <identify_core.h>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <fstream>
/* Independent double precision terminal circuit, stationary rotor; no estimator
 * parameter or controller state is used as a plant state. */
struct Plant{
 double x[4]={};double rs=12.23,rr=9,ls=.462,lr=.462,lm=.45;
 void current(double&a,double&b){double det=ls*lr-lm*lm;a=(lr*x[0]-lm*x[2])/det;b=(lr*x[1]-lm*x[3])/det;}
 void deriv(double*z,double ideal_a,double ideal_b,double*f){
  const double det=ls*lr-lm*lm,ia=(lr*z[0]-lm*z[2])/det,ib=(lr*z[1]-lm*z[3])/det;
  const double ip[3]={ia,-.5*ia+.866025403784*ib,-.5*ia-.866025403784*ib};
  const double drops[3]={7,7.4,6.7};double e[3];
  for(unsigned i=0;i<3;i++)e[i]=drops[i]*ip[i]/(std::abs(ip[i])+.025);
  const double va=.99*ideal_a-(2*e[0]-e[1]-e[2])/3+.10;
  const double vb=.99*ideal_b-(e[1]-e[2])/sqrt(3.)-.06;
  f[0]=va-rs*ia;f[1]=vb-rs*ib;f[2]=-rr*(-lm*z[0]+ls*z[2])/det;f[3]=-rr*(-lm*z[1]+ls*z[3])/det;
 }
 void step(double va,double vb,double dt){
  double k[4][4],z[4];deriv(x,va,vb,k[0]);
  for(unsigned i=0;i<4;i++)z[i]=x[i]+.5*dt*k[0][i];deriv(z,va,vb,k[1]);
  for(unsigned i=0;i<4;i++)z[i]=x[i]+.5*dt*k[1][i];deriv(z,va,vb,k[2]);
  for(unsigned i=0;i<4;i++)z[i]=x[i]+dt*k[2][i];deriv(z,va,vb,k[3]);
  for(unsigned i=0;i<4;i++)x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
 }
};
static int execute(mi_config c,const std::string&file){
 Plant p;mi_state state={};uint32_t clock=170000000,now=0;
 ma_geometry geometry={5312,5184,771,112,240,229};
 std::mt19937 random(c.run_id);std::normal_distribution<float> noise(0,.0015f);
 ma_output command={};uint16_t active[3]={2656,2656,2656};
 uint32_t n=0;assert(mi_begin(&state,&c,0));
 for(;;){
  double ia,ib;p.current(ia,ib);
  const double ideal_a=(2.*active[0]-active[1]-active[2])/5312*320/3;
  const double ideal_b=(active[1]-(double)active[2])/5312*320/sqrt(3.);
  // Current at the actual quiet strobe, at a different instant from UPDATE.
  p.step(ideal_a,ideal_b,5184./clock);p.current(ia,ib);
  mi_sample sample={};sample.ia=(float)ia+noise(random);sample.ib=(float)ib+noise(random);
  sample.bus=320;sample.arr=5312;sample.cycles=now+5184;sample.epoch=++n;sample.valid=1;
  for(unsigned i=0;i<3;i++)sample.ccr[i]=active[i];
  p.step(ideal_a,ideal_b,(10624.-5184)/clock);now+=10624;
  int rc=mi_step(&state,&geometry,&sample,now,clock,&command);
  if(rc==MI_COMPLETE)break;
  if(rc!=MI_OK){fprintf(stderr,"run%u kind%u f%g failed=%d time=%g peak=%g\n",c.run_id,c.kind,c.frequency,rc,now/(double)clock,state.peak);return 1;}
  for(unsigned i=0;i<3;i++)active[i]=(uint16_t)command.ccr[i];
  assert(n<200000);
 }
 assert(mi_seal(&state,2026102936,clock));assert(state.ready&&!state.active&&!state.fault);
 assert(!mi_begin(&state,&c,now));assert(!mi_ack(&state,state.crc^1));
 std::ofstream stream(file,std::ios::binary);stream.write((const char*)state.bytes,MI_BYTES);
 printf("{\"run_id\":%u,\"kind\":%u,\"frequency\":%g,\"accepted\":%u,\"peak_A\":%.6f,\"source_kind\":\"synthetic\",\"file\":\"%s\"}\n",c.run_id,c.kind,c.frequency,state.accepted,state.peak,file.c_str());
 assert(mi_ack(&state,state.crc));return 0;
}
static void negatives(){
 mi_config c={1,MI_DC,0,0,.1f,12.23f,3000,1,{0,0,0},.025f,{0,0},0};mi_state s={};ma_output out;
 ma_geometry g={5312,5184,771,112,240,229};mi_sample x={};x.arr=5312;x.bus=320;x.valid=1;
 assert(mi_config_valid(&c));assert(mi_begin(&s,&c,0));x.ia=.5f;
 assert(mi_step(&s,&g,&x,10624,170000000,&out)==MI_BAD_CURRENT&&!out.valid);
 assert(mi_seal(&s,2026102936,170000000));assert(s.fault&&s.ready&&!mi_begin(&s,&c,0));
 assert(mi_ack(&s,s.crc));assert(mi_begin(&s,&c,0));x.ia=0;x.valid=0;
 assert(mi_step(&s,&g,&x,10624,170000000,&out)==MI_STALE&&!out.valid);
 c.amplitude=.31f;assert(!mi_config_valid(&c));c.amplitude=.1f;c.kind=MI_AC;c.frequency=1;c.duration_ms=8000;
 assert(!mi_config_valid(&c));c.calibration_crc=mi_cal_crc(&c);assert(mi_config_valid(&c));
 c.duration_ms=500;assert(!mi_config_valid(&c));
}
int main(int argc,char**argv){
 assert(argc==3);negatives();std::string mode=argv[1],folder=argv[2];unsigned run=1;int bad=0;
 if(mode=="dc"){
  for(unsigned axis=0;axis<3;axis++)for(float amp:{-.30f,-.20f,-.12f,-.06f,-.03f,.03f,.06f,.12f,.20f,.30f}){
   mi_config c={run++,MI_DC,0,axis*2.0943951024f,amp,12.23f,3000,1,{0,0,0},.025f,{0,0},0};
   bad+=execute(c,folder+"/dc_"+std::to_string(c.run_id)+".bin");
  }
 }else{
  // Calibration is obtained from the independent DC stage, passed by file.
  std::ifstream input(folder+"/calibration_core.bin",std::ios::binary);float a[7];input.read((char*)a,sizeof(a));assert(input.good());
  for(float f:{1.f,2.f,5.f,10.f,20.f,50.f,100.f,200.f,3.f,8.f,30.f,80.f}){
   mi_config c={run++,MI_AC,f,0,.2f,12.23f,(uint32_t)ceilf(1000*(fmaxf(3,ceilf(f))+5)/f)+1,a[0],{a[1],a[2],a[3]},a[4],{a[5],a[6]},0};
   c.calibration_crc=mi_cal_crc(&c);bad+=execute(c,folder+"/ac_"+std::to_string(c.run_id)+".bin");
  }
 }
 return bad?1:0;
}
