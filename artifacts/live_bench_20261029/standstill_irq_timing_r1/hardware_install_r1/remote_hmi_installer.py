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
        if (s['fw_build'],s['mc_fw_build']) not in ((2026102935, 2026102936), (2026102937, 2026102938)):
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
    index_data=base64.b64decode('PCFkb2N0eXBlIGh0bWw+CjxodG1sIGxhbmc9InJ1Ij4KPGhlYWQ+CiAgPG1ldGEgY2hhcnNldD0idXRmLTgiIC8+CiAgPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xIiAvPgogIDx0aXRsZT7QkNCY0KAgwrcg0YLQvtC60Lggwrcg0KPQv9GA0LDQstC70LXQvdC40LUg0LTQstC40LPQsNGC0LXQu9C10LwgVU5PUTwvdGl0bGU+CiAgPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSJzdHlsZS5jc3M/dWk9MjkzNy1pcnEtdGltaW5nIiAvPgo8c3R5bGU+Ci5zaW1wbGUtc2hlbGx7bWF4LXdpZHRoOjY4MHB4O2dhcDoxNHB4O3BhZGRpbmctdG9wOjIwcHh9LnNpbXBsZS1zaGVsbCBoMXtmb250LXNpemU6MjRweDttYXJnaW46MH0KLnNpbXBsZS1zaGVsbCAuaGVyb3tnYXA6OHB4fS5zaW1wbGUtc2hlbGwgLnN0YXR1cy1yb3d7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW59Ci5zaW1wbGUtdGl0bGViYXJ7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtnYXA6MTJweH0KLnNpbXBsZS10aXRsZWJhciBoMXtmb250LXNpemU6MjJweH0uc2ltcGxlLXRpdGxlYmFyIC5zdGF0dXMtcm93e3dpZHRoOmF1dG99Ci5zaW1wbGUtY29udHJvbHN7cGFkZGluZzoyMnB4O2Rpc3BsYXk6Z3JpZDtnYXA6MThweH0uc2ltcGxlLW1vZGV7bWFyZ2luOjA7Y29sb3I6I2FlYjljOTtmb250LXNpemU6MTRweH0KI3NpbXBsZVN0YXRle2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2VpZ2h0OjcwMDtsaW5lLWhlaWdodDoxLjM1fSNzaW1wbGVTdGF0ZVtkYXRhLXN0YXRlPWVycm9yXXtjb2xvcjojZmY4Mjk4fQojc2ltcGxlU3RhdGVbZGF0YS1zdGF0ZT1ydW5uaW5nXXtjb2xvcjojNDlkY2M4fS5zaW1wbGUtY29udHJvbHMgLmZyZXEtYmxvY2t7bWFyZ2luOjA7cG9zaXRpb246c3RhdGljfQouc2ltcGxlLWNvbnRyb2xzIC5mcmVxLXRvb2x0aXB7cG9zaXRpb246c3RhdGljO29wYWNpdHk6MTt0cmFuc2Zvcm06bm9uZTtwb2ludGVyLWV2ZW50czpub25lO2JhY2tncm91bmQ6bm9uZTtib3gtc2hhZG93Om5vbmU7dGV4dC1hbGlnbjpsZWZ0O2ZvbnQtc2l6ZTozMnB4O3BhZGRpbmc6OHB4IDAgMH0KLnNpbXBsZS1jb250cm9scyAuZnJlcS1yb3d7d2lkdGg6MTAwJX0uc2ltcGxlLWNvbnRyb2xzIGlucHV0W3R5cGU9cmFuZ2Vde3dpZHRoOjEwMCU7bWluLWhlaWdodDo0MHB4fQouc2ltcGxlLWNvbnRyb2xzIC5idXR0b24tcm93e2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6MTJweDttYXJnaW46MH0KLnNpbXBsZS1jb250cm9scyAuYnV0dG9uLXJvdyAuYnRue2ZvbnQtc2l6ZToxOXB4O21pbi1oZWlnaHQ6NTRweH0uc2ltcGxlLWNvbnRyb2xzIC5lc3RvcC1ibG9ja3ttYXJnaW46MH0KLnNpbXBsZS1jb250cm9scyAuYnRuLmVzdG9wLC5zaW1wbGUtY29udHJvbHMgLmJ0bi5lc3RvcC5hY3RpdmV7YmFja2dyb3VuZDojYzkxZDQwO2NvbG9yOndoaXRlO21pbi1oZWlnaHQ6NDhweH0KLnNpbXBsZS1yZWFkaW5nc3tkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCg0LG1pbm1heCgwLDFmcikpO2dhcDoxMHB4fQouc2ltcGxlLXJlYWRpbmd7YmFja2dyb3VuZDojMTAxNTFjO2JvcmRlcjoxcHggc29saWQgIzI3MzEzZDtib3JkZXItcmFkaXVzOjEycHg7cGFkZGluZzoxMnB4IDhweH0KLnNpbXBsZS1yZWFkaW5nIHNwYW57ZGlzcGxheTpibG9jaztmb250LXNpemU6MTJweDtjb2xvcjojYWViOWM5O21hcmdpbi1ib3R0b206N3B4fS5zaW1wbGUtcmVhZGluZyBzdHJvbmd7Zm9udC1zaXplOjIwcHh9Ci5zaW1wbGUtbm90ZXttYXJnaW46MDtjb2xvcjojYWViOWM5O2ZvbnQtc2l6ZToxM3B4O2xpbmUtaGVpZ2h0OjEuNDV9LnNpbXBsZS1kZXRhaWxze3BhZGRpbmc6MTZweCAyMHB4fQouc2ltcGxlLWRldGFpbHM+c3VtbWFyeXtjdXJzb3I6cG9pbnRlcjtmb250LXdlaWdodDo2MDA7Y29sb3I6I2JhYzVkNH0uc2ltcGxlLWRldGFpbHNbb3Blbl0+c3VtbWFyeXttYXJnaW4tYm90dG9tOjE2cHh9Ci5zaW1wbGUtZGV0YWlscyAuZ3JpZHtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyfS5zaW1wbGUtZGV0YWlscyAucGFuZWx7Ym94LXNoYWRvdzpub25lfQouc2ltcGxlLXNoZWxsIC5iZ3tkaXNwbGF5Om5vbmV9W2hpZGRlbl17ZGlzcGxheTpub25lIWltcG9ydGFudH0KQG1lZGlhKG1heC13aWR0aDo0MjBweCl7LnNpbXBsZS1zaGVsbHtwYWRkaW5nOjE0cHggMTJweCAzMnB4fS5zaW1wbGUtY29udHJvbHN7cGFkZGluZzoxN3B4fS5zaW1wbGUtcmVhZGluZ3N7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgyLG1pbm1heCgwLDFmcikpfX0KPC9zdHlsZT4KPGxpbmsgcmVsPSJpY29uIiBocmVmPSJkYXRhOiwiIC8+CjwvaGVhZD4KPGJvZHk+CiAgPGRpdiBjbGFzcz0iYmciPjwvZGl2PgogIDxtYWluIGNsYXNzPSJzaGVsbCBzaW1wbGUtc2hlbGwiPgo8ZGl2IGNsYXNzPSJzaW1wbGUtdGl0bGViYXIiPjxoMT7Qo9C/0YDQsNCy0LvQtdC90LjQtSDQkNCY0KA8L2gxPgo8aGVhZGVyIGNsYXNzPSJoZXJvIj4KICAgICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+CiAgICAgICAgPGRpdiBjbGFzcz0ic3RhdHVzLWNoaXAiIGlkPSJjb25uQ2hpcCI+CiAgICAgICAgICA8c3BhbiBjbGFzcz0iZG90IiBpZD0iY29ubkRvdCI+PC9zcGFuPgogICAgICAgICAgPHNwYW4gaWQ9ImNvbm5UZXh0Ij7QvtGE0LvQsNC50L08L3NwYW4+CiAgICAgICAgPC9kaXY+CiAgICAgICAgCiAgICAgIDwvZGl2PgogICAgPC9oZWFkZXI+PC9kaXY+CjxzZWN0aW9uIGNsYXNzPSJwYW5lbCBzaW1wbGUtY29udHJvbHMiPgogIDxsYWJlbCBmb3I9ImFsZ29yaXRobVNlbGVjdCI+0JDQu9Cz0L7RgNC40YLQvDwvbGFiZWw+CiAgPHNlbGVjdCBpZD0iYWxnb3JpdGhtU2VsZWN0IiBzdHlsZT0iY29sb3I6I2YyZjVmYTtiYWNrZ3JvdW5kOiMxMDE1MWM7Ym9yZGVyOjFweCBzb2xpZCAjMzU0MTUxO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjEycHg7Zm9udC1zaXplOjE2cHg7d2lkdGg6MTAwJTttaW4taGVpZ2h0OjQ2cHgiIGRpc2FibGVkIGFyaWEtZGVzY3JpYmVkYnk9ImFsZ29yaXRobU5vdGUiPgogICAgPG9wdGlvbiB2YWx1ZT0iMSI+0KHQutCw0LvRj9GA0L3Ri9C5IFYvZjwvb3B0aW9uPjxvcHRpb24gdmFsdWU9IjIiPtCS0LXQutGC0L7RgNC90YvQuSBGT0M8L29wdGlvbj4KICAgIDxvcHRpb24gdmFsdWU9IjMiPkZPQyArINCw0LTQsNC/0YLQuNCy0L3Ri9C5INCo0JjQnDwvb3B0aW9uPjxvcHRpb24gdmFsdWU9IjQiPtCY0LfQvNC10YDQtdC90LjQtSDQv9Cw0YDQsNC80LXRgtGA0L7Qsjwvb3B0aW9uPgogIDwvc2VsZWN0PgogIDxwIGNsYXNzPSJzaW1wbGUtbW9kZSIgaWQ9InNpbXBsZU1vZGUiPtCe0LbQuNC00LDQvdC40LUg0YDQtdC20LjQvNCwPC9wPgogIDxwIGNsYXNzPSJzaW1wbGUtbm90ZSIgaWQ9ImFsZ29yaXRobU5vdGUiIHJvbGU9InN0YXR1cyI+0JfQsNCz0YDRg9C30LrQsOKApjwvcD4KICA8ZGl2IGlkPSJzaW1wbGVTdGF0ZSIgcm9sZT0ic3RhdHVzIiBhcmlhLWxpdmU9InBvbGl0ZSI+0J/QvtC00LrQu9GO0YfQtdC90LjQteKApjwvZGl2Pgo8ZGl2IGNsYXNzPSJmcmVxLWJsb2NrIj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImxhYmVsIj7Qp9Cw0YHRgtC+0YLQsCAo0JPRhik8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImZyZXEtcm93Ij4KICAgICAgICAgICAgPGlucHV0IGFyaWEtbGFiZWw9ItCX0LDQtNCw0L3QuNC1INGH0LDRgdGC0L7RgtGLINC/0L7Qu9GPLCDQk9GGIiBpZD0iZnJlcVNsaWRlciIgdHlwZT0icmFuZ2UiIG1pbj0iMCIgbWF4PSI1MCIgc3RlcD0iMC4xIiB2YWx1ZT0iMTAiIC8+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImZyZXEtdG9vbHRpcCIgaWQ9ImZyZXFSZWFkb3V0Ij4xMC4wINCT0YY8L2Rpdj4KICAgICAgICA8L2Rpdj4KICA8cCBjbGFzcz0ic2ltcGxlLW5vdGUiIGlkPSJzaW1wbGVGaWVsZCI+0KfQsNGB0YLQvtGC0LAg0L/QvtC70Y86IOKAlDwvcD4KPGRpdiBjbGFzcz0iYnV0dG9uLXJvdyI+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gc3RhcnQiIGlkPSJzdGFydEJ0biI+0J/Rg9GB0Lo8L2J1dHRvbj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBzdG9wIiBpZD0ic3RvcEJ0biI+0KHRgtC+0L88L2J1dHRvbj4KICAgICAgICA8L2Rpdj48ZGl2IGNsYXNzPSJlc3RvcC1ibG9jayI+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZXN0b3AgZnVsbCIgaWQ9ImVzdG9wQnRuIj7QkNCy0LDRgNC40LnQvdGL0Lkg0YHRgtC+0L88L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QgZnVsbCIgaWQ9InNpbXBsZUNsZWFyIiBoaWRkZW4+0KHQsdGA0L7RgdC40YLRjCDQsNCy0LDRgNC40Y48L2J1dHRvbj4KICA8ZGl2IGNsYXNzPSJzaW1wbGUtcmVhZGluZ3MiPgogICAgPGRpdiBjbGFzcz0ic2ltcGxlLXJlYWRpbmciPjxzcGFuPtCo0LjQvdCwIERDPC9zcGFuPjxzdHJvbmcgaWQ9InNpbXBsZVZkYyI+4oCUPC9zdHJvbmc+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaW1wbGUtcmVhZGluZyI+PHNwYW4+0KLQvtC6IFU8L3NwYW4+PHN0cm9uZyBpZD0ic2ltcGxlSTAiPuKAlDwvc3Ryb25nPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2ltcGxlLXJlYWRpbmciPjxzcGFuPtCi0L7QuiBWPC9zcGFuPjxzdHJvbmcgaWQ9InNpbXBsZUkxIj7igJQ8L3N0cm9uZz48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpbXBsZS1yZWFkaW5nIj48c3Bhbj7QotC+0LogVzwvc3Bhbj48c3Ryb25nIGlkPSJzaW1wbGVJMiI+4oCUPC9zdHJvbmc+PC9kaXY+CiAgPC9kaXY+CiAgPHAgY2xhc3M9InNpbXBsZS1ub3RlIiBpZD0ic2ltcGxlQ3VycmVudE5vdGUiPtCi0L7QutC4IFJNUyDQv9C+INGI0YPQvdGC0LDQvDwvcD4KPC9zZWN0aW9uPgo8ZGV0YWlscyBjbGFzcz0icGFuZWwgc2ltcGxlLWRldGFpbHMiIGlkPSJtYW51YWxTZXR0aW5ncyI+PHN1bW1hcnk+0KDQsNC30LPQvtC9INC4INC30LDQvNC10LTQu9C10L3QuNC1PC9zdW1tYXJ5Pgo8ZGl2IGNsYXNzPSJtYW51YWwtY29uZmlnIiBpZD0ibWFudWFsQ29uZmlnIiBoaWRkZW4+CiAgICAgICAgICA8bGFiZWw+PGlucHV0IGlkPSJtYW51YWxDb250aW51b3VzIiB0eXBlPSJjaGVja2JveCIgY2hlY2tlZCAvPiDQoNCw0LHQvtGC0LAg0LTQviDQutC+0LzQsNC90LTRiyDCq9Ch0YLQvtC/wrs8L2xhYmVsPgogICAgICAgICAgPHA+0KfQsNGB0YLQvtGC0LAg0L/QvtC70Y86IDDigJM1MCDQk9GGLiDCq9Ch0YLQvtC/wrsg0LggMCDQk9GGIOKAlCDRgdCy0L7QsdC+0LTQvdGL0Lkg0LLRi9Cx0LXQsy48L3A+CiAgICAgICAgICA8bGFiZWw+0KDQsNC30LPQvtC9LCDQk9GGL9GBIDxpbnB1dCBpZD0ibWFudWFsQWNjZWwiIHR5cGU9Im51bWJlciIgbWluPSIwLjEiIG1heD0iNTAiIHN0ZXA9IjAuMSIgdmFsdWU9IjUiIC8+PC9sYWJlbD4KICAgICAgICAgIDxsYWJlbD7Ql9Cw0LzQtdC00LvQtdC90LjQtSwg0JPRhi/RgSA8aW5wdXQgaWQ9Im1hbnVhbERlY2VsIiB0eXBlPSJudW1iZXIiIG1pbj0iMC4xIiBtYXg9IjUiIHN0ZXA9IjAuMSIgdmFsdWU9IjEiIC8+PC9sYWJlbD4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBmdWxsIiBpZD0ibWFudWFsQXBwbHkiPtCf0YDQuNC80LXQvdC40YLRjCDRgNCw0LfQs9C+0L0g0Lgg0LfQsNC80LXQtNC70LXQvdC40LU8L2J1dHRvbj4KICAgICAgICAgIDxsYWJlbD7QodC90LjQttC10L3QuNC1INC30LDQtNCw0L3QuNGPIDxzZWxlY3QgaWQ9Im1hbnVhbERvd25tb2RlIj48b3B0aW9uIHZhbHVlPSJSQU1QIj7Qn9C70LDQstC90L4sINGBINC60L7QvdGC0YDQvtC70LXQvCBEQy3RiNC40L3Rizwvb3B0aW9uPjxvcHRpb24gdmFsdWU9IkNPQVNUIj7QktGL0LHQtdCzLCDQt9Cw0YLQtdC8INC+0YLQtNC10LvRjNC90YvQuSDQv9GD0YHQujwvb3B0aW9uPjwvc2VsZWN0PjwvbGFiZWw+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJodi1hcm0tbm90ZSIgaWQ9Im1hbnVhbFN0YXRlIj7QndCw0YHRgtGA0L7QudC60Lgg0LTQvtGB0YLRg9C/0L3RiyDQv9C+0YHQu9C1INC/0L7QtNC60LvRjtGH0LXQvdC40Y8uPC9kaXY+CiAgICAgICAgICA8bGFiZWw+0JfQsNC00LDQvdC40LUsINCT0YYgPGlucHV0IGlkPSJtYW51YWxGcmVxdWVuY3kiIHR5cGU9Im51bWJlciIgbWluPSIwIiBtYXg9IjUwIiBzdGVwPSIwLjEiIHZhbHVlPSI1IiAvPjwvbGFiZWw+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QgZnVsbCIgaWQ9Im1hbnVhbEZyZXF1ZW5jeUFwcGx5Ij7Ql9Cw0LTQsNGC0Ywg0YfQsNGB0YLQvtGC0YM8L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KPC9kZXRhaWxzPgo8ZGV0YWlscyBjbGFzcz0icGFuZWwgc2ltcGxlLWRldGFpbHMiIGlkPSJkaWFnbm9zdGljRGV0YWlscyI+PHN1bW1hcnk+0JTQuNCw0LPQvdC+0YHRgtC40LrQsCDQuCDQsNC70LPQvtGA0LjRgtC80Ys8L3N1bW1hcnk+CjxkaXYgY2xhc3M9InN0YXR1cy1jaGlwIHN0YXR1cy1tb2RlIiBpZD0ic3lzQ2hpcCI+CiAgICAgICAgICA8c3BhbiBpZD0ic3lzVGV4dCI+0KHQotCe0J88L3NwYW4+CiAgICAgICAgPC9kaXY+CiAgICAKCiAgICA8c2VjdGlvbiBjbGFzcz0iZ3JpZCI+CiAgICAgIDxkaXYgY2xhc3M9InBhbmVsIGNvbnRyb2xzIj4KICAgICAgICA8ZGl2IGNsYXNzPSJhY2Nlc3MtYmxvY2siIGlkPSJjb250cm9sQWNjZXNzQmxvY2siIGhpZGRlbj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImxhYmVsIj7QlNC+0YHRgtGD0L8g0Log0YHRgtC10L3QtNGDPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJhY2Nlc3Mtcm93Ij4KICAgICAgICAgICAgPGlucHV0IGlkPSJjb250cm9sVG9rZW4iIGNsYXNzPSJhY2Nlc3MtaW5wdXQiIHR5cGU9InBhc3N3b3JkIiBhdXRvY29tcGxldGU9ImN1cnJlbnQtcGFzc3dvcmQiIHBsYWNlaG9sZGVyPSLQmtC70Y7RhyDRg9C/0YDQsNCy0LvQtdC90LjRjyIgLz4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0iY29udHJvbFRva2VuU2F2ZSIgdHlwZT0iYnV0dG9uIj7Qn9GA0LjQvNC10L3QuNGC0Yw8L2J1dHRvbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iYWNjZXNzLXN0YXR1cyIgaWQ9ImNvbnRyb2xBY2Nlc3NTdGF0dXMiPtCi0YDQtdCx0YPQtdGC0YHRjyDQutC70Y7RhyDRg9C/0YDQsNCy0LvQtdC90LjRjzwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9Im1vZGUtcm93Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9ImxhYmVsIj7QoNC10LbQuNC8PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzZWdtZW50ZWQiIGlkPSJtb2RlVG9nZ2xlIj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0ic2VnIiBkYXRhLW1vZGU9IlZGIj5WRjwvYnV0dG9uPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJzZWciIGRhdGEtbW9kZT0iRk9DIj5GT0M8L2J1dHRvbj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0ic2VnIiBkYXRhLW1vZGU9Ik1JQyI+TUlDPC9idXR0b24+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICAKICAgICAgICAKCiAgICAgICAgCiAgICAgICAgPGRpdiBjbGFzcz0iaHYtYXJtLWJsb2NrIiBpZD0iaHZBcm1CbG9jayIgaGlkZGVuPgogICAgICAgICAgPGRpdiBjbGFzcz0iYXJtLXByb2ZpbGUtdG9nZ2xlIiBpZD0iYXJtUHJvZmlsZVRvZ2dsZSIgYXJpYS1sYWJlbD0i0J/RgNC+0YTQuNC70Ywg0LfQsNC/0YPRgdC60LAiPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJhcm0tcHJvZmlsZS1idG4iIHR5cGU9ImJ1dHRvbiIgZGF0YS1hcm0tcHJvZmlsZT0iaHYiPkhWIDMxMCDQkjwvYnV0dG9uPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJhcm0tcHJvZmlsZS1idG4iIHR5cGU9ImJ1dHRvbiIgZGF0YS1hcm0tcHJvZmlsZT0ibHYiPkxWIFRFU1Q8L2J1dHRvbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaHYtYXJtLWhlYWQiPgogICAgICAgICAgICA8ZGl2PgogICAgICAgICAgICAgIDxkaXYgY2xhc3M9ImxhYmVsIiBpZD0iYXJtUHJvZmlsZUxhYmVsIj7QodC40LvQvtCy0LDRjyDRiNC40L3QsDwvZGl2PgogICAgICAgICAgICAgIDxzdHJvbmcgaWQ9Imh2QXJtU3RhdHVzIj5IViDQt9Cw0LHQu9C+0LrQuNGA0L7QstCw0L3QsDwvc3Ryb25nPgogICAgICAgICAgICA8L2Rpdj4KICAgICAgICAgICAgPHNwYW4gY2xhc3M9Imh2LWFybS10aW1lciIgaWQ9Imh2QXJtVGltZXIiPjAuMCDRgTwvc3Bhbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGlucHV0CiAgICAgICAgICAgIGlkPSJodkFybUNvbmZpcm0iCiAgICAgICAgICAgIGNsYXNzPSJodi1hcm0taW5wdXQiCiAgICAgICAgICAgIHR5cGU9InRleHQiCiAgICAgICAgICAgIGlucHV0bW9kZT0idGV4dCIKICAgICAgICAgICAgYXV0b2NvbXBsZXRlPSJvZmYiCiAgICAgICAgICAgIGF1dG9jYXBpdGFsaXplPSJjaGFyYWN0ZXJzIgogICAgICAgICAgICBwbGFjZWhvbGRlcj0i0JLQstC10LTQuNGC0LUgQVJNIDMxMFYiCiAgICAgICAgICAvPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGh2LWFybSBmdWxsIiBpZD0iaHZBcm1CdG4iPtCg0LDQt9GA0LXRiNC40YLRjCBIViDQvdCwIDMwINGB0LXQutGD0L3QtDwvYnV0dG9uPgogICAgICAgICAgPHAgY2xhc3M9Imh2LWFybS1ub3RlIiBpZD0iYXJtUHJvZmlsZU5vdGUiPtCg0LDQt9GA0LXRiNC10L3QuNC1INC+0LPRgNCw0L3QuNGH0LXQvdC+INC/0L4g0LLRgNC10LzQtdC90LguIFNUT1AsIEVTVE9QLCDQv9C10YDQtdC30LDQv9GD0YHQuiwg0L/QvtGC0LXRgNGPINC60L7QvdGC0YDQvtC70Y8g0LjQu9C4INGC0LDQudC8LdCw0YPRgiDRgdC90LjQvNCw0Y7RgiDQtdCz0L4uPC9wPgogICAgICAgICAgPGRldGFpbHMgY2xhc3M9InZidXMtY2FwdHVyZS1ibG9jayI+PHN1bW1hcnk+0JrQsNC70LjQsdGA0L7QstC60LAgREMt0YjQuNC90Ys8L3N1bW1hcnk+CiAgICAgICAgICAgIDxpbnB1dAogICAgICAgICAgICAgIGlkPSJ2YnVzTWV0ZXJJbnB1dCIKICAgICAgICAgICAgICBjbGFzcz0iaHYtYXJtLWlucHV0IgogICAgICAgICAgICAgIHR5cGU9Im51bWJlciIKICAgICAgICAgICAgICBpbnB1dG1vZGU9ImRlY2ltYWwiCiAgICAgICAgICAgICAgbWluPSIwIgogICAgICAgICAgICAgIG1heD0iNDUwIgogICAgICAgICAgICAgIHN0ZXA9IjAuMSIKICAgICAgICAgICAgICBwbGFjZWhvbGRlcj0i0J3QsNC/0YDRj9C20LXQvdC40LUg0LzRg9C70YzRgtC40LzQtdGC0YDQsCwg0JIiCiAgICAgICAgICAgIC8+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBmdWxsIiBpZD0idmJ1c0NhcHR1cmVCdG4iPtCX0LDQv9C40YHQsNGC0Ywg0L/QvtC60LDQt9Cw0L3QuNC1IFZidXM8L2J1dHRvbj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iaHYtYXJtLW5vdGUiIGlkPSJ2YnVzQ2FsaWJyYXRpb25TdGF0ZSI+0JrQsNC70LjQsdGA0L7QstC60LAgVmJ1cyDQvdC1INC/0L7QtNGC0LLQtdGA0LbQtNC10L3QsC48L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iaHYtYXJtLW5vdGUiIGlkPSJ2YnVzQ2FwdHVyZVJlc3VsdCI+0KLQvtC70YzQutC+INC40LfQvNC10YDQtdC90LjQtTog0YDQtdC70LUg0Lgg0KjQmNCcINC90LUg0LLQutC70Y7Rh9Cw0Y7RgtGB0Y8uPC9kaXY+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBmdWxsIiBpZD0idmJ1c1Jlc2V0QnRuIj7QodCx0YDQvtGB0LjRgtGMINC60LDQu9C40LHRgNC+0LLQutGDIFZidXM8L2J1dHRvbj4KICAgICAgICAgIDwvZGV0YWlscz4KICAgICAgICA8L2Rpdj4KCiAgICAgICAgPGRpdiBjbGFzcz0iaW8tYmxvY2siPgogICAgICAgICAgPGRpdiBjbGFzcz0ibGFiZWwiPklQTTE1IEkvTzwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iaW8tcm93Ij4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0icGZjQnRuIj5QRkM6IE9GRjwvYnV0dG9uPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJicmFrZS1yb3ciPgogICAgICAgICAgICA8aW5wdXQgaWQ9ImJyYWtlU2xpZGVyIiB0eXBlPSJyYW5nZSIgbWluPSIwIiBtYXg9IjEiIHN0ZXA9IjAuMDUiIHZhbHVlPSIwIiAvPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJicmFrZS1yZWFkb3V0IiBpZD0iYnJha2VSZWFkb3V0Ij5CUksgMCU8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iZmFuLXJvdyI+CiAgICAgICAgICAgIDxpbnB1dCBpZD0iZmFuU2xpZGVyIiB0eXBlPSJyYW5nZSIgbWluPSIwIiBtYXg9IjEiIHN0ZXA9IjAuMDUiIHZhbHVlPSIwIiAvPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJmYW4tcmVhZG91dCIgaWQ9ImZhblJlYWRvdXQiPkZBTiAwJTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+CgogICAgICAgIAogICAgICA8L2Rpdj4KCiAgICAgIDxkaXYgY2xhc3M9InBhbmVsIHN0YXR1cyI+CiAgICAgICAgPGgyPtCh0YLQsNGC0YPRgTwvaDI+CiAgICAgICAgPGRpdiBjbGFzcz0ic3RhdHVzLWdyaWQiPgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCh0L7RgdGC0L7Rj9C90LjQtTwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0ic3RhdGVWYWwiPlNBRkU8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCg0LXQttC40Lw8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9Im1vZGVWYWwiPkZPQzwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0JrQvtC90YLRg9GAIE51Y2xlbzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iYmFja2VuZFZhbCI+RFVUWTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KHQstGP0LfRjCBTVE0zMjwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0ibGlua1ZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCo0JjQnDwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0icHdtVmFsIj4wPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QodC60L7RgNC+0YHRgtGMPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJzcGVlZFZhbCI+MCDQvtCxL9C80LjQvTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KjQuNC90LAgREM8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InZkY1ZhbCI+MC4wIFY8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCg0LDQtNC40LDRgtC+0YAgSVBNPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJ0ZW1wVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+SWEvSWIvSWM8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImN1cnJWYWwiPjAgLyAwIC8gMCBBPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj5QaGFzZSBtZWFzIEEvQi9DPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJwaGFzZVZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPklkINC30LDQtNCw0L3QvjwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iaWRSZWZWYWwiPjAuMDAgQTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+TUlDINGN0LrQvtC90L7QvNC40Y88L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9Im1pY1NhdmVWYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj5QRkMvQlJLPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJpb1ZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCS0LXQvdGC0LjQu9GP0YLQvtGAPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJmYW5WYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QntCx0YDQsNGC0L3QsNGPINGB0LLRj9C30Yw8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImVuY1ZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9InN0YXR1cy1mb290ZXIiPgogICAgICAgICAgPHNwYW4gaWQ9Imxhc3RVcGRhdGUiPtCd0LXRgiDQtNCw0L3QvdGL0YU8L3NwYW4+CiAgICAgICAgICA8YnV0dG9uIGlkPSJia2luVHJhY2VMb2FkIiBjbGFzcz0iYnRuIGdob3N0IiB0eXBlPSJidXR0b24iPtCh0YfQuNGC0LDRgtGMINGB0L3QuNC80L7QuiBCS0lOPC9idXR0b24+CiAgICAgICAgICA8c3BhbiBpZD0iYmtpblRyYWNlU3RhdHVzIj7QodC90LjQvNC+0Log0L/QvtGP0LLQuNGC0YHRjyDQv9C+0YHQu9C1INGB0YDQsNCx0LDRgtGL0LLQsNC90LjRjyDQt9Cw0YnQuNGC0YsuPC9zcGFuPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KCiAgICA8c2VjdGlvbiBjbGFzcz0icGFuZWwiIGlkPSJyZXNlYXJjaFBhbmVsIj48aDI+0JjRgdGB0LvQtdC00L7QstCw0YLQtdC70YzRgdC60LDRjyDRgdC10YDQuNGPPC9oMj48ZGl2IGlkPSJyZXNlYXJjaEFsZ29yaXRobXMiPtCe0LbQuNC00LDQvdC40LUg0L/QvtC00YLQstC10YDQttC00LXQvdC40Y8gTnVjbGVvPC9kaXY+PC9zZWN0aW9uPgogICAgPHNlY3Rpb24gY2xhc3M9InBhbmVsIGxvZ3MiPgogICAgICA8ZGl2IGNsYXNzPSJsb2ctcm93Ij4KICAgICAgICA8c3BhbiBjbGFzcz0ibG9nLXRpdGxlIj7Qm9C+0LPQuDwvc3Bhbj4KICAgICAgICA8c2VsZWN0IGlkPSJsb2dIb3VycyI+CiAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIxIj4xINGH0LDRgTwvb3B0aW9uPgogICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iNiI+NiDRh9Cw0YHQvtCyPC9vcHRpb24+CiAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIyNCIgc2VsZWN0ZWQ+MjQg0YfQsNGB0LA8L29wdGlvbj4KICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8YnV0dG9uIGlkPSJsb2dEb3dubG9hZCIgY2xhc3M9ImJ0biBnaG9zdCIgdHlwZT0iYnV0dG9uIj7QodC60LDRh9Cw0YLRjDwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgIDwvc2VjdGlvbj4KICAKPC9kZXRhaWxzPgo8L21haW4+CgogIDxzY3JpcHQgc3JjPSJhcHAuanM/dWk9MjkzNy1pcnEtdGltaW5nIj48L3NjcmlwdD4KPC9ib2R5Pgo8L2h0bWw+Cg==')
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
