/* Execute the real diagnostic adapter against fake MMIO, never a device. */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
struct Timer {uint32_t BDTR=0x1000,CR1=0,DIER=0,ARR=5312,CCR1=2656,CCR2=2656,CCR3=2656,CCR4=4928,PSC=0,RCR=0,SR=0,EGR=0,SMCR=0,AF1=0,CCMR1=0,CCMR2=0,CCER=0;};
struct GPIO {uint32_t MODER=0,ODR=0,IDR=0,LCKR=0,AFR[2]={0,0};};
struct Dwt {uint32_t CYCCNT=0;};
static Timer tim,aux;static GPIO pa,pb,pc,pd;static Dwt dwt;
#define TIM1 (&tim)
#define TIM8 (&aux)
#define GPIOC (&pc)
#define GPIOD (&pd)
#define GPIOA (&pa)
#define GPIOB (&pb)
#define DWT (&dwt)
#define TIM_BDTR_MOE 0x8000U
#define TIM_BDTR_BKE 0x1000U
#define TIM_BDTR_OSSI 0x400U
#define TIM_BDTR_OSSR 0x800U
#define GPIO_PIN_0 1U
#define GPIO_PIN_1 2U
#define GPIO_PIN_7 128U
#define GPIO_PIN_8 256U
#define GPIO_PIN_9 512U
#define GPIO_PIN_10 1024U
#define GPIO_MODE_OUTPUT_PP 1U
#define GPIO_NOPULL 0U
#define GPIO_SPEED_FREQ_LOW 0U
#define GPIO_PIN_RESET 0U
#define __DMB() do{}while(0)
#define TIM_CR1_CEN_Pos           (0U)
#define TIM_CR1_CEN_Msk           (0x1UL << TIM_CR1_CEN_Pos)                   /*!< 0x00000001 */
#define TIM_CR1_CEN               TIM_CR1_CEN_Msk                              /*!<Counter enable */
#define TIM_CR1_UDIS_Pos          (1U)
#define TIM_CR1_UDIS_Msk          (0x1UL << TIM_CR1_UDIS_Pos)                  /*!< 0x00000002 */
#define TIM_CR1_UDIS              TIM_CR1_UDIS_Msk                             /*!<Update disable */
#define TIM_CR1_URS_Pos           (2U)
#define TIM_CR1_URS_Msk           (0x1UL << TIM_CR1_URS_Pos)                   /*!< 0x00000004 */
#define TIM_CR1_URS               TIM_CR1_URS_Msk                              /*!<Update request source */
#define TIM_CR1_OPM_Pos           (3U)
#define TIM_CR1_OPM_Msk           (0x1UL << TIM_CR1_OPM_Pos)                   /*!< 0x00000008 */
#define TIM_CR1_OPM               TIM_CR1_OPM_Msk                              /*!<One pulse mode */
#define TIM_CR1_DIR_Pos           (4U)
#define TIM_CR1_DIR_Msk           (0x1UL << TIM_CR1_DIR_Pos)                   /*!< 0x00000010 */
#define TIM_CR1_DIR               TIM_CR1_DIR_Msk                              /*!<Direction */
#define TIM_CR1_CMS_Pos           (5U)
#define TIM_CR1_CMS_Msk           (0x3UL << TIM_CR1_CMS_Pos)                   /*!< 0x00000060 */
#define TIM_CR1_CMS               TIM_CR1_CMS_Msk                              /*!<CMS[1:0] bits (Center-aligned mode selection) */
#define TIM_CR1_CMS_0             (0x1UL << TIM_CR1_CMS_Pos)                   /*!< 0x00000020 */
#define TIM_CR1_CMS_1             (0x2UL << TIM_CR1_CMS_Pos)                   /*!< 0x00000040 */
#define TIM_CR1_ARPE_Pos          (7U)
#define TIM_CR1_ARPE_Msk          (0x1UL << TIM_CR1_ARPE_Pos)                  /*!< 0x00000080 */
#define TIM_CR1_ARPE              TIM_CR1_ARPE_Msk                             /*!<Auto-reload preload enable */
#define TIM_CR1_CKD_Pos           (8U)
#define TIM_CR1_CKD_Msk           (0x3UL << TIM_CR1_CKD_Pos)                   /*!< 0x00000300 */
#define TIM_CR1_CKD               TIM_CR1_CKD_Msk                              /*!<CKD[1:0] bits (clock division) */
#define TIM_CR1_CKD_0             (0x1UL << TIM_CR1_CKD_Pos)                   /*!< 0x00000100 */
#define TIM_CR1_CKD_1             (0x2UL << TIM_CR1_CKD_Pos)                   /*!< 0x00000200 */
#define TIM_CR1_UIFREMAP_Pos      (11U)
#define TIM_CR1_UIFREMAP_Msk      (0x1UL << TIM_CR1_UIFREMAP_Pos)              /*!< 0x00000800 */
#define TIM_CR1_UIFREMAP          TIM_CR1_UIFREMAP_Msk                         /*!<Update interrupt flag remap */
#define TIM_CR1_DITHEN_Pos      (12U)
#define TIM_CR1_DITHEN_Msk      (0x1UL << TIM_CR1_DITHEN_Pos)                  /*!< 0x00001000 */
#define TIM_CR1_DITHEN          TIM_CR1_DITHEN_Msk                             /*!<Dithering enable */
#define TIM_CR2_CCPC_Pos          (0U)
#define TIM_CR2_CCPC_Msk          (0x1UL << TIM_CR2_CCPC_Pos)                  /*!< 0x00000001 */
#define TIM_CR2_CCPC              TIM_CR2_CCPC_Msk                             /*!<Capture/Compare Preloaded Control */
#define TIM_CR2_CCUS_Pos          (2U)
#define TIM_CR2_CCUS_Msk          (0x1UL << TIM_CR2_CCUS_Pos)                  /*!< 0x00000004 */
#define TIM_CR2_CCUS              TIM_CR2_CCUS_Msk                             /*!<Capture/Compare Control Update Selection */
#define TIM_CR2_CCDS_Pos          (3U)
#define TIM_CR2_CCDS_Msk          (0x1UL << TIM_CR2_CCDS_Pos)                  /*!< 0x00000008 */
#define TIM_CR2_CCDS              TIM_CR2_CCDS_Msk                             /*!<Capture/Compare DMA Selection */
#define TIM_CR2_MMS_Pos           (4U)
#define TIM_CR2_MMS_Msk           (0x200007UL << TIM_CR2_MMS_Pos)              /*!< 0x02000070 */
#define TIM_CR2_MMS               TIM_CR2_MMS_Msk                              /*!<MMS[3:0] bits (Master Mode Selection) */
#define TIM_CR2_MMS_0             (0x000001UL << TIM_CR2_MMS_Pos)              /*!< 0x00000010 */
#define TIM_CR2_MMS_1             (0x000002UL << TIM_CR2_MMS_Pos)              /*!< 0x00000020 */
#define TIM_CR2_MMS_2             (0x000004UL << TIM_CR2_MMS_Pos)              /*!< 0x00000040 */
#define TIM_CR2_MMS_3             (0x200000UL << TIM_CR2_MMS_Pos)              /*!< 0x02000000 */
#define TIM_CR2_TI1S_Pos          (7U)
#define TIM_CR2_TI1S_Msk          (0x1UL << TIM_CR2_TI1S_Pos)                  /*!< 0x00000080 */
#define TIM_CR2_TI1S              TIM_CR2_TI1S_Msk                             /*!<TI1 Selection */
#define TIM_CR2_OIS1_Pos          (8U)
#define TIM_CR2_OIS1_Msk          (0x1UL << TIM_CR2_OIS1_Pos)                  /*!< 0x00000100 */
#define TIM_CR2_OIS1              TIM_CR2_OIS1_Msk                             /*!<Output Idle state 1 (OC1 output) */
#define TIM_CR2_OIS1N_Pos         (9U)
#define TIM_CR2_OIS1N_Msk         (0x1UL << TIM_CR2_OIS1N_Pos)                 /*!< 0x00000200 */
#define TIM_CR2_OIS1N             TIM_CR2_OIS1N_Msk                            /*!<Output Idle state 1 (OC1N output) */
#define TIM_CR2_OIS2_Pos          (10U)
#define TIM_CR2_OIS2_Msk          (0x1UL << TIM_CR2_OIS2_Pos)                  /*!< 0x00000400 */
#define TIM_CR2_OIS2              TIM_CR2_OIS2_Msk                             /*!<Output Idle state 2 (OC2 output) */
#define TIM_CR2_OIS2N_Pos         (11U)
#define TIM_CR2_OIS2N_Msk         (0x1UL << TIM_CR2_OIS2N_Pos)                 /*!< 0x00000800 */
#define TIM_CR2_OIS2N             TIM_CR2_OIS2N_Msk                            /*!<Output Idle state 2 (OC2N output) */
#define TIM_CR2_OIS3_Pos          (12U)
#define TIM_CR2_OIS3_Msk          (0x1UL << TIM_CR2_OIS3_Pos)                  /*!< 0x00001000 */
#define TIM_CR2_OIS3              TIM_CR2_OIS3_Msk                             /*!<Output Idle state 3 (OC3 output) */
#define TIM_CR2_OIS3N_Pos         (13U)
#define TIM_CR2_OIS3N_Msk         (0x1UL << TIM_CR2_OIS3N_Pos)                 /*!< 0x00002000 */
#define TIM_CR2_OIS3N             TIM_CR2_OIS3N_Msk                            /*!<Output Idle state 3 (OC3N output) */
#define TIM_CR2_OIS4_Pos          (14U)
#define TIM_CR2_OIS4_Msk          (0x1UL << TIM_CR2_OIS4_Pos)                  /*!< 0x00004000 */
#define TIM_CR2_OIS4              TIM_CR2_OIS4_Msk                             /*!<Output Idle state 4 (OC4 output) */
#define TIM_CR2_OIS4N_Pos         (15U)
#define TIM_CR2_OIS4N_Msk         (0x1UL << TIM_CR2_OIS4N_Pos)                 /*!< 0x00008000 */
#define TIM_CR2_OIS4N             TIM_CR2_OIS4N_Msk                            /*!<Output Idle state 4 (OC4N output) */
#define TIM_CR2_OIS5_Pos          (16U)
#define TIM_CR2_OIS5_Msk          (0x1UL << TIM_CR2_OIS5_Pos)                  /*!< 0x00010000 */
#define TIM_CR2_OIS5              TIM_CR2_OIS5_Msk                             /*!<Output Idle state 5 (OC5 output) */
#define TIM_CR2_OIS6_Pos          (18U)
#define TIM_CR2_OIS6_Msk          (0x1UL << TIM_CR2_OIS6_Pos)                  /*!< 0x00040000 */
#define TIM_CR2_OIS6              TIM_CR2_OIS6_Msk                             /*!<Output Idle state 6 (OC6 output) */
#define TIM_CR2_MMS2_Pos          (20U)
#define TIM_CR2_MMS2_Msk          (0xFUL << TIM_CR2_MMS2_Pos)                  /*!< 0x00F00000 */
#define TIM_CR2_MMS2              TIM_CR2_MMS2_Msk                             /*!<MMS[2:0] bits (Master Mode Selection) */
#define TIM_CR2_MMS2_0            (0x1UL << TIM_CR2_MMS2_Pos)                  /*!< 0x00100000 */
#define TIM_CR2_MMS2_1            (0x2UL << TIM_CR2_MMS2_Pos)                  /*!< 0x00200000 */
#define TIM_CR2_MMS2_2            (0x4UL << TIM_CR2_MMS2_Pos)                  /*!< 0x00400000 */
#define TIM_CR2_MMS2_3            (0x8UL << TIM_CR2_MMS2_Pos)                  /*!< 0x00800000 */
#define TIM_SMCR_SMS_Pos          (0U)
#define TIM_SMCR_SMS_Msk          (0x10007UL << TIM_SMCR_SMS_Pos)              /*!< 0x00010007 */
#define TIM_SMCR_SMS              TIM_SMCR_SMS_Msk                             /*!<SMS[2:0] bits (Slave mode selection) */
#define TIM_SMCR_SMS_0            (0x00001UL << TIM_SMCR_SMS_Pos)              /*!< 0x00000001 */
#define TIM_SMCR_SMS_1            (0x00002UL << TIM_SMCR_SMS_Pos)              /*!< 0x00000002 */
#define TIM_SMCR_SMS_2            (0x00004UL << TIM_SMCR_SMS_Pos)              /*!< 0x00000004 */
#define TIM_SMCR_SMS_3            (0x10000UL << TIM_SMCR_SMS_Pos)              /*!< 0x00010000 */
#define TIM_SMCR_OCCS_Pos         (3U)
#define TIM_SMCR_OCCS_Msk         (0x1UL << TIM_SMCR_OCCS_Pos)                 /*!< 0x00000008 */
#define TIM_SMCR_OCCS             TIM_SMCR_OCCS_Msk                            /*!< OCREF clear selection */
#define TIM_SMCR_TS_Pos           (4U)
#define TIM_SMCR_TS_Msk           (0x30007UL << TIM_SMCR_TS_Pos)               /*!< 0x00300070 */
#define TIM_SMCR_TS               TIM_SMCR_TS_Msk                              /*!<TS[2:0] bits (Trigger selection) */
#define TIM_SMCR_TS_0             (0x00001UL << TIM_SMCR_TS_Pos)               /*!< 0x00000010 */
#define TIM_SMCR_TS_1             (0x00002UL << TIM_SMCR_TS_Pos)               /*!< 0x00000020 */
#define TIM_SMCR_TS_2             (0x00004UL << TIM_SMCR_TS_Pos)               /*!< 0x00000040 */
#define TIM_SMCR_TS_3             (0x10000UL << TIM_SMCR_TS_Pos)               /*!< 0x00100000 */
#define TIM_SMCR_TS_4             (0x20000UL << TIM_SMCR_TS_Pos)               /*!< 0x00200000 */
#define TIM_SMCR_MSM_Pos          (7U)
#define TIM_SMCR_MSM_Msk          (0x1UL << TIM_SMCR_MSM_Pos)                  /*!< 0x00000080 */
#define TIM_SMCR_MSM              TIM_SMCR_MSM_Msk                             /*!<Master/slave mode */
#define TIM_SMCR_ETF_Pos          (8U)
#define TIM_SMCR_ETF_Msk          (0xFUL << TIM_SMCR_ETF_Pos)                  /*!< 0x00000F00 */
#define TIM_SMCR_ETF              TIM_SMCR_ETF_Msk                             /*!<ETF[3:0] bits (External trigger filter) */
#define TIM_SMCR_ETF_0            (0x1UL << TIM_SMCR_ETF_Pos)                  /*!< 0x00000100 */
#define TIM_SMCR_ETF_1            (0x2UL << TIM_SMCR_ETF_Pos)                  /*!< 0x00000200 */
#define TIM_SMCR_ETF_2            (0x4UL << TIM_SMCR_ETF_Pos)                  /*!< 0x00000400 */
#define TIM_SMCR_ETF_3            (0x8UL << TIM_SMCR_ETF_Pos)                  /*!< 0x00000800 */
#define TIM_SMCR_ETPS_Pos         (12U)
#define TIM_SMCR_ETPS_Msk         (0x3UL << TIM_SMCR_ETPS_Pos)                 /*!< 0x00003000 */
#define TIM_SMCR_ETPS             TIM_SMCR_ETPS_Msk                            /*!<ETPS[1:0] bits (External trigger prescaler) */
#define TIM_SMCR_ETPS_0           (0x1UL << TIM_SMCR_ETPS_Pos)                 /*!< 0x00001000 */
#define TIM_SMCR_ETPS_1           (0x2UL << TIM_SMCR_ETPS_Pos)                 /*!< 0x00002000 */
#define TIM_SMCR_ECE_Pos          (14U)
#define TIM_SMCR_ECE_Msk          (0x1UL << TIM_SMCR_ECE_Pos)                  /*!< 0x00004000 */
#define TIM_SMCR_ECE              TIM_SMCR_ECE_Msk                             /*!<External clock enable */
#define TIM_SMCR_ETP_Pos          (15U)
#define TIM_SMCR_ETP_Msk          (0x1UL << TIM_SMCR_ETP_Pos)                  /*!< 0x00008000 */
#define TIM_SMCR_ETP              TIM_SMCR_ETP_Msk                             /*!<External trigger polarity */
#define TIM_SMCR_SMSPE_Pos        (24U)
#define TIM_SMCR_SMSPE_Msk        (0x1UL << TIM_SMCR_SMSPE_Pos)                /*!< 0x02000000 */
#define TIM_SMCR_SMSPE            TIM_SMCR_SMSPE_Msk                           /*!<SMS preload enable */
#define TIM_SMCR_SMSPS_Pos        (25U)
#define TIM_SMCR_SMSPS_Msk        (0x1UL << TIM_SMCR_SMSPS_Pos)                /*!< 0x04000000 */
#define TIM_SMCR_SMSPS            TIM_SMCR_SMSPS_Msk                           /*!<SMS preload source */
#define TIM_DIER_UIE_Pos          (0U)
#define TIM_DIER_UIE_Msk          (0x1UL << TIM_DIER_UIE_Pos)                  /*!< 0x00000001 */
#define TIM_DIER_UIE              TIM_DIER_UIE_Msk                             /*!<Update interrupt enable */
#define TIM_DIER_CC1IE_Pos        (1U)
#define TIM_DIER_CC1IE_Msk        (0x1UL << TIM_DIER_CC1IE_Pos)                /*!< 0x00000002 */
#define TIM_DIER_CC1IE            TIM_DIER_CC1IE_Msk                           /*!<Capture/Compare 1 interrupt enable */
#define TIM_DIER_CC2IE_Pos        (2U)
#define TIM_DIER_CC2IE_Msk        (0x1UL << TIM_DIER_CC2IE_Pos)                /*!< 0x00000004 */
#define TIM_DIER_CC2IE            TIM_DIER_CC2IE_Msk                           /*!<Capture/Compare 2 interrupt enable */
#define TIM_DIER_CC3IE_Pos        (3U)
#define TIM_DIER_CC3IE_Msk        (0x1UL << TIM_DIER_CC3IE_Pos)                /*!< 0x00000008 */
#define TIM_DIER_CC3IE            TIM_DIER_CC3IE_Msk                           /*!<Capture/Compare 3 interrupt enable */
#define TIM_DIER_CC4IE_Pos        (4U)
#define TIM_DIER_CC4IE_Msk        (0x1UL << TIM_DIER_CC4IE_Pos)                /*!< 0x00000010 */
#define TIM_DIER_CC4IE            TIM_DIER_CC4IE_Msk                           /*!<Capture/Compare 4 interrupt enable */
#define TIM_DIER_COMIE_Pos        (5U)
#define TIM_DIER_COMIE_Msk        (0x1UL << TIM_DIER_COMIE_Pos)                /*!< 0x00000020 */
#define TIM_DIER_COMIE            TIM_DIER_COMIE_Msk                           /*!<COM interrupt enable */
#define TIM_DIER_TIE_Pos          (6U)
#define TIM_DIER_TIE_Msk          (0x1UL << TIM_DIER_TIE_Pos)                  /*!< 0x00000040 */
#define TIM_DIER_TIE              TIM_DIER_TIE_Msk                             /*!<Trigger interrupt enable */
#define TIM_DIER_BIE_Pos          (7U)
#define TIM_DIER_BIE_Msk          (0x1UL << TIM_DIER_BIE_Pos)                  /*!< 0x00000080 */
#define TIM_DIER_BIE              TIM_DIER_BIE_Msk                             /*!<Break interrupt enable */
#define TIM_DIER_UDE_Pos          (8U)
#define TIM_DIER_UDE_Msk          (0x1UL << TIM_DIER_UDE_Pos)                  /*!< 0x00000100 */
#define TIM_DIER_UDE              TIM_DIER_UDE_Msk                             /*!<Update DMA request enable */
#define TIM_DIER_CC1DE_Pos        (9U)
#define TIM_DIER_CC1DE_Msk        (0x1UL << TIM_DIER_CC1DE_Pos)                /*!< 0x00000200 */
#define TIM_DIER_CC1DE            TIM_DIER_CC1DE_Msk                           /*!<Capture/Compare 1 DMA request enable */
#define TIM_DIER_CC2DE_Pos        (10U)
#define TIM_DIER_CC2DE_Msk        (0x1UL << TIM_DIER_CC2DE_Pos)                /*!< 0x00000400 */
#define TIM_DIER_CC2DE            TIM_DIER_CC2DE_Msk                           /*!<Capture/Compare 2 DMA request enable */
#define TIM_DIER_CC3DE_Pos        (11U)
#define TIM_DIER_CC3DE_Msk        (0x1UL << TIM_DIER_CC3DE_Pos)                /*!< 0x00000800 */
#define TIM_DIER_CC3DE            TIM_DIER_CC3DE_Msk                           /*!<Capture/Compare 3 DMA request enable */
#define TIM_DIER_CC4DE_Pos        (12U)
#define TIM_DIER_CC4DE_Msk        (0x1UL << TIM_DIER_CC4DE_Pos)                /*!< 0x00001000 */
#define TIM_DIER_CC4DE            TIM_DIER_CC4DE_Msk                           /*!<Capture/Compare 4 DMA request enable */
#define TIM_DIER_COMDE_Pos        (13U)
#define TIM_DIER_COMDE_Msk        (0x1UL << TIM_DIER_COMDE_Pos)                /*!< 0x00002000 */
#define TIM_DIER_COMDE            TIM_DIER_COMDE_Msk                           /*!<COM DMA request enable */
#define TIM_DIER_TDE_Pos          (14U)
#define TIM_DIER_TDE_Msk          (0x1UL << TIM_DIER_TDE_Pos)                  /*!< 0x00004000 */
#define TIM_DIER_TDE              TIM_DIER_TDE_Msk                             /*!<Trigger DMA request enable */
#define TIM_DIER_IDXIE_Pos        (20U)
#define TIM_DIER_IDXIE_Msk        (0x1UL << TIM_DIER_IDXIE_Pos)                /*!< 0x00100000 */
#define TIM_DIER_IDXIE            TIM_DIER_IDXIE_Msk                           /*!<Encoder index interrupt enable */
#define TIM_DIER_DIRIE_Pos        (21U)
#define TIM_DIER_DIRIE_Msk        (0x1UL << TIM_DIER_DIRIE_Pos)                /*!< 0x00200000 */
#define TIM_DIER_DIRIE            TIM_DIER_DIRIE_Msk                           /*!<Encoder direction change interrupt enable */
#define TIM_DIER_IERRIE_Pos       (22U)
#define TIM_DIER_IERRIE_Msk       (0x1UL << TIM_DIER_IERRIE_Pos)               /*!< 0x00400000 */
#define TIM_DIER_IERRIE           TIM_DIER_IERRIE_Msk                          /*!<Encoder index error enable */
#define TIM_DIER_TERRIE_Pos       (23U)
#define TIM_DIER_TERRIE_Msk       (0x1UL << TIM_DIER_TERRIE_Pos)               /*!< 0x00800000 */
#define TIM_DIER_TERRIE           TIM_DIER_TERRIE_Msk                          /*!<Encoder transition error enable */
#define TIM_SR_UIF_Pos            (0U)
#define TIM_SR_UIF_Msk            (0x1UL << TIM_SR_UIF_Pos)                    /*!< 0x00000001 */
#define TIM_SR_UIF                TIM_SR_UIF_Msk                               /*!<Update interrupt Flag */
#define TIM_SR_CC1IF_Pos          (1U)
#define TIM_SR_CC1IF_Msk          (0x1UL << TIM_SR_CC1IF_Pos)                  /*!< 0x00000002 */
#define TIM_SR_CC1IF              TIM_SR_CC1IF_Msk                             /*!<Capture/Compare 1 interrupt Flag */
#define TIM_SR_CC2IF_Pos          (2U)
#define TIM_SR_CC2IF_Msk          (0x1UL << TIM_SR_CC2IF_Pos)                  /*!< 0x00000004 */
#define TIM_SR_CC2IF              TIM_SR_CC2IF_Msk                             /*!<Capture/Compare 2 interrupt Flag */
#define TIM_SR_CC3IF_Pos          (3U)
#define TIM_SR_CC3IF_Msk          (0x1UL << TIM_SR_CC3IF_Pos)                  /*!< 0x00000008 */
#define TIM_SR_CC3IF              TIM_SR_CC3IF_Msk                             /*!<Capture/Compare 3 interrupt Flag */
#define TIM_SR_CC4IF_Pos          (4U)
#define TIM_SR_CC4IF_Msk          (0x1UL << TIM_SR_CC4IF_Pos)                  /*!< 0x00000010 */
#define TIM_SR_CC4IF              TIM_SR_CC4IF_Msk                             /*!<Capture/Compare 4 interrupt Flag */
#define TIM_SR_COMIF_Pos          (5U)
#define TIM_SR_COMIF_Msk          (0x1UL << TIM_SR_COMIF_Pos)                  /*!< 0x00000020 */
#define TIM_SR_COMIF              TIM_SR_COMIF_Msk                             /*!<COM interrupt Flag */
#define TIM_SR_TIF_Pos            (6U)
#define TIM_SR_TIF_Msk            (0x1UL << TIM_SR_TIF_Pos)                    /*!< 0x00000040 */
#define TIM_SR_TIF                TIM_SR_TIF_Msk                               /*!<Trigger interrupt Flag */
#define TIM_SR_BIF_Pos            (7U)
#define TIM_SR_BIF_Msk            (0x1UL << TIM_SR_BIF_Pos)                    /*!< 0x00000080 */
#define TIM_SR_BIF                TIM_SR_BIF_Msk                               /*!<Break interrupt Flag */
#define TIM_SR_B2IF_Pos           (8U)
#define TIM_SR_B2IF_Msk           (0x1UL << TIM_SR_B2IF_Pos)                   /*!< 0x00000100 */
#define TIM_SR_B2IF               TIM_SR_B2IF_Msk                              /*!<Break 2 interrupt Flag */
#define TIM_SR_CC1OF_Pos          (9U)
#define TIM_SR_CC1OF_Msk          (0x1UL << TIM_SR_CC1OF_Pos)                  /*!< 0x00000200 */
#define TIM_SR_CC1OF              TIM_SR_CC1OF_Msk                             /*!<Capture/Compare 1 Overcapture Flag */
#define TIM_SR_CC2OF_Pos          (10U)
#define TIM_SR_CC2OF_Msk          (0x1UL << TIM_SR_CC2OF_Pos)                  /*!< 0x00000400 */
#define TIM_SR_CC2OF              TIM_SR_CC2OF_Msk                             /*!<Capture/Compare 2 Overcapture Flag */
#define TIM_SR_CC3OF_Pos          (11U)
#define TIM_SR_CC3OF_Msk          (0x1UL << TIM_SR_CC3OF_Pos)                  /*!< 0x00000800 */
#define TIM_SR_CC3OF              TIM_SR_CC3OF_Msk                             /*!<Capture/Compare 3 Overcapture Flag */
#define TIM_SR_CC4OF_Pos          (12U)
#define TIM_SR_CC4OF_Msk          (0x1UL << TIM_SR_CC4OF_Pos)                  /*!< 0x00001000 */
#define TIM_SR_CC4OF              TIM_SR_CC4OF_Msk                             /*!<Capture/Compare 4 Overcapture Flag */
#define TIM_SR_SBIF_Pos           (13U)
#define TIM_SR_SBIF_Msk           (0x1UL << TIM_SR_SBIF_Pos)                   /*!< 0x00002000 */
#define TIM_SR_SBIF               TIM_SR_SBIF_Msk                              /*!<System Break interrupt Flag */
#define TIM_SR_CC5IF_Pos          (16U)
#define TIM_SR_CC5IF_Msk          (0x1UL << TIM_SR_CC5IF_Pos)                  /*!< 0x00010000 */
#define TIM_SR_CC5IF              TIM_SR_CC5IF_Msk                             /*!<Capture/Compare 5 interrupt Flag */
#define TIM_SR_CC6IF_Pos          (17U)
#define TIM_SR_CC6IF_Msk          (0x1UL << TIM_SR_CC6IF_Pos)                  /*!< 0x00020000 */
#define TIM_SR_CC6IF              TIM_SR_CC6IF_Msk                             /*!<Capture/Compare 6 interrupt Flag */
#define TIM_SR_IDXF_Pos           (20U)
#define TIM_SR_IDXF_Msk           (0x1UL << TIM_SR_IDXF_Pos)                   /*!< 0x00100000 */
#define TIM_SR_IDXF               TIM_SR_IDXF_Msk                              /*!<Encoder index interrupt flag */
#define TIM_SR_DIRF_Pos           (21U)
#define TIM_SR_DIRF_Msk           (0x1UL << TIM_SR_DIRF_Pos)                   /*!< 0x00200000 */
#define TIM_SR_DIRF               TIM_SR_DIRF_Msk                              /*!<Encoder direction change interrupt flag */
#define TIM_SR_IERRF_Pos          (22U)
#define TIM_SR_IERRF_Msk          (0x1UL << TIM_SR_IERRF_Pos)                  /*!< 0x00400000 */
#define TIM_SR_IERRF              TIM_SR_IERRF_Msk                             /*!<Encoder index error flag */
#define TIM_SR_TERRF_Pos          (23U)
#define TIM_SR_TERRF_Msk          (0x1UL << TIM_SR_TERRF_Pos)                  /*!< 0x00800000 */
#define TIM_SR_TERRF              TIM_SR_TERRF_Msk                             /*!<Encoder transition error flag */
#define TIM_EGR_UG_Pos            (0U)
#define TIM_EGR_UG_Msk            (0x1UL << TIM_EGR_UG_Pos)                    /*!< 0x00000001 */
#define TIM_EGR_UG                TIM_EGR_UG_Msk                               /*!<Update Generation */
#define TIM_EGR_CC1G_Pos          (1U)
#define TIM_EGR_CC1G_Msk          (0x1UL << TIM_EGR_CC1G_Pos)                  /*!< 0x00000002 */
#define TIM_EGR_CC1G              TIM_EGR_CC1G_Msk                             /*!<Capture/Compare 1 Generation */
#define TIM_EGR_CC2G_Pos          (2U)
#define TIM_EGR_CC2G_Msk          (0x1UL << TIM_EGR_CC2G_Pos)                  /*!< 0x00000004 */
#define TIM_EGR_CC2G              TIM_EGR_CC2G_Msk                             /*!<Capture/Compare 2 Generation */
#define TIM_EGR_CC3G_Pos          (3U)
#define TIM_EGR_CC3G_Msk          (0x1UL << TIM_EGR_CC3G_Pos)                  /*!< 0x00000008 */
#define TIM_EGR_CC3G              TIM_EGR_CC3G_Msk                             /*!<Capture/Compare 3 Generation */
#define TIM_EGR_CC4G_Pos          (4U)
#define TIM_EGR_CC4G_Msk          (0x1UL << TIM_EGR_CC4G_Pos)                  /*!< 0x00000010 */
#define TIM_EGR_CC4G              TIM_EGR_CC4G_Msk                             /*!<Capture/Compare 4 Generation */
#define TIM_EGR_COMG_Pos          (5U)
#define TIM_EGR_COMG_Msk          (0x1UL << TIM_EGR_COMG_Pos)                  /*!< 0x00000020 */
#define TIM_EGR_COMG              TIM_EGR_COMG_Msk                             /*!<Capture/Compare Control Update Generation */
#define TIM_EGR_TG_Pos            (6U)
#define TIM_EGR_TG_Msk            (0x1UL << TIM_EGR_TG_Pos)                    /*!< 0x00000040 */
#define TIM_EGR_TG                TIM_EGR_TG_Msk                               /*!<Trigger Generation */
#define TIM_EGR_BG_Pos            (7U)
#define TIM_EGR_BG_Msk            (0x1UL << TIM_EGR_BG_Pos)                    /*!< 0x00000080 */
#define TIM_EGR_BG                TIM_EGR_BG_Msk                               /*!<Break Generation */
#define TIM_EGR_B2G_Pos           (8U)
#define TIM_EGR_B2G_Msk           (0x1UL << TIM_EGR_B2G_Pos)                   /*!< 0x00000100 */
#define TIM_EGR_B2G               TIM_EGR_B2G_Msk                              /*!<Break 2 Generation */
#define TIM_CCMR1_CC1S_Pos        (0U)
#define TIM_CCMR1_CC1S_Msk        (0x3UL << TIM_CCMR1_CC1S_Pos)                /*!< 0x00000003 */
#define TIM_CCMR1_CC1S            TIM_CCMR1_CC1S_Msk                           /*!<CC1S[1:0] bits (Capture/Compare 1 Selection) */
#define TIM_CCMR1_CC1S_0          (0x1UL << TIM_CCMR1_CC1S_Pos)                /*!< 0x00000001 */
#define TIM_CCMR1_CC1S_1          (0x2UL << TIM_CCMR1_CC1S_Pos)                /*!< 0x00000002 */
#define TIM_CCMR1_OC1FE_Pos       (2U)
#define TIM_CCMR1_OC1FE_Msk       (0x1UL << TIM_CCMR1_OC1FE_Pos)               /*!< 0x00000004 */
#define TIM_CCMR1_OC1FE           TIM_CCMR1_OC1FE_Msk                          /*!<Output Compare 1 Fast enable */
#define TIM_CCMR1_OC1PE_Pos       (3U)
#define TIM_CCMR1_OC1PE_Msk       (0x1UL << TIM_CCMR1_OC1PE_Pos)               /*!< 0x00000008 */
#define TIM_CCMR1_OC1PE           TIM_CCMR1_OC1PE_Msk                          /*!<Output Compare 1 Preload enable */
#define TIM_CCMR1_OC1M_Pos        (4U)
#define TIM_CCMR1_OC1M_Msk        (0x1007UL << TIM_CCMR1_OC1M_Pos)             /*!< 0x00010070 */
#define TIM_CCMR1_OC1M            TIM_CCMR1_OC1M_Msk                           /*!<OC1M[2:0] bits (Output Compare 1 Mode) */
#define TIM_CCMR1_OC1M_0          (0x0001UL << TIM_CCMR1_OC1M_Pos)             /*!< 0x00000010 */
#define TIM_CCMR1_OC1M_1          (0x0002UL << TIM_CCMR1_OC1M_Pos)             /*!< 0x00000020 */
#define TIM_CCMR1_OC1M_2          (0x0004UL << TIM_CCMR1_OC1M_Pos)             /*!< 0x00000040 */
#define TIM_CCMR1_OC1M_3          (0x1000UL << TIM_CCMR1_OC1M_Pos)             /*!< 0x00010000 */
#define TIM_CCMR1_OC1CE_Pos       (7U)
#define TIM_CCMR1_OC1CE_Msk       (0x1UL << TIM_CCMR1_OC1CE_Pos)               /*!< 0x00000080 */
#define TIM_CCMR1_OC1CE           TIM_CCMR1_OC1CE_Msk                          /*!<Output Compare 1 Clear Enable */
#define TIM_CCMR1_CC2S_Pos        (8U)
#define TIM_CCMR1_CC2S_Msk        (0x3UL << TIM_CCMR1_CC2S_Pos)                /*!< 0x00000300 */
#define TIM_CCMR1_CC2S            TIM_CCMR1_CC2S_Msk                           /*!<CC2S[1:0] bits (Capture/Compare 2 Selection) */
#define TIM_CCMR1_CC2S_0          (0x1UL << TIM_CCMR1_CC2S_Pos)                /*!< 0x00000100 */
#define TIM_CCMR1_CC2S_1          (0x2UL << TIM_CCMR1_CC2S_Pos)                /*!< 0x00000200 */
#define TIM_CCMR1_OC2FE_Pos       (10U)
#define TIM_CCMR1_OC2FE_Msk       (0x1UL << TIM_CCMR1_OC2FE_Pos)               /*!< 0x00000400 */
#define TIM_CCMR1_OC2FE           TIM_CCMR1_OC2FE_Msk                          /*!<Output Compare 2 Fast enable */
#define TIM_CCMR1_OC2PE_Pos       (11U)
#define TIM_CCMR1_OC2PE_Msk       (0x1UL << TIM_CCMR1_OC2PE_Pos)               /*!< 0x00000800 */
#define TIM_CCMR1_OC2PE           TIM_CCMR1_OC2PE_Msk                          /*!<Output Compare 2 Preload enable */
#define TIM_CCMR1_OC2M_Pos        (12U)
#define TIM_CCMR1_OC2M_Msk        (0x1007UL << TIM_CCMR1_OC2M_Pos)             /*!< 0x01007000 */
#define TIM_CCMR1_OC2M            TIM_CCMR1_OC2M_Msk                           /*!<OC2M[2:0] bits (Output Compare 2 Mode) */
#define TIM_CCMR1_OC2M_0          (0x0001UL << TIM_CCMR1_OC2M_Pos)             /*!< 0x00001000 */
#define TIM_CCMR1_OC2M_1          (0x0002UL << TIM_CCMR1_OC2M_Pos)             /*!< 0x00002000 */
#define TIM_CCMR1_OC2M_2          (0x0004UL << TIM_CCMR1_OC2M_Pos)             /*!< 0x00004000 */
#define TIM_CCMR1_OC2M_3          (0x1000UL << TIM_CCMR1_OC2M_Pos)             /*!< 0x01000000 */
#define TIM_CCMR1_OC2CE_Pos       (15U)
#define TIM_CCMR1_OC2CE_Msk       (0x1UL << TIM_CCMR1_OC2CE_Pos)               /*!< 0x00008000 */
#define TIM_CCMR1_OC2CE           TIM_CCMR1_OC2CE_Msk                          /*!<Output Compare 2 Clear Enable */
#define TIM_CCMR1_IC1PSC_Pos      (2U)
#define TIM_CCMR1_IC1PSC_Msk      (0x3UL << TIM_CCMR1_IC1PSC_Pos)              /*!< 0x0000000C */
#define TIM_CCMR1_IC1PSC          TIM_CCMR1_IC1PSC_Msk                         /*!<IC1PSC[1:0] bits (Input Capture 1 Prescaler) */
#define TIM_CCMR1_IC1PSC_0        (0x1UL << TIM_CCMR1_IC1PSC_Pos)              /*!< 0x00000004 */
#define TIM_CCMR1_IC1PSC_1        (0x2UL << TIM_CCMR1_IC1PSC_Pos)              /*!< 0x00000008 */
#define TIM_CCMR1_IC1F_Pos        (4U)
#define TIM_CCMR1_IC1F_Msk        (0xFUL << TIM_CCMR1_IC1F_Pos)                /*!< 0x000000F0 */
#define TIM_CCMR1_IC1F            TIM_CCMR1_IC1F_Msk                           /*!<IC1F[3:0] bits (Input Capture 1 Filter) */
#define TIM_CCMR1_IC1F_0          (0x1UL << TIM_CCMR1_IC1F_Pos)                /*!< 0x00000010 */
#define TIM_CCMR1_IC1F_1          (0x2UL << TIM_CCMR1_IC1F_Pos)                /*!< 0x00000020 */
#define TIM_CCMR1_IC1F_2          (0x4UL << TIM_CCMR1_IC1F_Pos)                /*!< 0x00000040 */
#define TIM_CCMR1_IC1F_3          (0x8UL << TIM_CCMR1_IC1F_Pos)                /*!< 0x00000080 */
#define TIM_CCMR1_IC2PSC_Pos      (10U)
#define TIM_CCMR1_IC2PSC_Msk      (0x3UL << TIM_CCMR1_IC2PSC_Pos)              /*!< 0x00000C00 */
#define TIM_CCMR1_IC2PSC          TIM_CCMR1_IC2PSC_Msk                         /*!<IC2PSC[1:0] bits (Input Capture 2 Prescaler) */
#define TIM_CCMR1_IC2PSC_0        (0x1UL << TIM_CCMR1_IC2PSC_Pos)              /*!< 0x00000400 */
#define TIM_CCMR1_IC2PSC_1        (0x2UL << TIM_CCMR1_IC2PSC_Pos)              /*!< 0x00000800 */
#define TIM_CCMR1_IC2F_Pos        (12U)
#define TIM_CCMR1_IC2F_Msk        (0xFUL << TIM_CCMR1_IC2F_Pos)                /*!< 0x0000F000 */
#define TIM_CCMR1_IC2F            TIM_CCMR1_IC2F_Msk                           /*!<IC2F[3:0] bits (Input Capture 2 Filter) */
#define TIM_CCMR1_IC2F_0          (0x1UL << TIM_CCMR1_IC2F_Pos)                /*!< 0x00001000 */
#define TIM_CCMR1_IC2F_1          (0x2UL << TIM_CCMR1_IC2F_Pos)                /*!< 0x00002000 */
#define TIM_CCMR1_IC2F_2          (0x4UL << TIM_CCMR1_IC2F_Pos)                /*!< 0x00004000 */
#define TIM_CCMR1_IC2F_3          (0x8UL << TIM_CCMR1_IC2F_Pos)                /*!< 0x00008000 */
#define TIM_CCMR2_CC3S_Pos        (0U)
#define TIM_CCMR2_CC3S_Msk        (0x3UL << TIM_CCMR2_CC3S_Pos)                /*!< 0x00000003 */
#define TIM_CCMR2_CC3S            TIM_CCMR2_CC3S_Msk                           /*!<CC3S[1:0] bits (Capture/Compare 3 Selection) */
#define TIM_CCMR2_CC3S_0          (0x1UL << TIM_CCMR2_CC3S_Pos)                /*!< 0x00000001 */
#define TIM_CCMR2_CC3S_1          (0x2UL << TIM_CCMR2_CC3S_Pos)                /*!< 0x00000002 */
#define TIM_CCMR2_OC3FE_Pos       (2U)
#define TIM_CCMR2_OC3FE_Msk       (0x1UL << TIM_CCMR2_OC3FE_Pos)               /*!< 0x00000004 */
#define TIM_CCMR2_OC3FE           TIM_CCMR2_OC3FE_Msk                          /*!<Output Compare 3 Fast enable */
#define TIM_CCMR2_OC3PE_Pos       (3U)
#define TIM_CCMR2_OC3PE_Msk       (0x1UL << TIM_CCMR2_OC3PE_Pos)               /*!< 0x00000008 */
#define TIM_CCMR2_OC3PE           TIM_CCMR2_OC3PE_Msk                          /*!<Output Compare 3 Preload enable */
#define TIM_CCMR2_OC3M_Pos        (4U)
#define TIM_CCMR2_OC3M_Msk        (0x1007UL << TIM_CCMR2_OC3M_Pos)             /*!< 0x00010070 */
#define TIM_CCMR2_OC3M            TIM_CCMR2_OC3M_Msk                           /*!<OC3M[2:0] bits (Output Compare 3 Mode) */
#define TIM_CCMR2_OC3M_0          (0x0001UL << TIM_CCMR2_OC3M_Pos)             /*!< 0x00000010 */
#define TIM_CCMR2_OC3M_1          (0x0002UL << TIM_CCMR2_OC3M_Pos)             /*!< 0x00000020 */
#define TIM_CCMR2_OC3M_2          (0x0004UL << TIM_CCMR2_OC3M_Pos)             /*!< 0x00000040 */
#define TIM_CCMR2_OC3M_3          (0x1000UL << TIM_CCMR2_OC3M_Pos)             /*!< 0x00010000 */
#define TIM_CCMR2_OC3CE_Pos       (7U)
#define TIM_CCMR2_OC3CE_Msk       (0x1UL << TIM_CCMR2_OC3CE_Pos)               /*!< 0x00000080 */
#define TIM_CCMR2_OC3CE           TIM_CCMR2_OC3CE_Msk                          /*!<Output Compare 3 Clear Enable */
#define TIM_CCMR2_CC4S_Pos        (8U)
#define TIM_CCMR2_CC4S_Msk        (0x3UL << TIM_CCMR2_CC4S_Pos)                /*!< 0x00000300 */
#define TIM_CCMR2_CC4S            TIM_CCMR2_CC4S_Msk                           /*!<CC4S[1:0] bits (Capture/Compare 4 Selection) */
#define TIM_CCMR2_CC4S_0          (0x1UL << TIM_CCMR2_CC4S_Pos)                /*!< 0x00000100 */
#define TIM_CCMR2_CC4S_1          (0x2UL << TIM_CCMR2_CC4S_Pos)                /*!< 0x00000200 */
#define TIM_CCMR2_OC4FE_Pos       (10U)
#define TIM_CCMR2_OC4FE_Msk       (0x1UL << TIM_CCMR2_OC4FE_Pos)               /*!< 0x00000400 */
#define TIM_CCMR2_OC4FE           TIM_CCMR2_OC4FE_Msk                          /*!<Output Compare 4 Fast enable */
#define TIM_CCMR2_OC4PE_Pos       (11U)
#define TIM_CCMR2_OC4PE_Msk       (0x1UL << TIM_CCMR2_OC4PE_Pos)               /*!< 0x00000800 */
#define TIM_CCMR2_OC4PE           TIM_CCMR2_OC4PE_Msk                          /*!<Output Compare 4 Preload enable */
#define TIM_CCMR2_OC4M_Pos        (12U)
#define TIM_CCMR2_OC4M_Msk        (0x1007UL << TIM_CCMR2_OC4M_Pos)             /*!< 0x01007000 */
#define TIM_CCMR2_OC4M            TIM_CCMR2_OC4M_Msk                           /*!<OC4M[2:0] bits (Output Compare 4 Mode) */
#define TIM_CCMR2_OC4M_0          (0x0001UL << TIM_CCMR2_OC4M_Pos)             /*!< 0x00001000 */
#define TIM_CCMR2_OC4M_1          (0x0002UL << TIM_CCMR2_OC4M_Pos)             /*!< 0x00002000 */
#define TIM_CCMR2_OC4M_2          (0x0004UL << TIM_CCMR2_OC4M_Pos)             /*!< 0x00004000 */
#define TIM_CCMR2_OC4M_3          (0x1000UL << TIM_CCMR2_OC4M_Pos)             /*!< 0x01000000 */
#define TIM_CCMR2_OC4CE_Pos       (15U)
#define TIM_CCMR2_OC4CE_Msk       (0x1UL << TIM_CCMR2_OC4CE_Pos)               /*!< 0x00008000 */
#define TIM_CCMR2_OC4CE           TIM_CCMR2_OC4CE_Msk                          /*!<Output Compare 4 Clear Enable */
#define TIM_CCMR2_IC3PSC_Pos      (2U)
#define TIM_CCMR2_IC3PSC_Msk      (0x3UL << TIM_CCMR2_IC3PSC_Pos)              /*!< 0x0000000C */
#define TIM_CCMR2_IC3PSC          TIM_CCMR2_IC3PSC_Msk                         /*!<IC3PSC[1:0] bits (Input Capture 3 Prescaler) */
#define TIM_CCMR2_IC3PSC_0        (0x1UL << TIM_CCMR2_IC3PSC_Pos)              /*!< 0x00000004 */
#define TIM_CCMR2_IC3PSC_1        (0x2UL << TIM_CCMR2_IC3PSC_Pos)              /*!< 0x00000008 */
#define TIM_CCMR2_IC3F_Pos        (4U)
#define TIM_CCMR2_IC3F_Msk        (0xFUL << TIM_CCMR2_IC3F_Pos)                /*!< 0x000000F0 */
#define TIM_CCMR2_IC3F            TIM_CCMR2_IC3F_Msk                           /*!<IC3F[3:0] bits (Input Capture 3 Filter) */
#define TIM_CCMR2_IC3F_0          (0x1UL << TIM_CCMR2_IC3F_Pos)                /*!< 0x00000010 */
#define TIM_CCMR2_IC3F_1          (0x2UL << TIM_CCMR2_IC3F_Pos)                /*!< 0x00000020 */
#define TIM_CCMR2_IC3F_2          (0x4UL << TIM_CCMR2_IC3F_Pos)                /*!< 0x00000040 */
#define TIM_CCMR2_IC3F_3          (0x8UL << TIM_CCMR2_IC3F_Pos)                /*!< 0x00000080 */
#define TIM_CCMR2_IC4PSC_Pos      (10U)
#define TIM_CCMR2_IC4PSC_Msk      (0x3UL << TIM_CCMR2_IC4PSC_Pos)              /*!< 0x00000C00 */
#define TIM_CCMR2_IC4PSC          TIM_CCMR2_IC4PSC_Msk                         /*!<IC4PSC[1:0] bits (Input Capture 4 Prescaler) */
#define TIM_CCMR2_IC4PSC_0        (0x1UL << TIM_CCMR2_IC4PSC_Pos)              /*!< 0x00000400 */
#define TIM_CCMR2_IC4PSC_1        (0x2UL << TIM_CCMR2_IC4PSC_Pos)              /*!< 0x00000800 */
#define TIM_CCMR2_IC4F_Pos        (12U)
#define TIM_CCMR2_IC4F_Msk        (0xFUL << TIM_CCMR2_IC4F_Pos)                /*!< 0x0000F000 */
#define TIM_CCMR2_IC4F            TIM_CCMR2_IC4F_Msk                           /*!<IC4F[3:0] bits (Input Capture 4 Filter) */
#define TIM_CCMR2_IC4F_0          (0x1UL << TIM_CCMR2_IC4F_Pos)                /*!< 0x00001000 */
#define TIM_CCMR2_IC4F_1          (0x2UL << TIM_CCMR2_IC4F_Pos)                /*!< 0x00002000 */
#define TIM_CCMR2_IC4F_2          (0x4UL << TIM_CCMR2_IC4F_Pos)                /*!< 0x00004000 */
#define TIM_CCMR2_IC4F_3          (0x8UL << TIM_CCMR2_IC4F_Pos)                /*!< 0x00008000 */
#define TIM_CCMR3_OC5FE_Pos       (2U)
#define TIM_CCMR3_OC5FE_Msk       (0x1UL << TIM_CCMR3_OC5FE_Pos)               /*!< 0x00000004 */
#define TIM_CCMR3_OC5FE           TIM_CCMR3_OC5FE_Msk                          /*!<Output Compare 5 Fast enable */
#define TIM_CCMR3_OC5PE_Pos       (3U)
#define TIM_CCMR3_OC5PE_Msk       (0x1UL << TIM_CCMR3_OC5PE_Pos)               /*!< 0x00000008 */
#define TIM_CCMR3_OC5PE           TIM_CCMR3_OC5PE_Msk                          /*!<Output Compare 5 Preload enable */
#define TIM_CCMR3_OC5M_Pos        (4U)
#define TIM_CCMR3_OC5M_Msk        (0x1007UL << TIM_CCMR3_OC5M_Pos)             /*!< 0x00010070 */
#define TIM_CCMR3_OC5M            TIM_CCMR3_OC5M_Msk                           /*!<OC5M[3:0] bits (Output Compare 5 Mode) */
#define TIM_CCMR3_OC5M_0          (0x0001UL << TIM_CCMR3_OC5M_Pos)             /*!< 0x00000010 */
#define TIM_CCMR3_OC5M_1          (0x0002UL << TIM_CCMR3_OC5M_Pos)             /*!< 0x00000020 */
#define TIM_CCMR3_OC5M_2          (0x0004UL << TIM_CCMR3_OC5M_Pos)             /*!< 0x00000040 */
#define TIM_CCMR3_OC5M_3          (0x1000UL << TIM_CCMR3_OC5M_Pos)             /*!< 0x00010000 */
#define TIM_CCMR3_OC5CE_Pos       (7U)
#define TIM_CCMR3_OC5CE_Msk       (0x1UL << TIM_CCMR3_OC5CE_Pos)               /*!< 0x00000080 */
#define TIM_CCMR3_OC5CE           TIM_CCMR3_OC5CE_Msk                          /*!<Output Compare 5 Clear Enable */
#define TIM_CCMR3_OC6FE_Pos       (10U)
#define TIM_CCMR3_OC6FE_Msk       (0x1UL << TIM_CCMR3_OC6FE_Pos)               /*!< 0x00000400 */
#define TIM_CCMR3_OC6FE           TIM_CCMR3_OC6FE_Msk                          /*!<Output Compare 6 Fast enable */
#define TIM_CCMR3_OC6PE_Pos       (11U)
#define TIM_CCMR3_OC6PE_Msk       (0x1UL << TIM_CCMR3_OC6PE_Pos)               /*!< 0x00000800 */
#define TIM_CCMR3_OC6PE           TIM_CCMR3_OC6PE_Msk                          /*!<Output Compare 6 Preload enable */
#define TIM_CCMR3_OC6M_Pos        (12U)
#define TIM_CCMR3_OC6M_Msk        (0x1007UL << TIM_CCMR3_OC6M_Pos)             /*!< 0x01007000 */
#define TIM_CCMR3_OC6M            TIM_CCMR3_OC6M_Msk                           /*!<OC6M[3:0] bits (Output Compare 6 Mode) */
#define TIM_CCMR3_OC6M_0          (0x0001UL << TIM_CCMR3_OC6M_Pos)             /*!< 0x00001000 */
#define TIM_CCMR3_OC6M_1          (0x0002UL << TIM_CCMR3_OC6M_Pos)             /*!< 0x00002000 */
#define TIM_CCMR3_OC6M_2          (0x0004UL << TIM_CCMR3_OC6M_Pos)             /*!< 0x00004000 */
#define TIM_CCMR3_OC6M_3          (0x1000UL << TIM_CCMR3_OC6M_Pos)             /*!< 0x01000000 */
#define TIM_CCMR3_OC6CE_Pos       (15U)
#define TIM_CCMR3_OC6CE_Msk       (0x1UL << TIM_CCMR3_OC6CE_Pos)               /*!< 0x00008000 */
#define TIM_CCMR3_OC6CE           TIM_CCMR3_OC6CE_Msk                          /*!<Output Compare 6 Clear Enable */
#define TIM_CCER_CC1E_Pos         (0U)
#define TIM_CCER_CC1E_Msk         (0x1UL << TIM_CCER_CC1E_Pos)                 /*!< 0x00000001 */
#define TIM_CCER_CC1E             TIM_CCER_CC1E_Msk                            /*!<Capture/Compare 1 output enable */
#define TIM_CCER_CC1P_Pos         (1U)
#define TIM_CCER_CC1P_Msk         (0x1UL << TIM_CCER_CC1P_Pos)                 /*!< 0x00000002 */
#define TIM_CCER_CC1P             TIM_CCER_CC1P_Msk                            /*!<Capture/Compare 1 output Polarity */
#define TIM_CCER_CC1NE_Pos        (2U)
#define TIM_CCER_CC1NE_Msk        (0x1UL << TIM_CCER_CC1NE_Pos)                /*!< 0x00000004 */
#define TIM_CCER_CC1NE            TIM_CCER_CC1NE_Msk                           /*!<Capture/Compare 1 Complementary output enable */
#define TIM_CCER_CC1NP_Pos        (3U)
#define TIM_CCER_CC1NP_Msk        (0x1UL << TIM_CCER_CC1NP_Pos)                /*!< 0x00000008 */
#define TIM_CCER_CC1NP            TIM_CCER_CC1NP_Msk                           /*!<Capture/Compare 1 Complementary output Polarity */
#define TIM_CCER_CC2E_Pos         (4U)
#define TIM_CCER_CC2E_Msk         (0x1UL << TIM_CCER_CC2E_Pos)                 /*!< 0x00000010 */
#define TIM_CCER_CC2E             TIM_CCER_CC2E_Msk                            /*!<Capture/Compare 2 output enable */
#define TIM_CCER_CC2P_Pos         (5U)
#define TIM_CCER_CC2P_Msk         (0x1UL << TIM_CCER_CC2P_Pos)                 /*!< 0x00000020 */
#define TIM_CCER_CC2P             TIM_CCER_CC2P_Msk                            /*!<Capture/Compare 2 output Polarity */
#define TIM_CCER_CC2NE_Pos        (6U)
#define TIM_CCER_CC2NE_Msk        (0x1UL << TIM_CCER_CC2NE_Pos)                /*!< 0x00000040 */
#define TIM_CCER_CC2NE            TIM_CCER_CC2NE_Msk                           /*!<Capture/Compare 2 Complementary output enable */
#define TIM_CCER_CC2NP_Pos        (7U)
#define TIM_CCER_CC2NP_Msk        (0x1UL << TIM_CCER_CC2NP_Pos)                /*!< 0x00000080 */
#define TIM_CCER_CC2NP            TIM_CCER_CC2NP_Msk                           /*!<Capture/Compare 2 Complementary output Polarity */
#define TIM_CCER_CC3E_Pos         (8U)
#define TIM_CCER_CC3E_Msk         (0x1UL << TIM_CCER_CC3E_Pos)                 /*!< 0x00000100 */
#define TIM_CCER_CC3E             TIM_CCER_CC3E_Msk                            /*!<Capture/Compare 3 output enable */
#define TIM_CCER_CC3P_Pos         (9U)
#define TIM_CCER_CC3P_Msk         (0x1UL << TIM_CCER_CC3P_Pos)                 /*!< 0x00000200 */
#define TIM_CCER_CC3P             TIM_CCER_CC3P_Msk                            /*!<Capture/Compare 3 output Polarity */
#define TIM_CCER_CC3NE_Pos        (10U)
#define TIM_CCER_CC3NE_Msk        (0x1UL << TIM_CCER_CC3NE_Pos)                /*!< 0x00000400 */
#define TIM_CCER_CC3NE            TIM_CCER_CC3NE_Msk                           /*!<Capture/Compare 3 Complementary output enable */
#define TIM_CCER_CC3NP_Pos        (11U)
#define TIM_CCER_CC3NP_Msk        (0x1UL << TIM_CCER_CC3NP_Pos)                /*!< 0x00000800 */
#define TIM_CCER_CC3NP            TIM_CCER_CC3NP_Msk                           /*!<Capture/Compare 3 Complementary output Polarity */
#define TIM_CCER_CC4E_Pos         (12U)
#define TIM_CCER_CC4E_Msk         (0x1UL << TIM_CCER_CC4E_Pos)                 /*!< 0x00001000 */
#define TIM_CCER_CC4E             TIM_CCER_CC4E_Msk                            /*!<Capture/Compare 4 output enable */
#define TIM_CCER_CC4P_Pos         (13U)
#define TIM_CCER_CC4P_Msk         (0x1UL << TIM_CCER_CC4P_Pos)                 /*!< 0x00002000 */
#define TIM_CCER_CC4P             TIM_CCER_CC4P_Msk                            /*!<Capture/Compare 4 output Polarity */
#define TIM_CCER_CC4NE_Pos        (14U)
#define TIM_CCER_CC4NE_Msk        (0x1UL << TIM_CCER_CC4NE_Pos)                /*!< 0x00004000 */
#define TIM_CCER_CC4NE            TIM_CCER_CC4NE_Msk                           /*!<Capture/Compare 4 Complementary output enable */
#define TIM_CCER_CC4NP_Pos        (15U)
#define TIM_CCER_CC4NP_Msk        (0x1UL << TIM_CCER_CC4NP_Pos)                /*!< 0x00008000 */
#define TIM_CCER_CC4NP            TIM_CCER_CC4NP_Msk                           /*!<Capture/Compare 4 Complementary output Polarity */
#define TIM_CCER_CC5E_Pos         (16U)
#define TIM_CCER_CC5E_Msk         (0x1UL << TIM_CCER_CC5E_Pos)                 /*!< 0x00010000 */
#define TIM_CCER_CC5E             TIM_CCER_CC5E_Msk                            /*!<Capture/Compare 5 output enable */
#define TIM_CCER_CC5P_Pos         (17U)
#define TIM_CCER_CC5P_Msk         (0x1UL << TIM_CCER_CC5P_Pos)                 /*!< 0x00020000 */
#define TIM_CCER_CC5P             TIM_CCER_CC5P_Msk                            /*!<Capture/Compare 5 output Polarity */
#define TIM_CCER_CC6E_Pos         (20U)
#define TIM_CCER_CC6E_Msk         (0x1UL << TIM_CCER_CC6E_Pos)                 /*!< 0x00100000 */
#define TIM_CCER_CC6E             TIM_CCER_CC6E_Msk                            /*!<Capture/Compare 6 output enable */
#define TIM_CCER_CC6P_Pos         (21U)
#define TIM_CCER_CC6P_Msk         (0x1UL << TIM_CCER_CC6P_Pos)                 /*!< 0x00200000 */
#define TIM_CCER_CC6P             TIM_CCER_CC6P_Msk                            /*!<Capture/Compare 6 output Polarity */
#define TIM_CNT_CNT_Pos           (0U)
#define TIM_CNT_CNT_Msk           (0xFFFFFFFFUL << TIM_CNT_CNT_Pos)            /*!< 0xFFFFFFFF */
#define TIM_CNT_CNT               TIM_CNT_CNT_Msk                              /*!<Counter Value */
#define TIM_CNT_UIFCPY_Pos        (31U)
#define TIM_CNT_UIFCPY_Msk        (0x1UL << TIM_CNT_UIFCPY_Pos)                /*!< 0x80000000 */
#define TIM_CNT_UIFCPY            TIM_CNT_UIFCPY_Msk                           /*!<Update interrupt flag copy (if UIFREMAP=1) */
#define TIM_PSC_PSC_Pos           (0U)
#define TIM_PSC_PSC_Msk           (0xFFFFUL << TIM_PSC_PSC_Pos)                /*!< 0x0000FFFF */
#define TIM_PSC_PSC               TIM_PSC_PSC_Msk                              /*!<Prescaler Value */
#define TIM_ARR_ARR_Pos           (0U)
#define TIM_ARR_ARR_Msk           (0xFFFFFFFFUL << TIM_ARR_ARR_Pos)            /*!< 0xFFFFFFFF */
#define TIM_ARR_ARR               TIM_ARR_ARR_Msk                              /*!<Actual auto-reload Value */
#define TIM_RCR_REP_Pos           (0U)
#define TIM_RCR_REP_Msk           (0xFFFFUL << TIM_RCR_REP_Pos)                /*!< 0x0000FFFF */
#define TIM_RCR_REP               TIM_RCR_REP_Msk                              /*!<Repetition Counter Value */
#define TIM_CCR1_CCR1_Pos         (0U)
#define TIM_CCR1_CCR1_Msk         (0xFFFFFFFFUL << TIM_CCR1_CCR1_Pos)          /*!< 0xFFFFFFFF */
#define TIM_CCR1_CCR1             TIM_CCR1_CCR1_Msk                            /*!<Capture/Compare 1 Value */
#define TIM_CCR2_CCR2_Pos         (0U)
#define TIM_CCR2_CCR2_Msk         (0xFFFFFFFFUL << TIM_CCR2_CCR2_Pos)          /*!< 0xFFFFFFFF */
#define TIM_CCR2_CCR2             TIM_CCR2_CCR2_Msk                            /*!<Capture/Compare 2 Value */
#define TIM_CCR3_CCR3_Pos         (0U)
#define TIM_CCR3_CCR3_Msk         (0xFFFFFFFFUL << TIM_CCR3_CCR3_Pos)          /*!< 0xFFFFFFFF */
#define TIM_CCR3_CCR3             TIM_CCR3_CCR3_Msk                            /*!<Capture/Compare 3 Value */
#define TIM_CCR4_CCR4_Pos         (0U)
#define TIM_CCR4_CCR4_Msk         (0xFFFFFFFFUL << TIM_CCR4_CCR4_Pos)          /*!< 0xFFFFFFFF */
#define TIM_CCR4_CCR4             TIM_CCR4_CCR4_Msk                            /*!<Capture/Compare 4 Value */
#define TIM_CCR5_CCR5_Pos         (0U)
#define TIM_CCR5_CCR5_Msk         (0xFFFFFUL << TIM_CCR5_CCR5_Pos)             /*!< 0x000FFFFF */
#define TIM_CCR5_CCR5             TIM_CCR5_CCR5_Msk                            /*!<Capture/Compare 5 Value */
#define TIM_CCR5_GC5C1_Pos        (29U)
#define TIM_CCR5_GC5C1_Msk        (0x1UL << TIM_CCR5_GC5C1_Pos)                /*!< 0x20000000 */
#define TIM_CCR5_GC5C1            TIM_CCR5_GC5C1_Msk                           /*!<Group Channel 5 and Channel 1 */
#define TIM_CCR5_GC5C2_Pos        (30U)
#define TIM_CCR5_GC5C2_Msk        (0x1UL << TIM_CCR5_GC5C2_Pos)                /*!< 0x40000000 */
#define TIM_CCR5_GC5C2            TIM_CCR5_GC5C2_Msk                           /*!<Group Channel 5 and Channel 2 */
#define TIM_CCR5_GC5C3_Pos        (31U)
#define TIM_CCR5_GC5C3_Msk        (0x1UL << TIM_CCR5_GC5C3_Pos)                /*!< 0x80000000 */
#define TIM_CCR5_GC5C3            TIM_CCR5_GC5C3_Msk                           /*!<Group Channel 5 and Channel 3 */
#define TIM_CCR6_CCR6_Pos         (0U)
#define TIM_CCR6_CCR6_Msk         (0xFFFFFUL << TIM_CCR6_CCR6_Pos)             /*!< 0x000FFFFF */
#define TIM_CCR6_CCR6             TIM_CCR6_CCR6_Msk                            /*!<Capture/Compare 6 Value */
#define TIM_BDTR_DTG_Pos          (0U)
#define TIM_BDTR_DTG_Msk          (0xFFUL << TIM_BDTR_DTG_Pos)                 /*!< 0x000000FF */
#define TIM_BDTR_DTG              TIM_BDTR_DTG_Msk                             /*!<DTG[0:7] bits (Dead-Time Generator set-up) */
#define TIM_BDTR_DTG_0            (0x01UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000001 */
#define TIM_BDTR_DTG_1            (0x02UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000002 */
#define TIM_BDTR_DTG_2            (0x04UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000004 */
#define TIM_BDTR_DTG_3            (0x08UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000008 */
#define TIM_BDTR_DTG_4            (0x10UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000010 */
#define TIM_BDTR_DTG_5            (0x20UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000020 */
#define TIM_BDTR_DTG_6            (0x40UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000040 */
#define TIM_BDTR_DTG_7            (0x80UL << TIM_BDTR_DTG_Pos)                 /*!< 0x00000080 */
#define TIM_BDTR_LOCK_Pos         (8U)
#define TIM_BDTR_LOCK_Msk         (0x3UL << TIM_BDTR_LOCK_Pos)                 /*!< 0x00000300 */
#define TIM_BDTR_LOCK             TIM_BDTR_LOCK_Msk                            /*!<LOCK[1:0] bits (Lock Configuration) */
#define TIM_BDTR_LOCK_0           (0x1UL << TIM_BDTR_LOCK_Pos)                 /*!< 0x00000100 */
#define TIM_BDTR_LOCK_1           (0x2UL << TIM_BDTR_LOCK_Pos)                 /*!< 0x00000200 */
#define TIM_BDTR_OSSI_Pos         (10U)
#define TIM_BDTR_OSSI_Msk         (0x1UL << TIM_BDTR_OSSI_Pos)                 /*!< 0x00000400 */
#define TIM_BDTR_OSSR_Pos         (11U)
#define TIM_BDTR_OSSR_Msk         (0x1UL << TIM_BDTR_OSSR_Pos)                 /*!< 0x00000800 */
#define TIM_BDTR_BKE_Pos          (12U)
#define TIM_BDTR_BKE_Msk          (0x1UL << TIM_BDTR_BKE_Pos)                  /*!< 0x00001000 */
#define TIM_BDTR_BKP_Pos          (13U)
#define TIM_BDTR_BKP_Msk          (0x1UL << TIM_BDTR_BKP_Pos)                  /*!< 0x00002000 */
#define TIM_BDTR_BKP              TIM_BDTR_BKP_Msk                             /*!<Break Polarity for Break 1 */
#define TIM_BDTR_AOE_Pos          (14U)
#define TIM_BDTR_AOE_Msk          (0x1UL << TIM_BDTR_AOE_Pos)                  /*!< 0x00004000 */
#define TIM_BDTR_AOE              TIM_BDTR_AOE_Msk                             /*!<Automatic Output enable */
#define TIM_BDTR_MOE_Pos          (15U)
#define TIM_BDTR_MOE_Msk          (0x1UL << TIM_BDTR_MOE_Pos)                  /*!< 0x00008000 */
#define TIM_BDTR_BKF_Pos          (16U)
#define TIM_BDTR_BKF_Msk          (0xFUL << TIM_BDTR_BKF_Pos)                  /*!< 0x000F0000 */
#define TIM_BDTR_BKF              TIM_BDTR_BKF_Msk                             /*!<Break Filter for Break 1 */
#define TIM_BDTR_BK2F_Pos         (20U)
#define TIM_BDTR_BK2F_Msk         (0xFUL << TIM_BDTR_BK2F_Pos)                 /*!< 0x00F00000 */
#define TIM_BDTR_BK2F             TIM_BDTR_BK2F_Msk                            /*!<Break Filter for Break 2 */
#define TIM_BDTR_BK2E_Pos         (24U)
#define TIM_BDTR_BK2E_Msk         (0x1UL << TIM_BDTR_BK2E_Pos)                 /*!< 0x01000000 */
#define TIM_BDTR_BK2E             TIM_BDTR_BK2E_Msk                            /*!<Break enable for Break 2 */
#define TIM_BDTR_BK2P_Pos         (25U)
#define TIM_BDTR_BK2P_Msk         (0x1UL << TIM_BDTR_BK2P_Pos)                 /*!< 0x02000000 */
#define TIM_BDTR_BK2P             TIM_BDTR_BK2P_Msk                            /*!<Break Polarity for Break 2 */
#define TIM_BDTR_BKDSRM_Pos       (26U)
#define TIM_BDTR_BKDSRM_Msk       (0x1UL << TIM_BDTR_BKDSRM_Pos)               /*!< 0x04000000 */
#define TIM_BDTR_BKDSRM           TIM_BDTR_BKDSRM_Msk                          /*!<Break disarming/re-arming */
#define TIM_BDTR_BK2DSRM_Pos      (27U)
#define TIM_BDTR_BK2DSRM_Msk      (0x1UL << TIM_BDTR_BK2DSRM_Pos)              /*!< 0x08000000 */
#define TIM_BDTR_BK2DSRM          TIM_BDTR_BK2DSRM_Msk                         /*!<Break2 disarming/re-arming */
#define TIM_BDTR_BKBID_Pos        (28U)
#define TIM_BDTR_BKBID_Msk        (0x1UL << TIM_BDTR_BKBID_Pos)                /*!< 0x10000000 */
#define TIM_BDTR_BKBID            TIM_BDTR_BKBID_Msk                           /*!<Break BIDirectional */
#define TIM_BDTR_BK2BID_Pos       (29U)
#define TIM_BDTR_BK2BID_Msk       (0x1UL << TIM_BDTR_BK2BID_Pos)               /*!< 0x20000000 */
#define TIM_BDTR_BK2BID           TIM_BDTR_BK2BID_Msk                          /*!<Break2 BIDirectional */
#define TIM_DCR_DBA_Pos           (0U)
#define TIM_DCR_DBA_Msk           (0x1FUL << TIM_DCR_DBA_Pos)                  /*!< 0x0000001F */
#define TIM_DCR_DBA               TIM_DCR_DBA_Msk                              /*!<DBA[4:0] bits (DMA Base Address) */
#define TIM_DCR_DBA_0             (0x01UL << TIM_DCR_DBA_Pos)                  /*!< 0x00000001 */
#define TIM_DCR_DBA_1             (0x02UL << TIM_DCR_DBA_Pos)                  /*!< 0x00000002 */
#define TIM_DCR_DBA_2             (0x04UL << TIM_DCR_DBA_Pos)                  /*!< 0x00000004 */
#define TIM_DCR_DBA_3             (0x08UL << TIM_DCR_DBA_Pos)                  /*!< 0x00000008 */
#define TIM_DCR_DBA_4             (0x10UL << TIM_DCR_DBA_Pos)                  /*!< 0x00000010 */
#define TIM_DCR_DBL_Pos           (8U)
#define TIM_DCR_DBL_Msk           (0x1FUL << TIM_DCR_DBL_Pos)                  /*!< 0x00001F00 */
#define TIM_DCR_DBL               TIM_DCR_DBL_Msk                              /*!<DBL[4:0] bits (DMA Burst Length) */
#define TIM_DCR_DBL_0             (0x01UL << TIM_DCR_DBL_Pos)                  /*!< 0x00000100 */
#define TIM_DCR_DBL_1             (0x02UL << TIM_DCR_DBL_Pos)                  /*!< 0x00000200 */
#define TIM_DCR_DBL_2             (0x04UL << TIM_DCR_DBL_Pos)                  /*!< 0x00000400 */
#define TIM_DCR_DBL_3             (0x08UL << TIM_DCR_DBL_Pos)                  /*!< 0x00000800 */
#define TIM_DCR_DBL_4             (0x10UL << TIM_DCR_DBL_Pos)                  /*!< 0x00001000 */
#define TIM1_AF1_BKINE_Pos        (0U)
#define TIM1_AF1_BKINE_Msk        (0x1UL << TIM1_AF1_BKINE_Pos)                /*!< 0x00000001 */
#define TIM1_AF1_BKINE            TIM1_AF1_BKINE_Msk                           /*!<BRK BKIN input enable */
#define TIM1_AF1_BKCMP1E_Pos      (1U)
#define TIM1_AF1_BKCMP1E_Msk      (0x1UL << TIM1_AF1_BKCMP1E_Pos)              /*!< 0x00000002 */
#define TIM1_AF1_BKCMP1E          TIM1_AF1_BKCMP1E_Msk                         /*!<BRK COMP1 enable */
#define TIM1_AF1_BKCMP2E_Pos      (2U)
#define TIM1_AF1_BKCMP2E_Msk      (0x1UL << TIM1_AF1_BKCMP2E_Pos)              /*!< 0x00000004 */
#define TIM1_AF1_BKCMP2E          TIM1_AF1_BKCMP2E_Msk                         /*!<BRK COMP2 enable */
#define TIM1_AF1_BKCMP3E_Pos      (3U)
#define TIM1_AF1_BKCMP3E_Msk      (0x1UL << TIM1_AF1_BKCMP3E_Pos)              /*!< 0x00000008 */
#define TIM1_AF1_BKCMP3E          TIM1_AF1_BKCMP3E_Msk                         /*!<BRK COMP3 enable */
#define TIM1_AF1_BKCMP4E_Pos      (4U)
#define TIM1_AF1_BKCMP4E_Msk      (0x1UL << TIM1_AF1_BKCMP4E_Pos)              /*!< 0x00000010 */
#define TIM1_AF1_BKCMP4E          TIM1_AF1_BKCMP4E_Msk                         /*!<BRK COMP4 enable */
#define TIM1_AF1_BKINP_Pos        (9U)
#define TIM1_AF1_BKINP_Msk        (0x1UL << TIM1_AF1_BKINP_Pos)                /*!< 0x00000200 */
#define TIM1_AF1_BKINP            TIM1_AF1_BKINP_Msk                           /*!<BRK BKIN input polarity */
#define TIM1_AF1_BKCMP1P_Pos      (10U)
#define TIM1_AF1_BKCMP1P_Msk      (0x1UL << TIM1_AF1_BKCMP1P_Pos)              /*!< 0x00000400 */
#define TIM1_AF1_BKCMP1P          TIM1_AF1_BKCMP1P_Msk                         /*!<BRK COMP1 input polarity */
#define TIM1_AF1_BKCMP2P_Pos      (11U)
#define TIM1_AF1_BKCMP2P_Msk      (0x1UL << TIM1_AF1_BKCMP2P_Pos)              /*!< 0x00000800 */
#define TIM1_AF1_BKCMP2P          TIM1_AF1_BKCMP2P_Msk                         /*!<BRK COMP2 input polarity */
#define TIM1_AF1_BKCMP3P_Pos      (12U)
#define TIM1_AF1_BKCMP3P_Msk      (0x1UL << TIM1_AF1_BKCMP3P_Pos)              /*!< 0x00001000 */
#define TIM1_AF1_BKCMP3P          TIM1_AF1_BKCMP3P_Msk                         /*!<BRK COMP3 input polarity */
#define TIM1_AF1_BKCMP4P_Pos      (13U)
#define TIM1_AF1_BKCMP4P_Msk      (0x1UL << TIM1_AF1_BKCMP4P_Pos)              /*!< 0x00002000 */
#define TIM1_AF1_BKCMP4P          TIM1_AF1_BKCMP4P_Msk                         /*!<BRK COMP4 input polarity */
#define TIM1_AF1_ETRSEL_Pos       (14U)
#define TIM1_AF1_ETRSEL_Msk       (0xFUL << TIM1_AF1_ETRSEL_Pos)               /*!< 0x0003C000 */
#define TIM1_AF1_ETRSEL           TIM1_AF1_ETRSEL_Msk                          /*!<ETRSEL[3:0] bits (TIM1 ETR source selection) */
#define TIM1_AF1_ETRSEL_0         (0x1UL << TIM1_AF1_ETRSEL_Pos)               /*!< 0x00004000 */
#define TIM1_AF1_ETRSEL_1         (0x2UL << TIM1_AF1_ETRSEL_Pos)               /*!< 0x00008000 */
#define TIM1_AF1_ETRSEL_2         (0x4UL << TIM1_AF1_ETRSEL_Pos)               /*!< 0x00010000 */
#define TIM1_AF1_ETRSEL_3         (0x8UL << TIM1_AF1_ETRSEL_Pos)               /*!< 0x00020000 */
#define TIM_OR_HSE32EN_Pos       (0U)
#define TIM_OR_HSE32EN_Msk       (0x1UL << TIM_OR_HSE32EN_Pos)                  /*!< 0x00000001 */
#define TIM_OR_HSE32EN           TIM_OR_HSE32EN_Msk                             /*!< HSE/32 clock enable */
#define TIM_TISEL_TI1SEL_Pos      (0U)
#define TIM_TISEL_TI1SEL_Msk      (0xFUL << TIM_TISEL_TI1SEL_Pos)              /*!< 0x0000000F */
#define TIM_TISEL_TI1SEL          TIM_TISEL_TI1SEL_Msk                         /*!<TI1SEL[3:0] bits (TIM1 TI1 SEL)*/
#define TIM_TISEL_TI1SEL_0        (0x1UL << TIM_TISEL_TI1SEL_Pos)              /*!< 0x00000001 */
#define TIM_TISEL_TI1SEL_1        (0x2UL << TIM_TISEL_TI1SEL_Pos)              /*!< 0x00000002 */
#define TIM_TISEL_TI1SEL_2        (0x4UL << TIM_TISEL_TI1SEL_Pos)              /*!< 0x00000004 */
#define TIM_TISEL_TI1SEL_3        (0x8UL << TIM_TISEL_TI1SEL_Pos)              /*!< 0x00000008 */
#define TIM_TISEL_TI2SEL_Pos      (8U)
#define TIM_TISEL_TI2SEL_Msk      (0xFUL << TIM_TISEL_TI2SEL_Pos)              /*!< 0x00000F00 */
#define TIM_TISEL_TI2SEL          TIM_TISEL_TI2SEL_Msk                         /*!<TI2SEL[3:0] bits (TIM1 TI2 SEL)*/
#define TIM_TISEL_TI2SEL_0        (0x1UL << TIM_TISEL_TI2SEL_Pos)              /*!< 0x00000100 */
#define TIM_TISEL_TI2SEL_1        (0x2UL << TIM_TISEL_TI2SEL_Pos)              /*!< 0x00000200 */
#define TIM_TISEL_TI2SEL_2        (0x4UL << TIM_TISEL_TI2SEL_Pos)              /*!< 0x00000400 */
#define TIM_TISEL_TI2SEL_3        (0x8UL << TIM_TISEL_TI2SEL_Pos)              /*!< 0x00000800 */
#define TIM_TISEL_TI3SEL_Pos      (16U)
#define TIM_TISEL_TI3SEL_Msk      (0xFUL << TIM_TISEL_TI3SEL_Pos)              /*!< 0x000F0000 */
#define TIM_TISEL_TI3SEL          TIM_TISEL_TI3SEL_Msk                         /*!<TI3SEL[3:0] bits (TIM1 TI3 SEL)*/
#define TIM_TISEL_TI3SEL_0        (0x1UL << TIM_TISEL_TI3SEL_Pos)              /*!< 0x00010000 */
#define TIM_TISEL_TI3SEL_1        (0x2UL << TIM_TISEL_TI3SEL_Pos)              /*!< 0x00020000 */
#define TIM_TISEL_TI3SEL_2        (0x4UL << TIM_TISEL_TI3SEL_Pos)              /*!< 0x00040000 */
#define TIM_TISEL_TI3SEL_3        (0x8UL << TIM_TISEL_TI3SEL_Pos)              /*!< 0x00080000 */
#define TIM_TISEL_TI4SEL_Pos      (24U)
#define TIM_TISEL_TI4SEL_Msk      (0xFUL << TIM_TISEL_TI4SEL_Pos)              /*!< 0x0F000000 */
#define TIM_TISEL_TI4SEL          TIM_TISEL_TI4SEL_Msk                         /*!<TI4SEL[3:0] bits (TIM1 TI4 SEL)*/
#define TIM_TISEL_TI4SEL_0        (0x1UL << TIM_TISEL_TI4SEL_Pos)              /*!< 0x01000000 */
#define TIM_TISEL_TI4SEL_1        (0x2UL << TIM_TISEL_TI4SEL_Pos)              /*!< 0x02000000 */
#define TIM_TISEL_TI4SEL_2        (0x4UL << TIM_TISEL_TI4SEL_Pos)              /*!< 0x04000000 */
#define TIM_TISEL_TI4SEL_3        (0x8UL << TIM_TISEL_TI4SEL_Pos)              /*!< 0x08000000 */
#define TIM_DTR2_DTGF_Pos      (0U)
#define TIM_DTR2_DTGF_Msk      (0xFFUL << TIM_DTR2_DTGF_Pos)                /*!< 0x0000000F */
#define TIM_DTR2_DTGF          TIM_DTR2_DTGF_Msk                            /*!<DTGF[7:0] bits (Deadtime falling edge generator setup)*/
#define TIM_DTR2_DTGF_0        (0x01UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000001 */
#define TIM_DTR2_DTGF_1        (0x02UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000002 */
#define TIM_DTR2_DTGF_2        (0x04UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000004 */
#define TIM_DTR2_DTGF_3        (0x08UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000008 */
#define TIM_DTR2_DTGF_4        (0x10UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000010 */
#define TIM_DTR2_DTGF_5        (0x20UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000020 */
#define TIM_DTR2_DTGF_6        (0x40UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000040 */
#define TIM_DTR2_DTGF_7        (0x80UL << TIM_DTR2_DTGF_Pos)                /*!< 0x00000080 */
#define TIM_DTR2_DTAE_Pos      (16U)
#define TIM_DTR2_DTAE_Msk      (0x1UL << TIM_DTR2_DTAE_Pos)                 /*!< 0x00004000 */
#define TIM_DTR2_DTAE          TIM_DTR2_DTAE_Msk                            /*!<Deadtime asymmetric enable */
#define TIM_DTR2_DTPE_Pos      (17U)
#define TIM_DTR2_DTPE_Msk      (0x1UL << TIM_DTR2_DTPE_Pos)                 /*!< 0x00008000 */
#define TIM_DTR2_DTPE          TIM_DTR2_DTPE_Msk                            /*!<Deadtime prelaod enable */
#define TIM_ECR_IE_Pos       (0U)
#define TIM_ECR_IE_Msk       (0x1UL << TIM_ECR_IE_Pos)                   /*!< 0x00000001 */
#define TIM_ECR_IE           TIM_ECR_IE_Msk                              /*!<Index enable */
#define TIM_ECR_IDIR_Pos      (1U)
#define TIM_ECR_IDIR_Msk      (0x3UL << TIM_ECR_IDIR_Pos)                 /*!< 0x00000006 */
#define TIM_ECR_IDIR          TIM_ECR_IDIR_Msk                            /*!<IDIR[1:0] bits (Index direction)*/
#define TIM_ECR_IDIR_0        (0x01UL << TIM_ECR_IDIR_Pos)                /*!< 0x00000001 */
#define TIM_ECR_IDIR_1        (0x02UL << TIM_ECR_IDIR_Pos)                /*!< 0x00000002 */
#define TIM_ECR_FIDX_Pos      (5U)
#define TIM_ECR_FIDX_Msk      (0x1UL << TIM_ECR_FIDX_Pos)                 /*!< 0x00000020 */
#define TIM_ECR_FIDX          TIM_ECR_FIDX_Msk                            /*!<First index enable */
#define TIM_ECR_IPOS_Pos      (6U)
#define TIM_ECR_IPOS_Msk      (0x3UL << TIM_ECR_IPOS_Pos)                 /*!< 0x0000000C0 */
#define TIM_ECR_IPOS          TIM_ECR_IPOS_Msk                            /*!<IPOS[1:0] bits (Index positioning)*/
#define TIM_ECR_IPOS_0        (0x01UL << TIM_ECR_IPOS_Pos)                /*!< 0x00000001 */
#define TIM_ECR_IPOS_1        (0x02UL << TIM_ECR_IPOS_Pos)                /*!< 0x00000002 */
#define TIM_ECR_PW_Pos        (16U)
#define TIM_ECR_PW_Msk        (0xFFUL << TIM_ECR_PW_Pos)                  /*!< 0x00FF0000 */
#define TIM_ECR_PW            TIM_ECR_PW_Msk                              /*!<PW[7:0] bits (Pulse width)*/
#define TIM_ECR_PW_0          (0x01UL << TIM_ECR_PW_Pos)                  /*!< 0x00010000 */
#define TIM_ECR_PW_1          (0x02UL << TIM_ECR_PW_Pos)                  /*!< 0x00020000 */
#define TIM_ECR_PW_2          (0x04UL << TIM_ECR_PW_Pos)                  /*!< 0x00040000 */
#define TIM_ECR_PW_3          (0x08UL << TIM_ECR_PW_Pos)                  /*!< 0x00080000 */
#define TIM_ECR_PW_4          (0x10UL << TIM_ECR_PW_Pos)                  /*!< 0x00100000 */
#define TIM_ECR_PW_5          (0x20UL << TIM_ECR_PW_Pos)                  /*!< 0x00200000 */
#define TIM_ECR_PW_6          (0x40UL << TIM_ECR_PW_Pos)                  /*!< 0x00400000 */
#define TIM_ECR_PW_7          (0x80UL << TIM_ECR_PW_Pos)                  /*!< 0x00800000 */
#define TIM_ECR_PWPRSC_Pos    (24U)
#define TIM_ECR_PWPRSC_Msk    (0x7UL << TIM_ECR_PWPRSC_Pos)               /*!< 0x07000000 */
#define TIM_ECR_PWPRSC        TIM_ECR_PWPRSC_Msk                          /*!<PWPRSC[2:0] bits (Pulse width prescaler)*/
#define TIM_ECR_PWPRSC_0      (0x01UL << TIM_ECR_PWPRSC_Pos)              /*!< 0x01000000 */
#define TIM_ECR_PWPRSC_1      (0x02UL << TIM_ECR_PWPRSC_Pos)              /*!< 0x02000000 */
#define TIM_ECR_PWPRSC_2      (0x04UL << TIM_ECR_PWPRSC_Pos)              /*!< 0x04000000 */
#define TIM_DMAR_DMAB_Pos         (0U)
#define TIM_DMAR_DMAB_Msk         (0xFFFFFFFFUL << TIM_DMAR_DMAB_Pos)     /*!< 0xFFFFFFFF */
#define TIM_DMAR_DMAB             TIM_DMAR_DMAB_Msk                       /*!<DMA register for burst accesses */

