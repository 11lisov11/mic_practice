"""Pure offline schema4 decoder. Raw bytes remain authoritative for replay."""
import math
import struct


def decode_nis_replay(raw):
    if len(raw)!=456:raise ValueError('NIS replay length')
    pre=struct.unpack_from('<42f2I',raw,0)
    motor=struct.unpack_from('<7fI5f',raw,176)
    inputs=struct.unpack_from('<5f',raw,228)
    post=struct.unpack_from('<49f3I',raw,248)
    # A replay is the first NIS validity refusal after the unchanged500-step
    # warmup. Nonfinite covariances can still be represented without JSON NaN.
    if pre[42]<499 or not (post[42]>=25) or post[51]>7:
        raise ValueError('NIS replay event/counters/result')
    def finite(values):return [x if math.isfinite(x) else None for x in values]
    return dict(available=True,raw_hex=raw.hex(),prior_state=finite(pre[:6]),
        prior_covariance=[finite(pre[6+6*i:12+6*i]) for i in range(6)],
        prior_steps=pre[42],prior_rejected=pre[43],
        motor=dict(zip(('rs','rr','ls','lr','lm','j','b','poles','flux','current_limit',
                        'trip_current','current_bw','speed_bw'),motor)),
        inputs=dict(zip(('ia_A','ib_A','va_V','vb_V','dt_s'),finite(inputs))),
        post_state=finite(post[:6]),post_covariance=[finite(post[6+6*i:12+6*i]) for i in range(6)],
        nis=finite([post[42]])[0],predicted_current_A=finite(post[43:45]),innovation_A=finite(post[45:47]),
        innovation_variance_A2=finite(post[47:49]),fpscr=post[49],post_rejected=post[50],
        result=post[51],post_steps=pre[42]+(post[51]==0),
        scope='one exact EKF call; not the entire physical current/voltage history')
