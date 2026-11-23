
#include <cstdio>
#include "current_core.h"
static const unsigned bias[4]={2068,2068,2067,2069},lo[4]={2054,2052,2052,2056},hi[4]={2103,2085,2082,2102};
int main(){cm_core s;cm_init(&s);
 for(unsigned i=0;i<8000+512*8;++i){unsigned pair=(i&1)?2:0,p=cm_path1(pair),q=cm_path2(pair);
 unsigned a=bias[p],b=bias[q];if(s.count[p]==10)a=lo[p];if(s.count[p]==100)a=hi[p];
 if(s.count[q]==10)b=lo[q];if(s.count[q]==100)b=hi[q];cm_sample(&s,i/16,0,pair,a,b,0,1);}
 printf("{\"failed\":%s,\"attempts\":%u,\"stable\":%u,\"u1_span\":%u,\"w2_span\":%u}",
 s.zero_bad&&!s.zero_ready?"true":"false",s.zero_attempts,s.zero_stable,s.zero_high[0]-s.zero_low[0],s.zero_high[3]-s.zero_low[3]);}
