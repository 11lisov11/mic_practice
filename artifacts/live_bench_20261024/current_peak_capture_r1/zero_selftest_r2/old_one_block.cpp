
#include <cstdio>
#include "current_core.h"
int main(){cm_core s;cm_init(&s);for(unsigned n=0;n<16000;++n){unsigned p=(n&1)?2:0;
 unsigned raw=2048;if(n==8201)raw+=49;cm_sample(&s,n/16,0,p,raw,2048,0,1);}
 printf("{\"old_failure_reproduced\":%s}",s.zero_bad&&!s.zero_ready?"true":"false");}
