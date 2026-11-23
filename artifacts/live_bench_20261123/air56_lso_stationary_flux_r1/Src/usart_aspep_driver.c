
/**
  ******************************************************************************
  * @file    usart_aspep_driver.c
  * @author  Motor Control SDK Team, ST Microelectronics
  * @brief   This file provides firmware functions that implement the uart driver for the aspep protocol
  *
  *
  ******************************************************************************
  * @attention
  *
  * <h2><center>&copy; Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.</center></h2>
  *
  * This software component is licensed by ST under Ultimate Liberty license
  * SLA0044, the "License"; You may not use this file except in compliance with
  * the License. You may obtain a copy of the License at:
  *                             www.st.com/SLA0044
  *
  ******************************************************************************
  */

#include <stdint.h>
#include "mc_stm_types.h"
#include "usart_aspep_driver.h"
#include "aspep.h"

// USART A uses one continuously running RX channel. Only MC_Scheduler
// consumes the ring and changes ASPEP receive spans.
enum { RX_RING_SIZE = 1024U, RX_RING_MASK = RX_RING_SIZE - 1U };
static uint8_t rx_ring[RX_RING_SIZE];
static uint8_t *rx_target;
static uint16_t rx_size, rx_tail, rx_head_previous;
static uint32_t rx_last_poll, rx_last_progress;
static bool rx_resync;
static bool rx_initialized;

// At 1,843,200 baud an 8N1 sender takes 5.55 ms to lap the ring.
// The largest pending span is 130 bytes (< 0.71 ms on the wire).
// Drop ambiguous data if the 0.5 ms scheduler was absent for 4 ms.
#define RX_MAX_PAUSE (SystemCoreClock / 250U)
#define RX_PARTIAL_TIMEOUT (SystemCoreClock / 40U)
#define RX_WIRE_ERRORS (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)
#define RX_CLEAR_ERRORS (USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF)

static uint16_t UASPEP_Head(const UASPEP_Handle_t *hw)
{
  return (uint16_t)((RX_RING_SIZE - LL_DMA_GetDataLength(hw->rxDMA, hw->rxChannel)) & RX_RING_MASK);
}

static void UASPEP_StartRing(UASPEP_Handle_t *hw)
{
  LL_DMA_DisableChannel(hw->rxDMA, hw->rxChannel);
  LL_DMA_ClearFlag_GI2(hw->rxDMA);
  LL_DMA_SetMode(hw->rxDMA, hw->rxChannel, LL_DMA_MODE_CIRCULAR);
  LL_DMA_SetMemoryAddress(hw->rxDMA, hw->rxChannel, (uint32_t)rx_ring);
  LL_DMA_SetDataLength(hw->rxDMA, hw->rxChannel, RX_RING_SIZE);
  LL_DMA_EnableChannel(hw->rxDMA, hw->rxChannel);
}

void UASPEP_TX_INIT(UASPEP_Handle_t *pHandle);
void UASPEP_RX_INIT(UASPEP_Handle_t *pHandle);

/** @addtogroup MCSDK
  * @{
  */

/** @addtogroup MCP
  * @{
  */

/**
  * @brief  Initialization of the Hardware used for data transmission and reception.
  *
  * @param  pHandle Handler of the current instance of the UASPEP component
  */
void UASPEP_INIT(void *pHWHandle)
{
  UASPEP_Handle_t *pHandle = (UASPEP_Handle_t *)pHWHandle; //cstat !MISRAC2012-Rule-11.5
  UASPEP_RX_INIT(pHandle);
  UASPEP_TX_INIT(pHandle);
}

/**
  * @brief  Configures the Hardware used for data transmission to controller.
  *
  * @param  pHandle Handler of the current instance of the UASPEP component
  */
void UASPEP_TX_INIT(UASPEP_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_USA_ASP_DRV
  if (NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    /* Enable DMA UART */
    LL_USART_ClearFlag_TC(pHandle->USARTx);
    LL_USART_EnableIT_TC(pHandle->USARTx);

    /* Enable DMA UART to start the TX request */
    LL_USART_EnableDMAReq_TX(pHandle->USARTx);

    /* Write the USART_TDR register address in the DMA control register to configure it as
     * the destination of the transfer */
    //cstat !MISRAC2012-Rule-11.4
    LL_DMA_SetPeriphAddress(pHandle->txDMA, pHandle->txChannel, (uint32_t)&pHandle->USARTx->TDR);

    /* Clear UART ISR */
    LL_USART_ClearFlag_TC(pHandle->USARTx);

    /* DMA end of transfer on UART TX channel completion is not activated */
    /* We prefer to activate UART TC itself to avoid to trig IT while queued data are still to be transmitted */
#ifdef NULL_PTR_CHECK_USA_ASP_DRV
  }
#endif
}

/**
  * @brief  Configures the Hardware used for data reception from controller.
  *
  * @param  pHandle Handler of the current instance of the UASPEP component
  */
