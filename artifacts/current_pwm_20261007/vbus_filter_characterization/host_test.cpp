
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#define __weak
#define MC_UNDER_VOLT 4U
#define MC_OVER_VOLT 2U
#define MC_NO_FAULTS 0U
struct BusVoltageSensor_Handle_t { uint16_t ConversionFactor, LatestConv, AvBusVoltage_d, FaultState; };
struct RDivider_Handle_t {
 BusVoltageSensor_Handle_t _Super;
 uint16_t OverVoltageThreshold, OverVoltageThresholdLow;
 bool OverVoltageHysteresisUpDir;
 uint16_t UnderVoltageThreshold;
};
uint16_t RVBS_CheckFaultState(RDivider_Handle_t *pHandle)
{
  uint16_t fault;
  /* If both thresholds are equal, single threshold feature is used */
  if (pHandle->OverVoltageThreshold == pHandle->OverVoltageThresholdLow)
  {
    if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
    {
      fault = MC_OVER_VOLT;
    }
    else if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else
    {
      fault = MC_NO_ERROR;
    }
  }
  else
  {
    /* If both thresholds are different, hysteresis feature is used (Brake mode) */
    if (pHandle->_Super.AvBusVoltage_d < pHandle->UnderVoltageThreshold)
    {
      fault = MC_UNDER_VOLT;
    }
    else if ( false == pHandle->OverVoltageHysteresisUpDir )
    {
      if (pHandle->_Super.AvBusVoltage_d < pHandle->OverVoltageThresholdLow)
      {
        pHandle->OverVoltageHysteresisUpDir = true;
        fault = MC_NO_ERROR;
      }
      else{
        fault = MC_OVER_VOLT;
      }
    }
    else
    {
      if (pHandle->_Super.AvBusVoltage_d > pHandle->OverVoltageThreshold)
      {
        pHandle->OverVoltageHysteresisUpDir = false;
        fault = MC_OVER_VOLT;
      }
      else{
        fault = MC_NO_ERROR;
      }
    }
  }
  return (fault);
}
__weak uint16_t RVBS_CalcAvVbus(RDivider_Handle_t *pHandle, uint16_t rawValue)
{
  uint16_t tempValue = 0U;
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  if (MC_NULL == pHandle)
  {
    /* Nothing to do. */
  }
  else
  {
#endif
    uint16_t hAux = rawValue;

    if (0xFFFFU == hAux)
    {
      /* Nothing to do */
    }
    else
    {
      pHandle->_Super.AvBusVoltage_d += (hAux - pHandle->_Super.AvBusVoltage_d) >> 8U;
      pHandle->_Super.FaultState = RVBS_CheckFaultState(pHandle);
      tempValue = pHandle->_Super.FaultState;
    }
#ifdef NULL_PTR_CHECK_RDIV_BUS_VLT_SNS
  }
#endif
  return (tempValue);
}
__weak uint16_t VBS_GetAvBusVoltage_V(const BusVoltageSensor_Handle_t *pHandle)
{
  uint32_t temp;
#ifdef NULL_PTR_CHECK_BUS_VOLT
  if (MC_NULL == pHandle)
  {
    temp = 0U;
  }
  else
  {
#endif
    temp = (uint32_t)(pHandle->AvBusVoltage_d);
    temp *= pHandle->ConversionFactor;
    temp /= 65536U;
#ifdef NULL_PTR_CHECK_BUS_VOLT
  }
#endif
  return ((uint16_t)temp);
}

int main() {
 unsigned cases=0, max_error=0; double max_display_error=0;
 for (unsigned code=0; code<4096; ++code) {
  const uint16_t raw=code<<4;
  for (unsigned init : {0U,65535U}) {
   RDivider_Handle_t h{}; h._Super.ConversionFactor=416;
   h._Super.AvBusVoltage_d=init;
   h.OverVoltageThreshold=h.OverVoltageThresholdLow=65000;
   for (unsigned n=0; n<4096; ++n) RVBS_CalcAvVbus(&h,raw);
   unsigned error=raw-h._Super.AvBusVoltage_d;
   assert(h._Super.AvBusVoltage_d<=raw && error<=255);
   if (init==65535) assert(error==0);
   if (error>max_error) max_error=error;
   double lost=raw*double(416)/65536-VBS_GetAvBusVoltage_V(&h._Super);
   if (lost>max_display_error) max_display_error=lost;
   auto previous=h._Super.AvBusVoltage_d;
   RVBS_CalcAvVbus(&h,0xFFFF);
   assert(h._Super.AvBusVoltage_d==previous);
   ++cases;
  }
 }
 std::printf("{\"pass\":true,\"constant_input_cases\":%u,\"max_filter_lag_u16\":%u,"
             "\"max_filter_and_integer_display_loss_v\":%.9f}\n",cases,max_error,max_display_error);
}
