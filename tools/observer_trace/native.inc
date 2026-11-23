
/* Observational writer in foreground only; no diagnostic DMA/serial during RUN. */
static od_capture observer_trace;
static volatile float bin_id,bin_iq,bin_idref,bin_iqref,bin_reference;
static volatile uint32_t bin_control_sequence,bin_control_adc_cycles;
static void ma_observer_record(const ma_current_sample*s,uint32_t stamp,uint32_t seq,uint32_t adc,
 float id,float iq,float idref,float iqref,float reference,float va,float vb,float dt,int fault,int published){
 if(observer_trace.frozen||!running||!LL_TIM_IsEnabledAllOutputs(TIM1))return;
 od_sample r;
 r.cycles=DWT->CYCCNT;r.steps=observer.steps;
 r.reasons=od_reasons(running,fe_profile_allowed(selected),observer.steps,run_fault||fault,
   hypotf(observer.x[2],observer.x[3]),model.flux,observer.nis);
 r.control_sequence=seq;r.control_adc_cycles=adc;
 r.observer_sequence=s->sequence;r.observer_adc_cycles=s->cycles;r.bin_cycles=stamp;
 r.rpm=observer.x[4]*9.549296586f;r.flux_alpha=observer.x[2];r.flux_beta=observer.x[3];r.nis=observer.nis;
 r.id=id;r.iq=iq;r.id_ref=idref;r.iq_ref=iqref;r.reference_hz=reference;
 r.ia=ma_amps(s->counts[0]);r.ib=(r.ia+2.f*ma_amps(s->counts[1]))*.5773502692f;
 r.va=va;r.vb=vb;r.dt=dt;r.observer_fault=(uint32_t)fault;r.published=(uint32_t)published;
 od_push(&observer_trace,&r);
}
int ma_observer_trace_packet(uint8_t*p,uint32_t build,unsigned page){
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||!observer_trace.frozen||page>=OD_PAGES)return 0;
 if(!observer_trace.sealed){
  observer_trace.blob.header.firmware=build;observer_trace.blob.header.crc=0;
  observer_trace.blob.header.crc=uv3_crc32c((const uint8_t*)&observer_trace.blob,OD_BYTES);
  observer_trace.sealed=1;
 }
 memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=OD_WIRE;p[3]=1;p[4]=1;p[5]=(uint8_t)page;
 p[6]=OD_PAGES;unsigned len=page==OD_PAGES-1U?16U:(unsigned)OD_PAYLOAD;p[7]=(uint8_t)len;
 memcpy(p+8,((const uint8_t*)&observer_trace.blob)+OD_PAYLOAD*page,len);p[38]=1;uv3_seal(p);return 1;
}
