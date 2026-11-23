#pragma once
using atomic_t=int;
#define ATOMIC_INIT(n) (n)
inline bool atomic_cas(atomic_t*p,int old,int next){if(*p!=old)return false;*p=next;return true;}
