"""Install only the HMI server; preserve calibration and MCU firmware."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import py_compile
import signal
import subprocess
import time
import urllib.request


def precheck(s, max_vdc=20):
    """Programming gate only; latched ESTOP/protection need not be cleared.

    Physical mains-off and independent meter confirmation are required by the
    caller. This does not authorize START or overriding any motor protection.
    """
    try:
        if max_vdc != 20: return False, 'unsupported programming threshold'
        if (s['fw_build'],s['mc_fw_build']) not in ((2026102971, 2026102972), (2026103001, 2026103002)):
            return False,'unexpected firmware pair'
        if s['state']!='SAFE' or s['pwm']!=0 or s['hmi_hv_armed']!=0 or int(s['bp_status'])&0x22:
            return False,'outputs or run request active'
        if s['estop'] not in (0,1): return False,'invalid ESTOP metadata'
        if s['rpc_schema_version']!=3 or s['mc_capabilities']!=1 or s['bp_mcsdk_telemetry']!=1:
            return False,'unexpected measurement contract'
        for key in ('vdc','bp_vdc'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<=max_vdc:
                return False,'bus above programming limit: '+key
        for key in ('mc_age_ms','bp_vbus_age_ms','bp_temp_age_ms'):
            if type(s[key]) not in (int,float) or not math.isfinite(s[key]) or not 0<=s[key]<300:
                return False,'stale measurement: '+key
        if s['bp_vbus_valid']!=1 or s['bp_temp_valid']!=1 or s['bp_temp_fault']!=0:
            return False,'invalid measurement or active temperature fault'
        if type(s['bp_vbus_raw']) is not int or not 0<=s['bp_vbus_raw']<=max_vdc*10:
            return False,'raw bus word above programming limit'
        for key in ('mc_uart_error_flags','bp_uart_error_flags'):
            if s[key]!=0: return False,'active UART hardware error: '+key
        # Resetting the Uno while Nucleo stays powered latches its command
        # watchdog. Fresh OFF replies remain usable for programming. Preserve
        # this evidence instead of sending CLEAR just to satisfy an installer.
        reset_timeout=(s.get('mc_transport_fault')==7 and s.get('bp_transport_fault')==7
            and s.get('mc_fault')==2 and s.get('bp_fault')==2
            and s.get('mc_last_bad_reason')==13
            and s.get('mc_last_uart_error_flags')==0)
        # A saved CRC latch need not be CLEARed for reprogramming on the
        # physically deenergized bench. This does not authorize motor START.
        known_crc=(s.get('mc_transport_fault')==2 and s.get('bp_transport_fault')==2
            and s.get('mc_fault') in (1,3) and s.get('bp_fault') in (1,3)
            and s.get('mc_fault_reason')==1 and s.get('mc_last_bad_reason')==1
            and s.get('mc_fault_current_mask')==0 and s.get('mc_fault_occurred_mask')==0
            and s.get('mc_last_uart_error_flags')==0)
        for key in ('mc_transport_fault','bp_transport_fault'):
            if s[key]!=0 and not (reset_timeout or known_crc): return False,'unrecognized transport latch: '+key
        for key in ('precharge','pfc','brake','bp_ext'):
            if s[key]!=0:return False,'service output active: '+key
        return True,'disarmed, fresh low bus; latched protection retained'
    except (KeyError,ValueError,TypeError,OverflowError):
        return False,'invalid or missing programming telemetry'


def status():
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        'http://127.0.0.1:8080/api/status', timeout=8
    ) as response:
        payload = json.load(response)
    if payload.get('ok') is not True or not isinstance(payload.get('data'), dict):
        raise RuntimeError('HMI status unavailable')
    return payload['data']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--wait-sec', type=int, default=0)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--max-vdc', type=int, choices=(20,), default=20)
    parser.add_argument('--confirm-mains-off', action='store_true',
                        help='Required for HMI-only update with auxiliary supply on; never MCU programming')
    parser.add_argument('--app-js', type=Path)
    parser.add_argument('--app-js-sha256')
    args = parser.parse_args()
    if args.max_vdc == 20 and not args.confirm_mains_off:
        parser.error('auxiliary-only HMI update requires mains-off confirmation')
    if not 0 <= args.wait_sec <= 3600:
        parser.error('wait-sec outside 0..3600')
    root = Path('/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
    calibration = Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
    candidate = args.candidate.resolve(strict=True)
    data = candidate.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256.lower():
        raise RuntimeError('candidate hash mismatch')
    py_compile.compile(str(candidate), doraise=True)
    import base64
    index_data=base64.b64decode('PCFkb2N0eXBlIGh0bWw+CjxodG1sIGxhbmc9InJ1Ij4KPGhlYWQ+CiAgPG1ldGEgY2hhcnNldD0idXRmLTgiIC8+CiAgPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xIiAvPgogIDx0aXRsZT7QkNCY0KAgwrcg0YLQvtC60Lggwrcg0KPQv9GA0LDQstC70LXQvdC40LUg0LTQstC40LPQsNGC0LXQu9C10LwgVU5PUTwvdGl0bGU+CiAgPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSJzdHlsZS5jc3M/dWk9MzAwMS1mYXN0LWJ1ZGdldCIgLz4KPHN0eWxlPgouc2ltcGxlLXNoZWxse21heC13aWR0aDo2ODBweDtnYXA6MTRweDtwYWRkaW5nLXRvcDoyMHB4fS5zaW1wbGUtc2hlbGwgaDF7Zm9udC1zaXplOjI0cHg7bWFyZ2luOjB9Ci5zaW1wbGUtc2hlbGwgLmhlcm97Z2FwOjhweH0uc2ltcGxlLXNoZWxsIC5zdGF0dXMtcm93e2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVufQouc2ltcGxlLXRpdGxlYmFye2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47Z2FwOjEycHh9Ci5zaW1wbGUtdGl0bGViYXIgaDF7Zm9udC1zaXplOjIycHh9LnNpbXBsZS10aXRsZWJhciAuc3RhdHVzLXJvd3t3aWR0aDphdXRvfQouc2ltcGxlLWNvbnRyb2xze3BhZGRpbmc6MjJweDtkaXNwbGF5OmdyaWQ7Z2FwOjE4cHh9LnNpbXBsZS1tb2Rle21hcmdpbjowO2NvbG9yOiNhZWI5Yzk7Zm9udC1zaXplOjE0cHh9CiNzaW1wbGVTdGF0ZXtmb250LXNpemU6MjBweDtmb250LXdlaWdodDo3MDA7bGluZS1oZWlnaHQ6MS4zNX0jc2ltcGxlU3RhdGVbZGF0YS1zdGF0ZT1lcnJvcl17Y29sb3I6I2ZmODI5OH0KI3NpbXBsZVN0YXRlW2RhdGEtc3RhdGU9cnVubmluZ117Y29sb3I6IzQ5ZGNjOH0uc2ltcGxlLWNvbnRyb2xzIC5mcmVxLWJsb2Nre21hcmdpbjowO3Bvc2l0aW9uOnN0YXRpY30KLnNpbXBsZS1jb250cm9scyAuZnJlcS10b29sdGlwe3Bvc2l0aW9uOnN0YXRpYztvcGFjaXR5OjE7dHJhbnNmb3JtOm5vbmU7cG9pbnRlci1ldmVudHM6bm9uZTtiYWNrZ3JvdW5kOm5vbmU7Ym94LXNoYWRvdzpub25lO3RleHQtYWxpZ246bGVmdDtmb250LXNpemU6MzJweDtwYWRkaW5nOjhweCAwIDB9Ci5zaW1wbGUtY29udHJvbHMgLmZyZXEtcm93e3dpZHRoOjEwMCV9LnNpbXBsZS1jb250cm9scyBpbnB1dFt0eXBlPXJhbmdlXXt3aWR0aDoxMDAlO21pbi1oZWlnaHQ6NDBweH0KLnNpbXBsZS1jb250cm9scyAuYnV0dG9uLXJvd3tkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjEycHg7bWFyZ2luOjB9Ci5zaW1wbGUtY29udHJvbHMgLmJ1dHRvbi1yb3cgLmJ0bntmb250LXNpemU6MTlweDttaW4taGVpZ2h0OjU0cHh9LnNpbXBsZS1jb250cm9scyAuZXN0b3AtYmxvY2t7bWFyZ2luOjB9Ci5zaW1wbGUtY29udHJvbHMgLmJ0bi5lc3RvcCwuc2ltcGxlLWNvbnRyb2xzIC5idG4uZXN0b3AuYWN0aXZle2JhY2tncm91bmQ6I2M5MWQ0MDtjb2xvcjp3aGl0ZTttaW4taGVpZ2h0OjQ4cHh9Ci5zaW1wbGUtcmVhZGluZ3N7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoNCxtaW5tYXgoMCwxZnIpKTtnYXA6MTBweH0KLnNpbXBsZS1yZWFkaW5ne2JhY2tncm91bmQ6IzEwMTUxYztib3JkZXI6MXB4IHNvbGlkICMyNzMxM2Q7Ym9yZGVyLXJhZGl1czoxMnB4O3BhZGRpbmc6MTJweCA4cHh9Ci5zaW1wbGUtcmVhZGluZyBzcGFue2Rpc3BsYXk6YmxvY2s7Zm9udC1zaXplOjEycHg7Y29sb3I6I2FlYjljOTttYXJnaW4tYm90dG9tOjdweH0uc2ltcGxlLXJlYWRpbmcgc3Ryb25ne2ZvbnQtc2l6ZToyMHB4fQouc2ltcGxlLW5vdGV7bWFyZ2luOjA7Y29sb3I6I2FlYjljOTtmb250LXNpemU6MTNweDtsaW5lLWhlaWdodDoxLjQ1fS5zaW1wbGUtZGV0YWlsc3twYWRkaW5nOjE2cHggMjBweH0KLnNpbXBsZS1kZXRhaWxzPnN1bW1hcnl7Y3Vyc29yOnBvaW50ZXI7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOiNiYWM1ZDR9LnNpbXBsZS1kZXRhaWxzW29wZW5dPnN1bW1hcnl7bWFyZ2luLWJvdHRvbToxNnB4fQouc2ltcGxlLWRldGFpbHMgLmdyaWR7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn0uc2ltcGxlLWRldGFpbHMgLnBhbmVse2JveC1zaGFkb3c6bm9uZX0KLnNpbXBsZS1zaGVsbCAuYmd7ZGlzcGxheTpub25lfVtoaWRkZW5de2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9CkBtZWRpYShtYXgtd2lkdGg6NDIwcHgpey5zaW1wbGUtc2hlbGx7cGFkZGluZzoxNHB4IDEycHggMzJweH0uc2ltcGxlLWNvbnRyb2xze3BhZGRpbmc6MTdweH0uc2ltcGxlLXJlYWRpbmdze2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMixtaW5tYXgoMCwxZnIpKX19Cjwvc3R5bGU+CjxsaW5rIHJlbD0iaWNvbiIgaHJlZj0iZGF0YTosIiAvPgo8L2hlYWQ+Cjxib2R5PgogIDxkaXYgY2xhc3M9ImJnIj48L2Rpdj4KICA8bWFpbiBjbGFzcz0ic2hlbGwgc2ltcGxlLXNoZWxsIj4KPGRpdiBjbGFzcz0ic2ltcGxlLXRpdGxlYmFyIj48aDE+0KPQv9GA0LDQstC70LXQvdC40LUg0JDQmNCgPC9oMT4KPGhlYWRlciBjbGFzcz0iaGVybyI+CiAgICAgIDxkaXYgY2xhc3M9InN0YXR1cy1yb3ciPgogICAgICAgIDxkaXYgY2xhc3M9InN0YXR1cy1jaGlwIiBpZD0iY29ubkNoaXAiPgogICAgICAgICAgPHNwYW4gY2xhc3M9ImRvdCIgaWQ9ImNvbm5Eb3QiPjwvc3Bhbj4KICAgICAgICAgIDxzcGFuIGlkPSJjb25uVGV4dCI+0L7RhNC70LDQudC9PC9zcGFuPgogICAgICAgIDwvZGl2PgogICAgICAgIAogICAgICA8L2Rpdj4KICAgIDwvaGVhZGVyPjwvZGl2Pgo8c2VjdGlvbiBjbGFzcz0icGFuZWwgc2ltcGxlLWNvbnRyb2xzIj4KICA8bGFiZWwgZm9yPSJhbGdvcml0aG1TZWxlY3QiPtCQ0LvQs9C+0YDQuNGC0Lw8L2xhYmVsPgogIDxzZWxlY3QgaWQ9ImFsZ29yaXRobVNlbGVjdCIgc3R5bGU9ImNvbG9yOiNmMmY1ZmE7YmFja2dyb3VuZDojMTAxNTFjO2JvcmRlcjoxcHggc29saWQgIzM1NDE1MTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxMnB4O2ZvbnQtc2l6ZToxNnB4O3dpZHRoOjEwMCU7bWluLWhlaWdodDo0NnB4IiBkaXNhYmxlZCBhcmlhLWRlc2NyaWJlZGJ5PSJhbGdvcml0aG1Ob3RlIj4KICAgIDxvcHRpb24gdmFsdWU9IjEiPtCh0LrQsNC70Y/RgNC90YvQuSBWL2Y8L29wdGlvbj48b3B0aW9uIHZhbHVlPSIyIj7QktC10LrRgtC+0YDQvdGL0LkgRk9DPC9vcHRpb24+CiAgICA8b3B0aW9uIHZhbHVlPSIzIj5GT0MgKyDQsNC00LDQv9GC0LjQstC90YvQuSDQqNCY0Jw8L29wdGlvbj48b3B0aW9uIHZhbHVlPSI0Ij7QmNC30LzQtdGA0LXQvdC40LUg0L/QsNGA0LDQvNC10YLRgNC+0LI8L29wdGlvbj4KICA8L3NlbGVjdD4KICA8cCBjbGFzcz0ic2ltcGxlLW1vZGUiIGlkPSJzaW1wbGVNb2RlIj7QntC20LjQtNCw0L3QuNC1INGA0LXQttC40LzQsDwvcD4KICA8cCBjbGFzcz0ic2ltcGxlLW5vdGUiIGlkPSJhbGdvcml0aG1Ob3RlIiByb2xlPSJzdGF0dXMiPtCX0LDQs9GA0YPQt9C60LDigKY8L3A+CiAgPGRpdiBpZD0ic2ltcGxlU3RhdGUiIHJvbGU9InN0YXR1cyIgYXJpYS1saXZlPSJwb2xpdGUiPtCf0L7QtNC60LvRjtGH0LXQvdC40LXigKY8L2Rpdj4KPGRpdiBjbGFzcz0iZnJlcS1ibG9jayI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJsYWJlbCI+0KfQsNGB0YLQvtGC0LAgKNCT0YYpPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJmcmVxLXJvdyI+CiAgICAgICAgICAgIDxpbnB1dCBhcmlhLWxhYmVsPSLQl9Cw0LTQsNC90LjQtSDRh9Cw0YHRgtC+0YLRiyDQv9C+0LvRjywg0JPRhiIgaWQ9ImZyZXFTbGlkZXIiIHR5cGU9InJhbmdlIiBtaW49IjAiIG1heD0iNTAiIHN0ZXA9IjAuMSIgdmFsdWU9IjEwIiAvPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJmcmVxLXRvb2x0aXAiIGlkPSJmcmVxUmVhZG91dCI+MTAuMCDQk9GGPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgPHAgY2xhc3M9InNpbXBsZS1ub3RlIiBpZD0ic2ltcGxlRmllbGQiPtCn0LDRgdGC0L7RgtCwINC/0L7Qu9GPOiDigJQ8L3A+CjxkaXYgY2xhc3M9ImJ1dHRvbi1yb3ciPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIHN0YXJ0IiBpZD0ic3RhcnRCdG4iPtCf0YPRgdC6PC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gc3RvcCIgaWQ9InN0b3BCdG4iPtCh0YLQvtC/PC9idXR0b24+CiAgICAgICAgPC9kaXY+PGRpdiBjbGFzcz0iZXN0b3AtYmxvY2siPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGVzdG9wIGZ1bGwiIGlkPSJlc3RvcEJ0biI+0JDQstCw0YDQuNC50L3Ri9C5INGB0YLQvtC/PC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IGZ1bGwiIGlkPSJzaW1wbGVDbGVhciIgaGlkZGVuPtCh0LHRgNC+0YHQuNGC0Ywg0LDQstCw0YDQuNGOPC9idXR0b24+CiAgPGRpdiBjbGFzcz0ic2ltcGxlLXJlYWRpbmdzIj4KICAgIDxkaXYgY2xhc3M9InNpbXBsZS1yZWFkaW5nIj48c3Bhbj7QqNC40L3QsCBEQzwvc3Bhbj48c3Ryb25nIGlkPSJzaW1wbGVWZGMiPuKAlDwvc3Ryb25nPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2ltcGxlLXJlYWRpbmciPjxzcGFuPtCi0L7QuiBVPC9zcGFuPjxzdHJvbmcgaWQ9InNpbXBsZUkwIj7igJQ8L3N0cm9uZz48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpbXBsZS1yZWFkaW5nIj48c3Bhbj7QotC+0LogVjwvc3Bhbj48c3Ryb25nIGlkPSJzaW1wbGVJMSI+4oCUPC9zdHJvbmc+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaW1wbGUtcmVhZGluZyI+PHNwYW4+0KLQvtC6IFc8L3NwYW4+PHN0cm9uZyBpZD0ic2ltcGxlSTIiPuKAlDwvc3Ryb25nPjwvZGl2PgogIDwvZGl2PgogIDxwIGNsYXNzPSJzaW1wbGUtbm90ZSIgaWQ9InNpbXBsZUN1cnJlbnROb3RlIj7QotC+0LrQuCBSTVMg0L/QviDRiNGD0L3RgtCw0Lw8L3A+Cjwvc2VjdGlvbj4KPGRldGFpbHMgY2xhc3M9InBhbmVsIHNpbXBsZS1kZXRhaWxzIiBpZD0ibWFudWFsU2V0dGluZ3MiPjxzdW1tYXJ5PtCg0LDQt9Cz0L7QvSDQuCDQt9Cw0LzQtdC00LvQtdC90LjQtTwvc3VtbWFyeT4KPGRpdiBjbGFzcz0ibWFudWFsLWNvbmZpZyIgaWQ9Im1hbnVhbENvbmZpZyIgaGlkZGVuPgogICAgICAgICAgPGxhYmVsPjxpbnB1dCBpZD0ibWFudWFsQ29udGludW91cyIgdHlwZT0iY2hlY2tib3giIGNoZWNrZWQgLz4g0KDQsNCx0L7RgtCwINC00L4g0LrQvtC80LDQvdC00YsgwqvQodGC0L7Qv8K7PC9sYWJlbD4KICAgICAgICAgIDxwPtCn0LDRgdGC0L7RgtCwINC/0L7Qu9GPOiAw4oCTNTAg0JPRhi4gwqvQodGC0L7Qv8K7INC4IDAg0JPRhiDigJQg0YHQstC+0LHQvtC00L3Ri9C5INCy0YvQsdC10LMuPC9wPgogICAgICAgICAgPGxhYmVsPtCg0LDQt9Cz0L7QvSwg0JPRhi/RgSA8aW5wdXQgaWQ9Im1hbnVhbEFjY2VsIiB0eXBlPSJudW1iZXIiIG1pbj0iMC4xIiBtYXg9IjUwIiBzdGVwPSIwLjEiIHZhbHVlPSI1IiAvPjwvbGFiZWw+CiAgICAgICAgICA8bGFiZWw+0JfQsNC80LXQtNC70LXQvdC40LUsINCT0YYv0YEgPGlucHV0IGlkPSJtYW51YWxEZWNlbCIgdHlwZT0ibnVtYmVyIiBtaW49IjAuMSIgbWF4PSI1IiBzdGVwPSIwLjEiIHZhbHVlPSIxIiAvPjwvbGFiZWw+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QgZnVsbCIgaWQ9Im1hbnVhbEFwcGx5Ij7Qn9GA0LjQvNC10L3QuNGC0Ywg0YDQsNC30LPQvtC9INC4INC30LDQvNC10LTQu9C10L3QuNC1PC9idXR0b24+CiAgICAgICAgICA8bGFiZWw+0KHQvdC40LbQtdC90LjQtSDQt9Cw0LTQsNC90LjRjyA8c2VsZWN0IGlkPSJtYW51YWxEb3dubW9kZSI+PG9wdGlvbiB2YWx1ZT0iUkFNUCI+0J/Qu9Cw0LLQvdC+LCDRgSDQutC+0L3RgtGA0L7Qu9C10LwgREMt0YjQuNC90Ys8L29wdGlvbj48b3B0aW9uIHZhbHVlPSJDT0FTVCI+0JLRi9Cx0LXQsywg0LfQsNGC0LXQvCDQvtGC0LTQtdC70YzQvdGL0Lkg0L/Rg9GB0Lo8L29wdGlvbj48L3NlbGVjdD48L2xhYmVsPgogICAgICAgICAgPGRpdiBjbGFzcz0iaHYtYXJtLW5vdGUiIGlkPSJtYW51YWxTdGF0ZSI+0J3QsNGB0YLRgNC+0LnQutC4INC00L7RgdGC0YPQv9C90Ysg0L/QvtGB0LvQtSDQv9C+0LTQutC70Y7Rh9C10L3QuNGPLjwvZGl2PgogICAgICAgICAgPGxhYmVsPtCX0LDQtNCw0L3QuNC1LCDQk9GGIDxpbnB1dCBpZD0ibWFudWFsRnJlcXVlbmN5IiB0eXBlPSJudW1iZXIiIG1pbj0iMCIgbWF4PSI1MCIgc3RlcD0iMC4xIiB2YWx1ZT0iNSIgLz48L2xhYmVsPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IGZ1bGwiIGlkPSJtYW51YWxGcmVxdWVuY3lBcHBseSI+0JfQsNC00LDRgtGMINGH0LDRgdGC0L7RgtGDPC9idXR0b24+CiAgICAgICAgPC9kaXY+CjwvZGV0YWlscz4KPGRldGFpbHMgY2xhc3M9InBhbmVsIHNpbXBsZS1kZXRhaWxzIiBpZD0iZGlhZ25vc3RpY0RldGFpbHMiPjxzdW1tYXJ5PtCU0LjQsNCz0L3QvtGB0YLQuNC60LAg0Lgg0LDQu9Cz0L7RgNC40YLQvNGLPC9zdW1tYXJ5Pgo8ZGl2IGNsYXNzPSJzdGF0dXMtY2hpcCBzdGF0dXMtbW9kZSIgaWQ9InN5c0NoaXAiPgogICAgICAgICAgPHNwYW4gaWQ9InN5c1RleHQiPtCh0KLQntCfPC9zcGFuPgogICAgICAgIDwvZGl2PgogICAgCgogICAgPHNlY3Rpb24gY2xhc3M9ImdyaWQiPgogICAgICA8ZGl2IGNsYXNzPSJwYW5lbCBjb250cm9scyI+CiAgICAgICAgPGRpdiBjbGFzcz0iYWNjZXNzLWJsb2NrIiBpZD0iY29udHJvbEFjY2Vzc0Jsb2NrIiBoaWRkZW4+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJsYWJlbCI+0JTQvtGB0YLRg9C/INC6INGB0YLQtdC90LTRgzwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iYWNjZXNzLXJvdyI+CiAgICAgICAgICAgIDxpbnB1dCBpZD0iY29udHJvbFRva2VuIiBjbGFzcz0iYWNjZXNzLWlucHV0IiB0eXBlPSJwYXNzd29yZCIgYXV0b2NvbXBsZXRlPSJjdXJyZW50LXBhc3N3b3JkIiBwbGFjZWhvbGRlcj0i0JrQu9GO0Ycg0YPQv9GA0LDQstC70LXQvdC40Y8iIC8+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgaWQ9ImNvbnRyb2xUb2tlblNhdmUiIHR5cGU9ImJ1dHRvbiI+0J/RgNC40LzQtdC90LjRgtGMPC9idXR0b24+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImFjY2Vzcy1zdGF0dXMiIGlkPSJjb250cm9sQWNjZXNzU3RhdHVzIj7QotGA0LXQsdGD0LXRgtGB0Y8g0LrQu9GO0Ycg0YPQv9GA0LDQstC70LXQvdC40Y88L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJtb2RlLXJvdyI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJsYWJlbCI+0KDQtdC20LjQvDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0ic2VnbWVudGVkIiBpZD0ibW9kZVRvZ2dsZSI+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9InNlZyIgZGF0YS1tb2RlPSJWRiI+VkY8L2J1dHRvbj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0ic2VnIiBkYXRhLW1vZGU9IkZPQyI+Rk9DPC9idXR0b24+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9InNlZyIgZGF0YS1tb2RlPSJNSUMiPk1JQzwvYnV0dG9uPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgCiAgICAgICAgCgogICAgICAgIAogICAgICAgIDxkaXYgY2xhc3M9Imh2LWFybS1ibG9jayIgaWQ9Imh2QXJtQmxvY2siIGhpZGRlbj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImFybS1wcm9maWxlLXRvZ2dsZSIgaWQ9ImFybVByb2ZpbGVUb2dnbGUiIGFyaWEtbGFiZWw9ItCf0YDQvtGE0LjQu9GMINC30LDQv9GD0YHQutCwIj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYXJtLXByb2ZpbGUtYnRuIiB0eXBlPSJidXR0b24iIGRhdGEtYXJtLXByb2ZpbGU9Imh2Ij5IViAzMTAg0JI8L2J1dHRvbj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYXJtLXByb2ZpbGUtYnRuIiB0eXBlPSJidXR0b24iIGRhdGEtYXJtLXByb2ZpbGU9Imx2Ij5MViBURVNUPC9idXR0b24+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9Imh2LWFybS1oZWFkIj4KICAgICAgICAgICAgPGRpdj4KICAgICAgICAgICAgICA8ZGl2IGNsYXNzPSJsYWJlbCIgaWQ9ImFybVByb2ZpbGVMYWJlbCI+0KHQuNC70L7QstCw0Y8g0YjQuNC90LA8L2Rpdj4KICAgICAgICAgICAgICA8c3Ryb25nIGlkPSJodkFybVN0YXR1cyI+SFYg0LfQsNCx0LvQvtC60LjRgNC+0LLQsNC90LA8L3N0cm9uZz4KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDxzcGFuIGNsYXNzPSJodi1hcm0tdGltZXIiIGlkPSJodkFybVRpbWVyIj4wLjAg0YE8L3NwYW4+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxpbnB1dAogICAgICAgICAgICBpZD0iaHZBcm1Db25maXJtIgogICAgICAgICAgICBjbGFzcz0iaHYtYXJtLWlucHV0IgogICAgICAgICAgICB0eXBlPSJ0ZXh0IgogICAgICAgICAgICBpbnB1dG1vZGU9InRleHQiCiAgICAgICAgICAgIGF1dG9jb21wbGV0ZT0ib2ZmIgogICAgICAgICAgICBhdXRvY2FwaXRhbGl6ZT0iY2hhcmFjdGVycyIKICAgICAgICAgICAgcGxhY2Vob2xkZXI9ItCS0LLQtdC00LjRgtC1IEFSTSAzMTBWIgogICAgICAgICAgLz4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBodi1hcm0gZnVsbCIgaWQ9Imh2QXJtQnRuIj7QoNCw0LfRgNC10YjQuNGC0YwgSFYg0L3QsCAzMCDRgdC10LrRg9C90LQ8L2J1dHRvbj4KICAgICAgICAgIDxwIGNsYXNzPSJodi1hcm0tbm90ZSIgaWQ9ImFybVByb2ZpbGVOb3RlIj7QoNCw0LfRgNC10YjQtdC90LjQtSDQvtCz0YDQsNC90LjRh9C10L3QviDQv9C+INCy0YDQtdC80LXQvdC4LiBTVE9QLCBFU1RPUCwg0L/QtdGA0LXQt9Cw0L/Rg9GB0LosINC/0L7RgtC10YDRjyDQutC+0L3RgtGA0L7Qu9GPINC40LvQuCDRgtCw0LnQvC3QsNGD0YIg0YHQvdC40LzQsNGO0YIg0LXQs9C+LjwvcD4KICAgICAgICAgIDxkZXRhaWxzIGNsYXNzPSJ2YnVzLWNhcHR1cmUtYmxvY2siPjxzdW1tYXJ5PtCa0LDQu9C40LHRgNC+0LLQutCwIERDLdGI0LjQvdGLPC9zdW1tYXJ5PgogICAgICAgICAgICA8aW5wdXQKICAgICAgICAgICAgICBpZD0idmJ1c01ldGVySW5wdXQiCiAgICAgICAgICAgICAgY2xhc3M9Imh2LWFybS1pbnB1dCIKICAgICAgICAgICAgICB0eXBlPSJudW1iZXIiCiAgICAgICAgICAgICAgaW5wdXRtb2RlPSJkZWNpbWFsIgogICAgICAgICAgICAgIG1pbj0iMCIKICAgICAgICAgICAgICBtYXg9IjQ1MCIKICAgICAgICAgICAgICBzdGVwPSIwLjEiCiAgICAgICAgICAgICAgcGxhY2Vob2xkZXI9ItCd0LDQv9GA0Y/QttC10L3QuNC1INC80YPQu9GM0YLQuNC80LXRgtGA0LAsINCSIgogICAgICAgICAgICAvPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QgZnVsbCIgaWQ9InZidXNDYXB0dXJlQnRuIj7Ql9Cw0L/QuNGB0LDRgtGMINC/0L7QutCw0LfQsNC90LjQtSBWYnVzPC9idXR0b24+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9Imh2LWFybS1ub3RlIiBpZD0idmJ1c0NhbGlicmF0aW9uU3RhdGUiPtCa0LDQu9C40LHRgNC+0LLQutCwIFZidXMg0L3QtSDQv9C+0LTRgtCy0LXRgNC20LTQtdC90LAuPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9Imh2LWFybS1ub3RlIiBpZD0idmJ1c0NhcHR1cmVSZXN1bHQiPtCi0L7Qu9GM0LrQviDQuNC30LzQtdGA0LXQvdC40LU6INGA0LXQu9C1INC4INCo0JjQnCDQvdC1INCy0LrQu9GO0YfQsNGO0YLRgdGPLjwvZGl2PgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QgZnVsbCIgaWQ9InZidXNSZXNldEJ0biI+0KHQsdGA0L7RgdC40YLRjCDQutCw0LvQuNCx0YDQvtCy0LrRgyBWYnVzPC9idXR0b24+CiAgICAgICAgICA8L2RldGFpbHM+CiAgICAgICAgPC9kaXY+CgogICAgICAgIDxkaXYgY2xhc3M9ImlvLWJsb2NrIj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImxhYmVsIj5JUE0xNSBJL088L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImlvLXJvdyI+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgaWQ9InBmY0J0biI+UEZDOiBPRkY8L2J1dHRvbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iYnJha2Utcm93Ij4KICAgICAgICAgICAgPGlucHV0IGlkPSJicmFrZVNsaWRlciIgdHlwZT0icmFuZ2UiIG1pbj0iMCIgbWF4PSIxIiBzdGVwPSIwLjA1IiB2YWx1ZT0iMCIgLz4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iYnJha2UtcmVhZG91dCIgaWQ9ImJyYWtlUmVhZG91dCI+QlJLIDAlPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImZhbi1yb3ciPgogICAgICAgICAgICA8aW5wdXQgaWQ9ImZhblNsaWRlciIgdHlwZT0icmFuZ2UiIG1pbj0iMCIgbWF4PSIxIiBzdGVwPSIwLjA1IiB2YWx1ZT0iMCIgLz4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iZmFuLXJlYWRvdXQiIGlkPSJmYW5SZWFkb3V0Ij5GQU4gMCU8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgIDwvZGl2PgoKICAgICAgICAKICAgICAgPC9kaXY+CgogICAgICA8ZGl2IGNsYXNzPSJwYW5lbCBzdGF0dXMiPgogICAgICAgIDxoMj7QodGC0LDRgtGD0YE8L2gyPgogICAgICAgIDxkaXYgY2xhc3M9InN0YXR1cy1ncmlkIj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QodC+0YHRgtC+0Y/QvdC40LU8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InN0YXRlVmFsIj5TQUZFPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QoNC10LbQuNC8PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJtb2RlVmFsIj5GT0M8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCa0L7QvdGC0YPRgCBOdWNsZW88L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImJhY2tlbmRWYWwiPkRVVFk8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCh0LLRj9C30YwgU1RNMzI8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImxpbmtWYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QqNCY0Jw8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InB3bVZhbCI+MDwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KHQutC+0YDQvtGB0YLRjDwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0ic3BlZWRWYWwiPjAg0L7QsS/QvNC40L08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCo0LjQvdCwIERDPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJ2ZGNWYWwiPjAuMCBWPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QoNCw0LTQuNCw0YLQvtGAIElQTTwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0idGVtcFZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPklhL0liL0ljPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJjdXJyVmFsIj4wIC8gMCAvIDAgQTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+UGhhc2UgbWVhcyBBL0IvQzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0icGhhc2VWYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj5JZCDQt9Cw0LTQsNC90L48L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImlkUmVmVmFsIj4wLjAwIEE8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPk1JQyDRjdC60L7QvdC+0LzQuNGPPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJtaWNTYXZlVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+UEZDL0JSSzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iaW9WYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QktC10L3RgtC40LvRj9GC0L7RgDwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iZmFuVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0J7QsdGA0LDRgtC90LDRjyDRgdCy0Y/Qt9GMPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJlbmNWYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJzdGF0dXMtZm9vdGVyIj4KICAgICAgICAgIDxzcGFuIGlkPSJsYXN0VXBkYXRlIj7QndC10YIg0LTQsNC90L3Ri9GFPC9zcGFuPgogICAgICAgICAgPGJ1dHRvbiBpZD0iYmtpblRyYWNlTG9hZCIgY2xhc3M9ImJ0biBnaG9zdCIgdHlwZT0iYnV0dG9uIj7QodGH0LjRgtCw0YLRjCDRgdC90LjQvNC+0LogQktJTjwvYnV0dG9uPgogICAgICAgICAgPHNwYW4gaWQ9ImJraW5UcmFjZVN0YXR1cyI+0KHQvdC40LzQvtC6INC/0L7Rj9Cy0LjRgtGB0Y8g0L/QvtGB0LvQtSDRgdGA0LDQsdCw0YLRi9Cy0LDQvdC40Y8g0LfQsNGJ0LjRgtGLLjwvc3Bhbj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CgogICAgPHNlY3Rpb24gY2xhc3M9InBhbmVsIiBpZD0icmVzZWFyY2hQYW5lbCI+PGgyPtCY0YHRgdC70LXQtNC+0LLQsNGC0LXQu9GM0YHQutCw0Y8g0YHQtdGA0LjRjzwvaDI+PGRpdiBpZD0icmVzZWFyY2hBbGdvcml0aG1zIj7QntC20LjQtNCw0L3QuNC1INC/0L7QtNGC0LLQtdGA0LbQtNC10L3QuNGPIE51Y2xlbzwvZGl2Pjwvc2VjdGlvbj4KICAgIDxzZWN0aW9uIGNsYXNzPSJwYW5lbCBsb2dzIj4KICAgICAgPGRpdiBjbGFzcz0ibG9nLXJvdyI+CiAgICAgICAgPHNwYW4gY2xhc3M9ImxvZy10aXRsZSI+0JvQvtCz0Lg8L3NwYW4+CiAgICAgICAgPHNlbGVjdCBpZD0ibG9nSG91cnMiPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iMSI+MSDRh9Cw0YE8L29wdGlvbj4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9IjYiPjYg0YfQsNGB0L7Qsjwvb3B0aW9uPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iMjQiIHNlbGVjdGVkPjI0INGH0LDRgdCwPC9vcHRpb24+CiAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAgPGJ1dHRvbiBpZD0ibG9nRG93bmxvYWQiIGNsYXNzPSJidG4gZ2hvc3QiIHR5cGU9ImJ1dHRvbiI+0KHQutCw0YfQsNGC0Yw8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L3NlY3Rpb24+CiAgCjwvZGV0YWlscz4KPC9tYWluPgoKICA8c2NyaXB0IHNyYz0iYXBwLmpzP3VpPTMwMDEtZmFzdC1idWRnZXQiPjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K')
    app_data = None
    if args.app_js:
        app_data = args.app_js.resolve(strict=True).read_bytes()
        if not args.app_js_sha256 or hashlib.sha256(app_data).hexdigest() != args.app_js_sha256.lower():
            raise RuntimeError('app.js hash mismatch')
    spec = importlib.util.spec_from_file_location('candidate_hmi', candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_calibration = calibration.read_bytes()
    store = module.VbusCalibrationStore(str(calibration))
    deadline = time.monotonic() + args.wait_sec
    while True:
        current = status()
        safe, reason = precheck(current, args.max_vdc)
        print(json.dumps({'precheck': safe, 'reason': reason,
                          'vdc': current.get('vdc')}), flush=True)
        if safe or time.monotonic() >= deadline:
            break
        time.sleep(10)
    if not safe:
        return 2
    if not store.is_valid(current):
        raise RuntimeError('saved calibration does not match candidate')
    if args.check_only:
        print(json.dumps({'check_only': True, 'calibration_valid': True}))
        return 0
    pid = int(subprocess.check_output(
        ['systemctl', 'show', '-p', 'MainPID', '--value', 'unoq-hmi.service'], text=True
    ).strip())
    restart = subprocess.check_output(
        ['systemctl', 'show', '-p', 'Restart', '--value', 'unoq-hmi.service'], text=True
    ).strip()
    proc = Path('/proc') / str(pid)
    if (pid <= 1 or restart != 'always' or proc.stat().st_uid != os.geteuid()
            or (proc / 'cwd').resolve() != root
            or 'server.py' not in (proc / 'cmdline').read_bytes().decode().split('\0')):
        raise RuntimeError('owned, automatically restarted HMI process not identified')
    target = root / 'server.py'
    previous = target.read_bytes()
    backup = root / 'backups' / ('vbus_reuse_' + time.strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    (backup / 'server.py').write_bytes(previous)
    (backup/'index.html').write_bytes((root/'static/index.html').read_bytes())
    if app_data is not None:
        (backup / 'app.js').write_bytes((root / 'static/app.js').read_bytes())
    # Copy atomically only after the last live safety check. Never change tokens,
    # calibration, startup arguments, or either MCU image.
    safe, reason = precheck(status(), args.max_vdc)
    if not safe:
        raise RuntimeError(reason)
    pending = root / 'server.py.vbus-pending'
    pending.write_bytes(data)
    pending.chmod(target.stat().st_mode & 0o777)
    os.replace(pending, target)
    if app_data is not None:
        pending_js = root / 'static/app.js.diag-pending'
        pending_js.write_bytes(app_data)
        pending_js.chmod(0o644)
        os.replace(pending_js, root / 'static/app.js')
    index_pending=root/'static/index.research-pending'
    index_pending.write_bytes(index_data);index_pending.chmod(0o644)
    os.replace(index_pending,root/'static/index.html')
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 35
    final = None
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            s = status()
            if (precheck(s, args.max_vdc)[0] and s.get('hmi_vbus_hv_calibrated') == 1
                    and int(subprocess.check_output(
                        ['systemctl', 'show', '-p', 'MainPID', '--value', 'unoq-hmi.service'],
                        text=True).strip()) != pid):
                final = s
                break
        except Exception:
            continue
    if final is None:
        raise RuntimeError('HMI installed but final verification failed; backup: ' + str(backup))
    if calibration.read_bytes() != original_calibration:
        raise RuntimeError('calibration record unexpectedly changed')
    if (root/'static/index.html').read_bytes()!=index_data:raise RuntimeError('index mismatch')
    if target.read_bytes() != data or (app_data is not None and (root/'static/app.js').read_bytes() != app_data):
        raise RuntimeError('installed HMI files do not match candidate')
    print(json.dumps({'installed': True, 'sha256': args.sha256.lower(),
                      'calibration_unchanged': True, 'calibration_valid': True,
                      'state': final['state'], 'pwm': final['pwm'], 'backup': str(backup),
                      'mc_fw_build': final['mc_fw_build'], 'fw_build': final['fw_build'],
                      'actuation_commands': 0}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
