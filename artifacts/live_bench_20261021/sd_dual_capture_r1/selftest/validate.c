#include <stdio.h>
#include "pulse_record.h"
int main(void){unsigned char p[320];if(fread(p,1,320,stdin)!=320)return 2;return bp_record_valid(p)?0:1;}
