
#include <string>
#include <cstdio>
#include <cstdint>
#include <cmath>
using std::isnan;using std::isinf;
struct String {
 std::string text;
 String()=default;String(const char*s):text(s){}String(char c):text(1,c){}
 String(unsigned long x):text(std::to_string(x)){}String(unsigned x):text(std::to_string(x)){}String(int x):text(std::to_string(x)){}
 void reserve(unsigned x){text.reserve(x);}
 String&operator+=(const String&s){text+=s.text;return *this;}
 String&operator+=(const char*s){text+=s;return *this;}
 String&operator+=(char c){text+=c;return *this;}
};
bool g_manual_scalar_mode=true,g_manual_coast_down=false,g_manual_reference_valid=true,g_manual_bus_hold=true;
uint16_t g_manual_accel_centi=200,g_manual_decel_centi=50;
float g_manual_reference_hz=23.4f;
static String format_fixed(float value, uint8_t decimals) {
  if (isnan(value)) return String("nan");
  if (isinf(value)) return value < 0.0f ? String("-inf") : String("inf");

  bool negative = value < 0.0f;
  float mag = negative ? -value : value;
  uint32_t scale = 1U;
  for (uint8_t i = 0; i < decimals; ++i) {
    scale *= 10U;
  }
  uint32_t scaled = (uint32_t)(mag * (float)scale + 0.5f);
  uint32_t whole = (scale > 0U) ? (scaled / scale) : scaled;
  uint32_t frac = (scale > 0U) ? (scaled % scale) : 0U;

  String out;
  out.reserve(20);
  if (negative && (whole != 0U || frac != 0U)) {
    out += '-';
  }
  out += String((unsigned long)whole);
  if (decimals == 0U) {
    return out;
  }
  out += '.';
  uint32_t div = scale / 10U;
  while (div > 0U) {
    out += (char)('0' + ((frac / div) % 10U));
    div /= 10U;
  }
  return out;
}
static String manual_status_fields(uint32_t bp_age) {
  String s;
  s.reserve(256);
  s += " manual_scalar_capable=1";
  s += " manual_run_mode="; s += String(g_manual_scalar_mode ? 1 : 0);
  s += " accel_hz_per_s="; s += format_fixed(g_manual_accel_centi*0.01f, 2);
  s += " decel_hz_per_s="; s += format_fixed(g_manual_decel_centi*0.01f, 2);
  s += " downmode_coast="; s += String(g_manual_coast_down ? 1 : 0);
  s += " mc_frequency_reference_hz="; s += format_fixed(g_manual_reference_hz, 2);
  s += " mc_frequency_reference_valid="; s += String(g_manual_reference_valid && bp_age < 300U ? 1 : 0);
  s += " mc_decel_bus_hold="; s += String(g_manual_bus_hold ? 1 : 0);
  return s;
}
int main(){
 for(unsigned age : {20U,300U}) std::puts(manual_status_fields(age).text.c_str());
 g_manual_reference_valid=false;std::puts(manual_status_fields(20).text.c_str());
}
