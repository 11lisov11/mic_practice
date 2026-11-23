
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <fstream>
#include <string>
struct String : std::string {
    using std::string::string;
    using std::string::operator=;
    explicit String(unsigned long n) : std::string(std::to_string(n)) {}
};
enum { PC_WIRE_BYTES = 1024, OD_WIRE_BYTES = 1888, BP_STATUS_PWM_ACTIVE = 32,
       NH_META_BYTES = 524, NH_ROW = 22 };
static bool g_pwm_enabled, g_pwm_outputs_active;
static unsigned g_bp_status;
static struct { bool complete; uint8_t data[PC_WIRE_BYTES]; } g_peak;
static struct { bool complete; uint8_t data[OD_WIRE_BYTES]; } g_observer_trace;
struct History {
    bool complete;
    uint8_t meta[524], rows[22], checkpoints[4];
    uint32_t count, epoch;
};
static History g_start_history;
bool nhr_exact(const History *) { return true; }
uint32_t odw_u32(const uint8_t *p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
static String rpc_capture_page(uint32_t part, uint32_t page) {
  // Called by rpc_history while holding g_control_owner, after its RUN guard.
  const bool adc = part == 3U;
  if (!(adc ? g_peak.complete : g_observer_trace.complete)) return "ERR NOT_COMPLETE";
  const uint8_t *data = adc ? g_peak.data : g_observer_trace.data;
  const unsigned size = adc ? (unsigned)PC_WIRE_BYTES : (unsigned)OD_WIRE_BYTES;
  const unsigned chunk = 192U;
  if (page >= (size + chunk - 1U) / chunk) return "ERR PAGE";
  const unsigned offset = page * chunk;
  const unsigned count = size - offset < chunk ? size - offset : chunk;
  String reply;
  reply.reserve(440);
  reply = "CP ";
  reply += String((unsigned long)part);
  reply += " "; reply += String((unsigned long)page);
  reply += " "; reply += String((unsigned long)size);
  reply += " "; reply += String((unsigned long)odw_u32(data + 8));
  reply += " "; reply += String((unsigned long)odw_u32(data + 60));
  reply += " ";
  const char hex[] = "0123456789abcdef";
  for (unsigned i = offset; i < offset + count; ++i) {
    reply += hex[data[i] >> 4];
    reply += hex[data[i] & 15];
  }
  return reply;
}

static String rpc_history(uint32_t part,uint32_t page) {
#if USE_ROUTER_BRIDGE
  ScopedControlLock<ControlMutex> owner(g_control_owner);
#endif
  if(g_pwm_enabled||g_pwm_outputs_active||(g_bp_status&BP_STATUS_PWM_ACTIVE))return "ERR RUN";
  if (part == 3U || part == 4U) return rpc_capture_page(part, page);
  if(!g_start_history.complete)return "ERR NOT_COMPLETE";
  const uint8_t*data=nullptr;unsigned size=0;
  if(part==0){data=g_start_history.meta;size=NH_META_BYTES;}
  else if(part==1){data=(const uint8_t*)g_start_history.rows;size=g_start_history.count*NH_ROW;}
  else if(part==2){data=(const uint8_t*)g_start_history.checkpoints;size=(g_start_history.count/16U)*4U;}
  else return "ERR PART";
  const unsigned chunk=192U,offset=page*chunk;
  if(page>1024U||(size?offset>=size:page!=0U))return "ERR PAGE";
  unsigned len=size-offset;if(len>chunk)len=chunk;
  String out;out.reserve(480);out="NH ";out+=String((unsigned long)g_start_history.epoch);
  out+=" ";out+=String(nhr_exact(&g_start_history)?1:0);out+=" ";out+=String((unsigned long)size);out+=" ";
  if(!len)out+="-";
  const char hex[]="0123456789abcdef";
  for(unsigned i=0;i<len;++i){out+=hex[data[offset+i]>>4];out+=hex[data[offset+i]&15];}return out;
}

int main(int argc, char **argv) {
    g_peak.complete = std::ifstream(argv[1], std::ios::binary)
        .read(reinterpret_cast<char *>(g_peak.data), PC_WIRE_BYTES).good();
    g_observer_trace.complete = std::ifstream(argv[2], std::ios::binary)
        .read(reinterpret_cast<char *>(g_observer_trace.data), OD_WIRE_BYTES).good();
    for (unsigned part = 3; part <= 4; ++part) {
        unsigned size = part == 3 ? PC_WIRE_BYTES : OD_WIRE_BYTES;
        for (unsigned page = 0; page < (size + 191) / 192; ++page)
            std::cout << rpc_history(part, page) << "\n";
    }
    std::cout << rpc_history(3, UINT32_MAX) << "\n" << rpc_history(0, 0) << "\n";
    g_start_history.complete = true;
    g_start_history.epoch = 77;
    std::cout << rpc_history(0, 0) << "\n";
    g_pwm_enabled = true;
    std::cout << rpc_history(3, 0) << "\n";
    g_pwm_enabled = false;
    g_pwm_outputs_active = true;
    std::cout << rpc_history(4, 0) << "\n";
    g_pwm_outputs_active = false;
    g_bp_status = BP_STATUS_PWM_ACTIVE;
    std::cout << rpc_history(3, 0) << "\n";
}
