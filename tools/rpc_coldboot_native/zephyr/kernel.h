#pragma once
#include <Arduino.h>
#define K_MSEC(n) (n)
#define K_FOREVER (-1)
#define K_NO_WAIT 0
struct k_mutex{int held=0;};
inline void k_mutex_init(k_mutex*m){m->held=0;}
inline int k_mutex_lock(k_mutex*m,int wait){if(m->held){delay(wait>0?wait:1);return -1;}m->held=1;return 0;}
inline void k_mutex_unlock(k_mutex*m){m->held=0;}
inline void k_msleep(unsigned n){delay(n);}
inline void k_yield(){delay(1);}
struct k_thread{};
using k_tid_t=k_thread*;
using k_thread_stack_t=char;
inline char fake_stack[2048];
inline unsigned fake_thread_creates=0;
inline k_thread_stack_t*k_thread_stack_alloc(size_t,int){return fake_stack;}
inline k_tid_t k_thread_create(k_thread*t,char*,size_t,void(*)(void*,void*,void*),void*,void*,void*,int,int,int){++fake_thread_creates;return t;}
inline void k_thread_name_set(k_tid_t,const char*){}
