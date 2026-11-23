#ifndef MIC_FPU_SQRT_DISPATCH_H
#define MIC_FPU_SQRT_DISPATCH_H
#include <stdint.h>
#include <string.h>

/* GNU ld --wrap applies to the library's internal square-root calls too.
 * Keep the original implementation available for every excluded condition.
 * No controller equation, norm expression, trip threshold, or timing guard
 * changes. Positive NORMAL binary32 inputs have a normal finite square root.
 * For round-to-nearest/even, hardware VSQRT and the library's correctly rounded
 * result have the same binary32 value. Special values/modes use the old code.
 */
#ifndef MIC_SQRT_FPSCR
static inline uint32_t mic_sqrt_fpscr(void){
 uint32_t v;__asm__ volatile("vmrs %0, fpscr":"=r"(v));return v;
}
#define MIC_SQRT_FPSCR() mic_sqrt_fpscr()
#endif
#ifndef MIC_SQRT_HW
static inline float mic_sqrt_hw(float x){
 float y;__asm__ volatile("vsqrt.f32 %0, %1":"=t"(y):"t"(x));return y;
}
#define MIC_SQRT_HW(x) mic_sqrt_hw(x)
#endif
#ifdef __cplusplus
extern "C" {
#endif
float __real___ieee754_sqrtf(float x);
float __wrap___ieee754_sqrtf(float x){
 uint32_t bits;memcpy(&bits,&x,sizeof(bits));
 /* FPSCR RMode[23:22] and FZ[24] must have their original IEEE/RNE setting.
    Raw bits classify without arithmetic on signalling NaNs or negative zero. */
 if(bits>=0x00800000U&&bits<0x7f800000U&&!(MIC_SQRT_FPSCR()&0x01c00000U))
  return MIC_SQRT_HW(x);
 return __real___ieee754_sqrtf(x);
}
#ifdef __cplusplus
}
#endif
#endif
