"""Validate the new estimated-mean zero contract, with complete pre-START history."""
def ready(s):
    try:
        if not ((s['fw_build'],s['mc_fw_build']) in ((2026102505,2026102506),(2026102507,2026102508),(2026102509,2026102510),(2026102513,2026102510),(2026102515,2026102510),(2026102516,2026102510),(2026102517,2026102510),(2026102518,2026102510),(2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704))
                and s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
                and not (s.get('mc_current_flags',0)&16)
                and 3<=s['mc_current_zero_attempts']<=8
                and 0<=s['mc_current_quality_age_ms']<1500
                and 0<=s['mc_current_age_ms']<750 and 0<=s['mc_age_ms']<300
                and len(s['mc_current_zero_spans'])==4
                and all(0<=v<=4095 for v in s['mc_current_zero_spans'])
                and len(s['mc_current_offsets_adc'])==4
                and all(1600<=v<=2500 for v in s['mc_current_offsets_adc'])):
            return False
        history=s.get('mc_zero_history')
        if s.get('mc_zero_history_valid')!=1 or not isinstance(history,list):
            return False
        if len(history)!=s['mc_current_zero_attempts']:
            return False
        last=history[-3:]
        if ([b['stable'] for b in last]!=[1,2,3] or last[0]['reject_flags'] not in (0,4)
                or any(b['reject_flags'] for b in last[1:])):
            return False
        if any(max(b['means_adc'][i] for b in last)-min(b['means_adc'][i] for b in last)>2 for i in range(4)):
            return False
        return True
    except (KeyError,TypeError,ValueError,IndexError):
        return False