#define GPIO_PIN_2 4U
#define GPIO_PIN_6 64U
#define GPIO_MODE_AF_PP 2U
#define GPIO_SPEED_FREQ_VERY_HIGH 3U
#define GPIO_PIN_SET 1U
#define GPIO_AF4_TIM8 4U
#define __HAL_RCC_GPIOC_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_GPIOD_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_TIM8_CLK_ENABLE() do{}while(0)
#define __HAL_RCC_TIM8_FORCE_RESET() do{}while(0)
#define __HAL_RCC_TIM8_RELEASE_RESET() do{}while(0)

struct GPIO_InitTypeDef {uint32_t Mode,Pull,Speed,Pin,Alternate;};
static uint32_t SystemCoreClock=170000000U,mic_local_stop_latched;
static uint16_t bus=10;static uint32_t now_ms;
static bool mic_local_stop_blocked(){return mic_local_stop_latched;}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR&=~TIM_BDTR_MOE;}
static void LL_TIM_ClearFlag_UPDATE(Timer*){}
static void LL_TIM_EnableIT_UPDATE(Timer*t){t->DIER|=1;}
static void LL_TIM_DisableIT_UPDATE(Timer*t){t->DIER&=~1U;}
static void HAL_GPIO_WritePin(GPIO*g,uint16_t pins,unsigned set){if(set){g->ODR|=pins;g->IDR|=pins;}else{g->ODR&=~pins;g->IDR&=~pins;}}
static void HAL_GPIO_Init(GPIO*g,GPIO_InitTypeDef*q){
 for(unsigned i=0;i<16;i++)if((q->Pin&(1U<<i))&&!(g->LCKR&(1U<<i))){
  g->MODER=(g->MODER&~(3U<<(2*i)))|(q->Mode<<(2*i));
  if(q->Mode==GPIO_MODE_AF_PP){unsigned at=(i%8)*4;g->AFR[i/8]=(g->AFR[i/8]&~(15U<<at))|(q->Alternate<<at);}
 }
}
static uint32_t HAL_GetTick(){return now_ms;}

