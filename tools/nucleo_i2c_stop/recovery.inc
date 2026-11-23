static inline void ec_idle(ec_state *e){e->state=0;e->prepare=0;e->recovering=0;e->have_free_since=false;}
static inline void ec_elapsed(ec_state *e,uint32_t cycles,uint32_t hz){
  uint32_t us=(cycles-e->begin_cycles)/(hz/1000000U);e->duration_us=(uint16_t)(us>65535U?65535U:us);
}
static inline void ec_error_done(ec_state *e,ec_io *io,uint32_t cycles,uint32_t hz,bool forced){
  if(forced){e->cleanup_flags|=EC_CL_FORCED;ec_inc32(&e->forced_resets);ec_inc16(&e->resets);}
  // Freeze terminal flags/levels BEFORE clearing STOPF or disabling PE.
  io->terminal(io->ctx,e->cleanup_flags);
  if(forced)io->reset(io->ctx);
  else {io->clear(io->ctx);io->park(io->ctx);io->flush_tx(io->ctx);}
  ec_elapsed(e,cycles,hz);ec_idle(e);
}
static inline void ec_recover(ec_state *e,ec_io *io,uint32_t ms,uint32_t cycles,uint32_t hz,uint32_t isr){
  (void)ms;
  if(isr&EC_STOPF)e->cleanup_flags|=EC_CL_STOP;
  if(isr&EC_ARLOF){e->cleanup_flags|=EC_CL_ARLO;e->recovering=3;}
  const bool free=!(isr&EC_BUSYF)&&io->lines(io->ctx)==3U;
  if(e->recovering==3){
    // Hardware releases arbitration; never send STOP into another transfer.
    if(free){
      if(!e->have_free_since){e->have_free_since=true;e->free_since_cycles=cycles;}
      else if((uint32_t)(cycles-e->free_since_cycles)>=(hz/1000000U)*EC_FREE_US){ec_error_done(e,io,cycles,hz,false);return;}
    }else e->have_free_since=false;
  }else if((isr&EC_STOPF)&&free){
    ec_inc32(&e->clean_stops);ec_error_done(e,io,cycles,hz,false);return;
  }
  const uint32_t elapsed=cycles-e->abort_cycles;
  if(elapsed>=(hz/1000000U)*EC_CLEANUP_US){
    e->cleanup_flags|=EC_CL_EXPIRED;ec_inc32(&e->cleanup_expired);
    ec_error_done(e,io,cycles,hz,true);return;
  }
  // NACK schedules hardware STOP. Give it a bounded grace period first.
  // A single software STOP is allowed only when START/STOP are clear,
  // the transfer is ours, and arbitration has not been lost.
  const bool grace=e->cause!=EC_NACK || elapsed>=(hz/1000000U)*EC_AUTO_STOP_GRACE_US;
  if(grace&&e->recovering!=3&&!(e->cleanup_flags&EC_CL_REQUESTED)&&
      !(isr&EC_STOPF)&&(isr&EC_BUSYF)&&io->stop_ready(io->ctx)){
    io->request_stop(io->ctx);e->cleanup_flags|=EC_CL_REQUESTED;ec_inc32(&e->stop_requests);
  }
}
static inline void ec_finish(ec_state *e,ec_io *io,uint32_t ms,uint32_t cycles,
                             uint32_t hz,uint8_t cause,uint32_t isr){
  if(!cause){
    io->clear(io->ctx);io->park(io->ctx);ec_inc32(&e->parks);ec_inc32(&e->reads);
    ec_idle(e);ec_elapsed(e,cycles,hz);e->sample_ms=ms;e->cause=EC_NONE;e->bus_ok=true;e->stage=0;
    e->raw=(uint16_t)(((e->bytes[1]&15U)<<8)|e->bytes[2]);e->status=e->bytes[0];
    e->angle_ok=(e->status&0x38U)==0x20U && (e->bytes[1]&0xf0U)==0;
    ec_track(e,ms);return;
  }
  if(e->recovering)return; // One failure/counter/capture per acquisition.
  if(io->fault)io->fault(io->ctx,cause,isr,ms,cycles);
  e->cause=cause;e->last_isr=isr;e->abort_cycles=cycles;e->sample_ms=ms;
  e->cleanup_flags=0;e->have_free_since=false;
  ec_inc32(&e->errors);
  if(cause==EC_NACK)ec_inc32(&e->primary_nack);
  else if(cause==EC_DEADLINE)ec_inc16(&e->timeouts);
  else if(cause==EC_BUSY)ec_inc32(&e->primary_busy);
  else if(cause==EC_ARLO)ec_inc32(&e->primary_arlo);
  else if(cause==EC_OVR)ec_inc32(&e->primary_ovr);
  else if(cause==EC_SHORT)ec_inc32(&e->primary_short);
  else if(cause==EC_SETUP)ec_inc32(&e->primary_setup);
  e->bus_ok=false;e->raw=0;e->status=0;e->angle_ok=false;ec_speed_reset(e);
  // A preflight error has not sent START. It must never generate STOP.
  if(!e->state){
    e->cleanup_flags=EC_CL_NO_TRANSFER;
    ec_error_done(e,io,cycles,hz,e->prepare==2);return;
  }
  e->recovering=cause==EC_ARLO?3:1;
  if(cause==EC_ARLO)e->cleanup_flags|=EC_CL_ARLO;
  if(isr&EC_NACKF)io->clear_nack(io->ctx); // W1C only NACKCF, preserve STOPF.
  ec_recover(e,io,ms,cycles,hz,isr);
}
