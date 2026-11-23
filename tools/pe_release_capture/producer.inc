bool mic_encoder_release_packet(uint8_t*p,unsigned slot,unsigned page){
  if(slot>1||page>=PR_PAGES||!(fault_ready&(1U<<slot)))return false;
  const sr_probe*q=&release_probe[slot];
  if(q->active||(!q->count&&!q->flags))return false;
  uint32_t r[PR_WORDS]={0};const uint32_t*parent=fault_record[slot];
  r[0]=PR_MAGIC;r[1]=PR_PEER;r[2]=uv3_crc32c((const uint8_t*)parent,FC_BYTES);
  r[3]=(uint32_t)q->flags|((uint32_t)q->count<<8)|((uint32_t)sr_result(q)<<16);
  r[4]=q->terminal_cycles;r[5]=q->terminal_gpio;r[6]=parent[32];r[7]=parent[2];
  for(unsigned i=0;i<q->count;i++){
    const sr_sample*s=&q->after[i];unsigned n=8+5*i;
    r[n]=s->cycles;r[n+1]=s->isr;r[n+2]=s->cr1;r[n+3]=s->cr2;r[n+4]=s->gpio;
  }
  r[23]=release_park_cycles[slot];r[24]=uv3_crc32c((const uint8_t*)r,96);
  pr_packet(p,r,slot,page,uv3_crc32c((const uint8_t*)r,PR_BYTES));return true;
}