static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}
static uint32_t MC_GetCurrentFaultsMotor1(){return 4;}
static uint32_t MC_GetOccurredFaultsMotor1(){return 1028;}
struct RampExtMngr_Handle_t {uint32_t FrequencyHz=500;};
static RampExtMngr_Handle_t original_ramp;
struct ACIM_VF_Handle_t {int bVF_Mode=0;float fFlux_Freq_Hz=0,fFlux_Freq_rads=0,fFlux_Angle_rad=0,fVoutMax_PWM_Mod_V=0,fCalcAngleExecFreqHz=16000;RampExtMngr_Handle_t*pRMNGR=&original_ramp;};
static ACIM_VF_Handle_t original;
static ACIM_VF_Handle_t*pACIM_VF_Component_M1=&original;
static unsigned math_calls,fail_math;
static void REMNG_Init(RampExtMngr_Handle_t*){}
static bool ACIM_VF_ExecRamp(ACIM_VF_Handle_t*,int16_t,unsigned){return true;}
static float ACIM_VF_FluxFreqCalc(ACIM_VF_Handle_t*p){p->fFlux_Freq_Hz+=.0033333333f;if(p->fFlux_Freq_Hz>5)p->fFlux_Freq_Hz=5;return p->fFlux_Freq_Hz;}
static void ACIM_VF_CalcAngle(ACIM_VF_Handle_t*p){p->fFlux_Angle_rad+=p->fFlux_Freq_rads/16000;}
static uint16_t ACIM_VF_Controller(ACIM_VF_Handle_t*p){
 ++math_calls;unsigned n=unsigned(p->fFlux_Freq_Hz*10);tim.CCR1=2600+n;tim.CCR2=2700-n;tim.CCR3=2650+n/2;return uint16_t(fail_math);
}

