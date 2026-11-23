  /* Preserve the original fixed-R NIS watchdog independently of the corrected
   * measurement coordinates. Exact sequential/Joseph beta expression; no larger
   * noise matrix may hide an event from the existing >50/20-step stop. */
  const float gs0=cov[0][0]+.0004f,ge0=ia-o->x[0];
  if(!isfinite(gs0)||gs0<=0)return MA_OBSERVER;
  const float gk1=cov[1][0]/gs0;
  const float gs1=cov[1][1]-gk1*cov[0][1]-gk1*cov[1][0]+gk1*gk1*gs0+.0004f;
  const float ge1=ib-(o->x[1]+gk1*ge0);
  if(!isfinite(gs1)||gs1<=0)return MA_OBSERVER;
  const float guard_nis=ge0*ge0/gs0+ge1*ge1/gs1;
  if(!isfinite(guard_nis))return MA_OBSERVER;
