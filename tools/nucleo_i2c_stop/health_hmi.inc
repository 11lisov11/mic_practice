                **{"enc_health_"+name: int(kv.get("enc_health_"+name,"0")) for name in
                   ("nack","deadline","busy","arlo","ovr","short","setup","berr_clears","clean_stops","forced_resets","stop_requests","cleanup_expired","normal_parks","cleanup_flags")},
