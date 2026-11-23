#include <Arduino.h>
#include <IWatchdog.h>
#include "lease.h"

// Dedicated spare Blue Pill only. Never flash this into the AIR Nucleo/Uno.
// PB12 -> isolated 3.3V/24V open-collector interface -> T3D DI2 (P101=-8).
// External 10k pulldown on PB12 ensures zero permit during reset/power loss.
static Lease lease;
static char input[65];
static unsigned used=0;
static uint32_t nextQ=0;

static void send_line(const char *kind,uint32_t value) {
  char body[24],line[40];
  snprintf(body,sizeof(body),"%s %08lX",kind,(unsigned long)value);
  snprintf(line,sizeof(line),"%s %04X\n",body,lease_crc(body));
  // USB backpressure must never stall the watchdog/output update.
  if (Serial.availableForWrite() >= int(strlen(line))) Serial.print(line);
}

static void receive_line(uint32_t now) {
  input[used]=0;
  if (!strcmp(input,"STOP")) {
    lease.stop();
    digitalWrite(PB12,LOW);
    send_line("OFF",0);
    return;
  }
  if (used!=17 || strncmp(input,"ACK ",4) || input[12]!=' ') return;
  for (unsigned i=4;i<17;i++) {
    if(i==12) continue;
    if(!((input[i]>='0'&&input[i]<='9')||(input[i]>='A'&&input[i]<='F'))) return;
  }
  uint16_t received=strtoul(input+13,nullptr,16);
  input[12]=0;
  if(lease_crc(input)!=received) return;
  uint32_t value=strtoul(input+4,nullptr,16);
  if(lease.reply(value,now)) send_line("OK",value);
}

void setup() {
  digitalWrite(PB12,LOW); pinMode(PB12,OUTPUT);
  IWatchdog.begin(500000);  // Independent hardware reset; measure LSI tolerance on the board.
  Serial.begin(115200);
  nextQ=millis();
}

void loop() {
  uint32_t now=millis();
  digitalWrite(PB12,lease.permit(now)?HIGH:LOW);
  IWatchdog.reload();
  unsigned budget=128;
  while(budget-- && Serial.available()) {
    int ch=Serial.read();
    if(ch=='\n') { receive_line(millis()); used=0; }
    else if(ch!='\r') {
      if(used<64) input[used++]=char(ch);
      else { used=0; lease.stop(); }
    }
  }
  now=millis();
  if(int32_t(now-nextQ)>=0) { lease.issue(now); send_line("Q",lease.nonce); nextQ=now+125; }
  digitalWrite(PB12,lease.permit(now)?HIGH:LOW);
}
