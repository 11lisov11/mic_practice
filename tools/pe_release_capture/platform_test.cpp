#include "nucleo_encoder.c"
#include <cassert>
#include <cstdio>
#include <cstring>
static void step(unsigned us){test_dwt.CYCCNT=us*170;mic_encoder_poll();}
static void start(){step(0);step(5);step(10);step(15);assert(enc.state==1);I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_TXIS|EC_BUSYF;step(20);assert(enc.state==2);}
static void emit(const uint8_t*b,unsigned n){for(unsigned i=0;i<n;i++)std::printf("%02x",b[i]);}
int main(int argc,char**argv){
 const char*mode=argc>1?argv[1]:"high";
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x300;test_i2c.ISR.value=1;
 mic_encoder_init();test_tick=5;start();TIM1->BDTR=32768;test_gpio.IDR=0x50;
 I2C1->ISR.value=0x8011;step(30);assert(enc.recovering&&fault_pending==3&&!fault_ready);
 test_gpio.IDR=0x250;step(130);assert(I2C1->CR2&I2C_CR2_STOP);
 mock_release_scl=strcmp(mode,"low")!=0;
 step(535);assert(enc.resets==1&&!enc.recovering&&fault_ready==3&&release_probe[1].count==1);
 assert((fault_record[1][4]>>26)==26&&fault_record[1][35]==0x8001&&fault_record[1][36]==0x201&&fault_record[1][38]==0x250);
 assert(release_probe[1].after[0].cr1==0x200&&!(release_probe[1].after[0].isr&EC_BUSYF));
 assert(!(release_probe[1].after[0].cr2&(I2C_CR2_START|I2C_CR2_STOP)));
 uint32_t parent[40];memcpy(parent,fault_record[1],sizeof(parent));uint8_t packet[UV3_FRAME];
 assert(!mic_encoder_release_packet(packet,1,0));
 if(!strcmp(mode,"late"))step(1073);
 else if(!strcmp(mode,"timeout"))step(1536);
 else if(!strcmp(mode,"cancel")){I2C1->CR1|=1;step(540);}
 else {step(540);assert(release_probe[1].count==2&&!release_probe[1].complete);step(555);}
 assert(!release_probe[1].active&&!memcmp(parent,fault_record[1],sizeof(parent)));
 pr_receiver receiver{};uint32_t parent_crc=uv3_crc32c((const uint8_t*)parent,FC_BYTES);
 unsigned frames=0;
 for(unsigned page=0;page<PR_PAGES;page++){
  assert(mic_encoder_release_packet(packet,1,page));assert(uv3_crc_ok(packet));
  for(unsigned j=0;j<UV3_FRAME;j++){
   uint8_t b[UV3_FRAME];memcpy(b,packet,UV3_FRAME);b[j]^=1;pr_receiver bad{};
   assert(!pr_receive(&bad,b,PR_PEER,true));
  }
  assert(pr_receive(&receiver,packet,PR_PEER,true));++frames;
 }
 assert(receiver.slot[1].valid&&pr_linked(&receiver.slot[1],(const uint8_t*)parent,parent_crc,true));
 assert(!pr_linked(&receiver.slot[1],(const uint8_t*)parent,parent_crc^1,true));
 assert(!pr_linked(&receiver.slot[1],(const uint8_t*)parent,parent_crc,false));
 assert(!pr_receive(&receiver,packet,2026102704,true));assert(!pr_receive(&receiver,packet,PR_PEER,false));
 uint8_t published[PR_BYTES];memcpy(published,receiver.slot[1].bytes,PR_BYTES);
 // Resealed malformed pages still fail semantic framing checks.
 uint8_t malformed[UV3_FRAME];memcpy(malformed,packet,UV3_FRAME);malformed[18]=1;uv3_seal(malformed);
 assert(!pr_receive(&receiver,malformed,PR_PEER,true));
 memcpy(malformed,packet,UV3_FRAME);malformed[5]=4;uv3_seal(malformed);assert(!pr_receive(&receiver,malformed,PR_PEER,true));
 memcpy(malformed,packet,UV3_FRAME);malformed[38]=2;uv3_seal(malformed);assert(!pr_receive(&receiver,malformed,PR_PEER,true));
 // A new outer CRC cannot conceal a bad payload CRC; old published data stays intact.
 uint32_t altered[PR_WORDS];memcpy(altered,published,PR_BYTES);altered[5]^=1;
 uint32_t altered_crc=uv3_crc32c((const uint8_t*)altered,PR_BYTES);
 for(unsigned page=0;page<PR_PAGES;page++){
  pr_packet(malformed,altered,1,page,altered_crc);
  bool okay=pr_receive(&receiver,malformed,PR_PEER,true);
  assert(page==PR_PAGES-1?!okay:okay);
 }
 assert(!memcmp(published,receiver.slot[1].bytes,PR_BYTES));
 // Correctly CRC-sealed, but inconsistent result/flags must also be rejected.
 memcpy(altered,published,PR_BYTES);altered[3]|=0x1000000U;altered[24]=uv3_crc32c((const uint8_t*)altered,96);
 assert(!pr_valid((const uint8_t*)altered));
 memcpy(altered,published,PR_BYTES);altered[8+2]|=1;altered[24]=uv3_crc32c((const uint8_t*)altered,96);
 assert(!pr_valid((const uint8_t*)altered));
 // Out-of-order pages are accepted only when the complete record shares one CRC.
 pr_receiver reordered{};
 for(unsigned page=PR_PAGES;page-->0;){assert(mic_encoder_release_packet(malformed,1,page));assert(pr_receive(&reordered,malformed,PR_PEER,true));}
 assert(reordered.slot[1].valid&&!memcmp(published,reordered.slot[1].bytes,PR_BYTES));
 packet[14]^=1;assert(!pr_receive(&receiver,packet,PR_PEER,true));assert(!memcmp(published,receiver.slot[1].bytes,PR_BYTES));
 unsigned expected=!strcmp(mode,"high")?SR_SCL_HIGH_AFTER_DISABLE:!strcmp(mode,"low")?SR_SCL_LOW_AFTER_DISABLE:!strcmp(mode,"late")?SR_SCL_HIGH_AFTER_DISABLE:SR_UNKNOWN;
 assert(sr_result(&release_probe[1])==expected);
 if(!strcmp(mode,"late"))assert((release_probe[1].flags&SR_LATE)&&release_probe[1].count==2&&release_probe[1].after[1].cycles==1073*170);
 uint8_t mask=fault_ready;uint32_t saved[40];memcpy(saved,fault_record[1],sizeof(saved));
 sr_probe probe=release_probe[1];
 // An unrelated later error must preserve both first-fault records.
 I2C1->ISR.value=EC_STOPF;auto i=io;enc.state=1;enc.stage=4;
 ec_finish(&enc,&i,7,2000*170,170000000,EC_SHORT,EC_STOPF);
 assert(fault_ready==mask&&!memcmp(saved,fault_record[1],sizeof(saved))&&!memcmp(&probe,&release_probe[1],sizeof(probe)));
 std::printf("{\"passed\":true,\"mode\":\"%s\",\"frames\":%u,\"result\":%u,\"record\":\"",mode,frames,expected);
 emit(published,PR_BYTES);std::printf("\",\"parent\":\"");emit((const uint8_t*)parent,FC_BYTES);std::puts("\"}");
}
