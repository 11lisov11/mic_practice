"""Conservative raw/group mean-variance checks for correlated zero-input noise."""
def apply_core(s):
    old='  uint32_t zero_energy[4];'
    assert s.count(old)==1
    s=s.replace(old,old+'\n  uint64_t zero_group_energy[4];\n  uint32_t zero_group_previous[4];')
    anchor='  if(raw<16 || raw>4079)s->zero_energy[path]|=0x80000000UL;'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'''
  if((s->count[path]&63U)==0U) {
    int32_t group_sum=(int32_t)(s->sum[path]-s->zero_group_previous[path])-2048*64;
    s->zero_group_previous[path]=s->sum[path];
    s->zero_group_energy[path]+=(uint64_t)((int64_t)group_sum*group_sum);
  }''')
    anchor='  memset(s->zero_energy,0,sizeof(s->zero_energy));'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'''
  memset(s->zero_group_energy,0,sizeof(s->zero_group_energy));
  memset(s->zero_group_previous,0,sizeof(s->zero_group_previous));''')
    s=s.replace('This estimate assumes stationary noise; block consistency is separate.',
        'Use the larger of raw-sample and four64-sample-group mean variance.\n     * This is an estimate; three consecutive block means must also agree.')
    anchor='    if(energy*9U>(uint64_t)denominator*4U){s->zero_last_bad|=1;bad_paths|=1U<<i;}'
    assert s.count(anchor)==1
    s=s.replace(anchor,'''    uint64_t group_energy=4U*s->zero_group_energy[i]-
                    (uint64_t)((int64_t)residual_sum*residual_sum);
    const uint32_t group_denominator=64U*64U*4U*4U*3U;
    if(energy*9U>(uint64_t)denominator*4U ||
       group_energy*9U>(uint64_t)group_denominator*4U){s->zero_last_bad|=1;bad_paths|=1U<<i;}''')
    anchor='    unsigned q=(unsigned)((energy+denominator/256U)/(denominator/128U));'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'''
    unsigned group_q=(unsigned)((group_energy+group_denominator/256U)/(group_denominator/128U));
    if(group_q>q)q=group_q;''')
    return s