void UASPEP_RX_INIT(UASPEP_Handle_t *pHandle)
{
#ifdef NULL_PTR_CHECK_USA_ASP_DRV
  if (NULL == pHandle)
  {
    /* Nothing to do */
  }
  else
  {
#endif
    LL_DMA_SetPeriphAddress(pHandle->rxDMA, pHandle->rxChannel,
                            (uint32_t)&pHandle->USARTx->RDR);
    pHandle->USARTx->ICR = RX_CLEAR_ERRORS;
    UASPEP_StartRing(pHandle);
    LL_USART_EnableDMAReq_RX(pHandle->USARTx);
    rx_last_poll = rx_last_progress = DWT->CYCCNT;
    rx_initialized = true;
#ifdef NULL_PTR_CHECK_USA_ASP_DRV
  }
#endif
}

/**
  * @brief  Configures data transmission.
  *
  * @param  pHWHandle Hardware components chosen for communication
  * @param  data Data to be transmitted to controller
  * @param  length Length of the data to be transmitted
  */
void UASPEP_CFG_TRANSMISSION(void *pHWHandle, void *data, uint16_t length)
{
  UASPEP_Handle_t *pHandle = (UASPEP_Handle_t *)pHWHandle; //cstat !MISRAC2012-Rule-11.5
  if (0U == LL_DMA_IsEnabledChannel(pHandle->txDMA, pHandle->txChannel))
  {
    //cstat !MISRAC2012-Rule-11.4 !MISRAC2012-Rule-11.6
    LL_DMA_SetMemoryAddress(pHandle->txDMA, pHandle->txChannel, (uint32_t)data);
    LL_DMA_SetDataLength(pHandle->txDMA, pHandle->txChannel, length);
    LL_DMA_EnableChannel(pHandle->txDMA, pHandle->txChannel);
  }
  else
  {
    /* Nothing to do */
  }
}

/**
  * @brief  Configures data reception.
  *
  * @param  pHWHandle Hardware components chosen for communication
  * @param  buffer Buffer which will receive the communicated data
  * @param  length Length of the received data
  */
void UASPEP_CFG_RECEPTION(void *pHWHandle, void* buffer, uint16_t length)
{
  (void)pHWHandle;
  rx_target = buffer;
  rx_size = length;
}

/**
  * @brief  Sets IDLE state : no transmission on going.
  *
  * @param  pHandle Handler of the current instance of the UASPEP component
  */
void UASPEP_IDLE_ENABLE(void *pHWHandle)
{
  (void)pHWHandle;
  rx_resync = true;
}

void UASPEP_Poll(ASPEP_Handle_t *protocol)
{
  if (!rx_initialized) { return; }
  UASPEP_Handle_t *hw = (UASPEP_Handle_t *)protocol->ASPEPIp;
  const uint32_t now = DWT->CYCCNT;
  const uint32_t elapsed = now - rx_last_poll;
  rx_last_poll = now;
  const uint16_t head = UASPEP_Head(hw);

  if (LL_DMA_IsActiveFlag_TE2(hw->rxDMA))
  {
    UASPEP_StartRing(hw);
    rx_head_previous = rx_tail = 0U;
    protocol->NewPacketAvailable = false;
    rx_resync = true;
    return;
  }
  const uint16_t arrived = (head - rx_head_previous) & RX_RING_MASK;
  const uint16_t previous_pending = (rx_head_previous - rx_tail) & RX_RING_MASK;
  rx_head_previous = head;
  if (arrived) { rx_last_progress = now; }

  if ((hw->USARTx->ISR & RX_WIRE_ERRORS) || elapsed >= RX_MAX_PAUSE ||
      arrived + previous_pending >= RX_RING_SIZE)
  {
    hw->USARTx->ICR = RX_CLEAR_ERRORS;
    protocol->NewPacketAvailable = false;
    rx_resync = true;
    rx_tail = head;
    rx_last_progress = now;
    return;
  }
  if (rx_resync)
  {
    rx_tail = head;
    // A full scheduler interval with no new bytes provides a quiet boundary.
    if (!arrived)
    {
      rx_resync = false;
      protocol->NewPacketAvailable = false;
      ASPEP_HWReset(protocol);
    }
    return;
  }

  // ASPEP arms the payload from the header callback and the next header
  // after the scheduler consumes the packet. Preserve both boundaries.
  for (unsigned span = 0; span < 2U && rx_size; ++span)
  {
    const uint16_t pending = (head - rx_tail) & RX_RING_MASK;
    if (pending < rx_size)
    {
      if ((pending || protocol->ASPEP_TL_State == WAITING_PAYLOAD) &&
          now - rx_last_progress >= RX_PARTIAL_TIMEOUT)
      {
        rx_resync = true;
        rx_tail = head;
      }
      return;
    }
    const uint16_t count = rx_size;
    __DMB();
    for (uint16_t i = 0; i < count; ++i)
    {
      rx_target[i] = rx_ring[(rx_tail + i) & RX_RING_MASK];
    }
    if ((hw->USARTx->ISR & RX_WIRE_ERRORS) ||
        LL_DMA_IsActiveFlag_TE2(hw->rxDMA) ||
        DWT->CYCCNT - now >= SystemCoreClock / 2000U)
    {
      rx_resync = true;
      return;
    }
    rx_tail = (rx_tail + count) & RX_RING_MASK;
    rx_size = 0;
    ASPEP_HWDataReceivedIT(protocol);
  }
}


/**
  * @}
  */

/**
  * @}
  */
/************************ (C) COPYRIGHT 2026 STMicroelectronics *****END OF FILE****/

