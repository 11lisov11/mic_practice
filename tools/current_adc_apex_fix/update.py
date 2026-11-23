"""Small exact source transformation from sealed2508 ADC IRQ."""
from prepare_current_shunt_monitor import once

FLAGS='''/* Pack only private ISR flags to make room for a full32-bit context epoch.
 * The public cm_core layout and trace wire remain byte-for-byte unchanged. */
static struct {
  uint8_t pair:2,valid:1,active:1,init:1,lost:1;
} adc_flags;
typedef char adc_flags_must_be_one_byte[(sizeof(adc_flags)==1)?1:-1];
#define pending_pair adc_flags.pair
#define pending_valid adc_flags.valid
#define pending_active adc_flags.active
#define initialized adc_flags.init
#define lost_sync adc_flags.lost
static uint32_t pending_epoch;'''

def apply_irq(s):
    s=once(s,'  if(!peak.frozen){jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;}',
        '''  /* JQM=1 must be EMPTY after this single injected sequence. */
  jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;''')
    s=once(s,'  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF))lost_sync=1;',
        '  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF) || jsqr1 || jsqr2)lost_sync=1;')
    s=once(s,'  uint8_t early=(uint8_t)(!direction && count>=old_trigger && count<TIM1->ARR-24U);',
        '''  /* The apex is NOT the update deadline. Check time until bottom UEV. */
  uint8_t early=(uint8_t)mic_adc_publish_in_time(TIM1->ARR,count,direction,old_trigger);''')
    s=once(s,'  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&\n      current_ccr[3]==old_trigger);',
        '''  uint8_t stamp_ok=(uint8_t)(pending_epoch==epoch0);
  uint8_t bottom_ok=(uint8_t)mic_adc_bottom_update(TIM1->ARR,current_update_cnt,current_update_cr1&TIM_CR1_DIR);
  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&
      current_ccr[3]==old_trigger && stamp_ok && bottom_ok);''')
    s=once(s,'  if(!active){plan.trigger=TIM1->ARR-CM_BEFORE_TOP;plan.valid=1;}',
        '  if(!active){plan.trigger=TIM1->ARR-CM_IDLE_BEFORE_TOP;plan.valid=1;}')
    s=once(s,'  pending_valid=(uint8_t)(early && plan.valid && epoch0==peak_epoch);',
        '  pending_valid=(uint8_t)(early && plan.valid && bottom_ok && epoch0==peak_epoch);')
    s=once(s,'  queue_pair(pair);','  pending_epoch=epoch0+1U;\n  queue_pair(pair);')
    s=once(s,'            bus<=20U && both && !lost_sync && early && context_ok);',
        '''            bus<=20U && both && !lost_sync && early && !active);
  /* With MOE off MCSDK may mask UPDATE IRQ. Autonull needs the freshly
   * completed single mux context (JQM empty), not an unserviced UEV stamp.
   * Its500ms settling and unchanged three-block/statistical gates stay in core. */''')
    s=once(s,'        (!geometry_ok?1024:0));',
        '        (!geometry_ok?1024:0)|(!early?2048:0)|(!stamp_ok?4096:0)|((jsqr1||jsqr2)?8192:0));')
    return s
