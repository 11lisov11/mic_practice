#include <cstdio>
#include <identify_core.h>
int main(){
mi_state state{};mi_config config{};config.run_id=4184657600U;config.kind=MI_DC;
config.amplitude=.06f;config.rs=12.23f;config.duration_ms=3000;
ma_geometry geometry{5312,5184,771,112,240,228};
if(!mi_begin(&state,&config,2245335241U))return 1;
mi_sample sample{};sample.bus=320;sample.arr=5312;sample.valid=1;
ma_output output{};int fault=0;unsigned calls=0;
sample.cycles=2308654283U;sample.epoch=3043688U;sample.ia=-0.0095935810f;sample.ib=0.0166165698f;sample.ccr[0]=2685;sample.ccr[1]=2627;sample.ccr[2]=2627;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308664905U;sample.epoch=3043689U;sample.ia=-0.0287807431f;sample.ib=0.0498497093f;sample.ccr[0]=2684;sample.ccr[1]=2628;sample.ccr[2]=2628;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308675531U;sample.epoch=3043690U;sample.ia=-0.1822780394f;sample.ib=-0.0387719961f;sample.ccr[0]=2681;sample.ccr[1]=2631;sample.ccr[2]=2631;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308686156U;sample.epoch=3043691U;sample.ia=0.0863422292f;sample.ib=-0.0166165698f;sample.ccr[0]=2682;sample.ccr[1]=2630;sample.ccr[2]=2630;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308696780U;sample.epoch=3043692U;sample.ia=0.0671550672f;sample.ib=-0.0166165698f;sample.ccr[0]=2692;sample.ccr[1]=2620;sample.ccr[2]=2620;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308707402U;sample.epoch=3043693U;sample.ia=0.0000000000f;sample.ib=0.0000000000f;sample.ccr[0]=2675;sample.ccr[1]=2637;sample.ccr[2]=2637;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308718026U;sample.epoch=3043694U;sample.ia=-0.0479679051f;sample.ib=-0.0055388566f;sample.ccr[0]=2676;sample.ccr[1]=2636;sample.ccr[2]=2636;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308728649U;sample.epoch=3043695U;sample.ia=0.2494331066f;sample.ib=-0.0221554263f;sample.ccr[0]=2680;sample.ccr[1]=2632;sample.ccr[2]=2632;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308739274U;sample.epoch=3043696U;sample.ia=0.0479679051f;sample.ib=0.0276942829f;sample.ccr[0]=2683;sample.ccr[1]=2629;sample.ccr[2]=2629;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308749899U;sample.epoch=3043697U;sample.ia=-0.0191871620f;sample.ib=-0.0664662790f;sample.ccr[0]=2665;sample.ccr[1]=2647;sample.ccr[2]=2647;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
sample.cycles=2308760523U;sample.epoch=3043698U;sample.ia=0.6043956044f;sample.ib=0.0055388566f;sample.ccr[0]=2677;sample.ccr[1]=2635;sample.ccr[2]=2635;if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}
if(fault!=MI_BAD_CURRENT||state.active||!state.done||calls!=11)return 2;
printf("{\"fault\":%u,\"calls\":%u,\"done\":%u,\"active\":%u}\n",fault,calls,state.done,state.active);
}
