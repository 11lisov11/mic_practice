    if peer==2026102704:
        for suffix in ('isr','cr1','cr2','gpio','cycles'):
            result['cleanup_terminal_'+suffix]=result.pop('post_reset_'+suffix)
        flags=w[4]>>26
        result.update(cleanup_flags=flags,cleanup_stop_seen=bool(flags&1),cleanup_forced=bool(flags&2),
            cleanup_arlo=bool(flags&4),cleanup_stop_requested=bool(flags&8),cleanup_expired=bool(flags&16),
            cleanup_no_transfer=bool(flags&32),cleanup_duration_us=((w[39]-w[3])&0xffffffff)*1e6/w[32])