#define VF_OL 1
struct RCCFake {uint32_t AHB2ENR=0,CCIPR=0;};static RCCFake rcc;
#define RCC (&rcc)
struct SysFake {uint32_t LOAD=169999;};static SysFake syst;
#define SysTick (&syst)
static void LL_TIM_EnableIT_BRK(Timer*t){t->DIER|=128;}
static void LL_TIM_DisableIT_BRK(Timer*t){t->DIER&=~128U;}
void mic_encoder_load_snapshot(uint32_t*v){std::memset(v,0,17*4);v[0]=now_ms/5;v[11]=7;}

struct AdcFake {uint32_t CR=1,ISR=64,JSQR=0;};static AdcFake a1,a2;
#define ADC1 (&a1)
#define ADC2 (&a2)
#define ADC_ISR_JEOS 64U
#define ADC_ISR_JQOVF 1024U
void mic_io_uart_snapshot(uint32_t*v){for(unsigned i=0;i<16;i++)v[i]=0;v[2]=now_ms/20+1;v[6]=now_ms/20+1;v[13]=now_ms;}
#define publish_ms io_publish_ms
#include "combined_io_diag.c"
#undef publish_ms
#include "pin_pwm_diag.c"

static unsigned checks;
static void test(bool v){++checks;if(!v){fprintf(stderr,"pin_check%u\n",checks);exit(1);}}
static void reset(){
 tim=Timer{};pa=GPIO{};pb=GPIO{};dwt={};now_ms=0;mic_local_stop_latched=0;
 state=reason=attempted=start=stop=elapsed=phase=updates=cached_at=max_cost=max_gap=break_sr=0;
 previous_irq=previous_poll=max_poll_gap=seq=publish_ms=0;fail_math=0;
 for(unsigned i=7;i<=10;i++)pa.MODER|=2U<<(2*i);
 pa.AFR[0]=6U<<28;pa.AFR[1]=0x666;pa.IDR=64;pb.MODER=10;pb.AFR[0]=0x66;
 adc_seen=200;adc_active=adc_at=adc_enter=adc_cost=adc_gap=adc_bad=adc_previous=0;
 sequence=0;uart_flags=0;uart_at=0;uart_frames=uart_completed=1;a1=AdcFake{};a2=AdcFake{};
 mic_io_init();mic_io_poll();mic_pin_init();
}
static void request(){mic_pin_request=PIN_REQUEST;mic_pin_poll();}
int main(){
 reset();test(!state);test(!(tim.BDTR&TIM_BDTR_MOE));request();test(state==1);
 for(unsigned n=1;n<=80000;n++){
  dwt.CYCCNT=n*10625U;now_ms=dwt.CYCCNT/170000;
  mic_io_adc_enter();if(n%8==0){mic_io_poll();mic_pin_poll();}mic_pin_irq();mic_io_adc_exit();
  if(n<16000){test(phase==1);test(!(tim.BDTR&TIM_BDTR_MOE));}
  if(n>=16000&&n<48000){test(phase==2);test(tim.BDTR&TIM_BDTR_MOE);test(tim.CCR1==1328&&tim.CCR2==2656&&tim.CCR3==3984);}
  if(n>=48000&&n<80000){test(phase==3);test(tim.BDTR&TIM_BDTR_MOE);}
 }
 test(state==2&&reason==0&&elapsed==850000000);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(tim.DIER&1));
 test(boundaries[2]-boundaries[0]==200);test(boundaries[4]-boundaries[2]==400);test(boundaries[6]-boundaries[4]==400);
 test(adc_active==80000);request();test(state==2);test(!(tim.BDTR&TIM_BDTR_MOE));
 now_ms+=50;mic_pin_poll();uint32_t words[64];for(unsigned i=0;i<64;i++)words[i]=mic_pin_report[i];
 test(words[4]==words[61]&&!(words[4]&1));test(ld_crc(words+5,56)==words[62]);
 for(unsigned why=0;why<7;why++){
  reset();request();dwt.CYCCNT=170000000;cached_at=adc_at=dwt.CYCCNT;mic_io_poll();mic_pin_irq();test(phase==2);
  if(why==0)pa.IDR=0;
  if(why==1)mic_local_stop_latched=1;
  if(why==2)tim.BDTR^=TIM_BDTR_BKE;
  if(why==3)tim.SR|=TIM_SR_BIF;
  if(why==4)cached_at-=850001;
  if(why==5)tim.BDTR&=~TIM_BDTR_MOE;
  if(why==6)fail_math=1;
  mic_pin_irq();test(state==3&&reason);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(tim.DIER&1));
 }
 reset();pa.MODER=0;request();test(state==4&&reason);test(!(tim.BDTR&TIM_BDTR_MOE));
 reset();request();mic_pin_request=PIN_CANCEL;mic_pin_poll();test(state==3&&reason==128);
 reset();request();mic_pin_break();test(state==3&&reason==4);test(!(tim.BDTR&TIM_BDTR_MOE));

 reset();request();dwt.CYCCNT=170000000;cached_at=dwt.CYCCNT;adc_at=dwt.CYCCNT-850001;mic_io_poll();mic_pin_irq();test(state==3&&(reason&256));test(!(tim.BDTR&TIM_BDTR_MOE));
 reset();request();uart_flags=1;mic_pin_irq();test(state==3&&(reason&512));
 reset();request();adc_bad=1;mic_pin_irq();test(state==3&&(reason&256));
 reset();request();uart_at=0;now_ms=301;mic_pin_irq();test(state==3&&(reason&512));
 printf("{\"passed\":true,\"checks\":%u,\"actual_hardware_calls\":0}\n",checks);
}
