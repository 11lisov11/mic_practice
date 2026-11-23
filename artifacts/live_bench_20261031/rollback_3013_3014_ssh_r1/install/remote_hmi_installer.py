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
    """Installation only; applies solely to the confirmed isolated setup."""
    try:
        if max_vdc != 20:
            return False, 'unsupported installer argument'
        if (s['fw_build'], s['mc_fw_build']) not in ((2026103015, 2026103016), (2026103013, 2026103014)):
            return False, 'unexpected pair'
        if s['state'] != 'SAFE' or s['pwm'] != 0 or s.get('hmi_hv_armed') != 0 or int(s['bp_status']) & 0x22:
            return False, 'outputs or RUN request active'
        if s['rpc_schema_version'] != 3 or s['mc_capabilities'] != 1 or s['bp_mcsdk_telemetry'] != 1:
            return False, 'unexpected telemetry contract'
        if not 0 <= s['mc_age_ms'] < 300:
            return False, 'stale controller reply'
        if s.get('mc_last_uart_error_flags', 0) != 0:
            return False, 'recent UART hardware error'
        if any(s.get(k, 0) != 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')):
            return False, 'service output active'
        return True, 'isolated programming only: operator J1/J4 OFF and ribbon absent; ADC bus input disconnected'
    except (KeyError, TypeError, ValueError, OverflowError):
        return False, 'missing or invalid controller state'


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
    index_data=base64.b64decode('PCFkb2N0eXBlIGh0bWw+CjxodG1sIGxhbmc9InJ1Ij4KPGhlYWQ+CiAgPG1ldGEgY2hhcnNldD0idXRmLTgiIC8+CiAgPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xIiAvPgogIDx0aXRsZT7QkNCY0KAgwrcg0YLQvtC60Lggwrcg0KPQv9GA0LDQstC70LXQvdC40LUg0LTQstC40LPQsNGC0LXQu9C10LwgVU5PUTwvdGl0bGU+CiAgPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSJzdHlsZS5jc3M/dWk9MzAxMy1ib290LWNhcHR1cmUiIC8+CjxzdHlsZT4KLnNpbXBsZS1zaGVsbHttYXgtd2lkdGg6NjgwcHg7Z2FwOjE0cHg7cGFkZGluZy10b3A6MjBweH0uc2ltcGxlLXNoZWxsIGgxe2ZvbnQtc2l6ZToyNHB4O21hcmdpbjowfQouc2ltcGxlLXNoZWxsIC5oZXJve2dhcDo4cHh9LnNpbXBsZS1zaGVsbCAuc3RhdHVzLXJvd3tqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbn0KLnNpbXBsZS10aXRsZWJhcntkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2dhcDoxMnB4fQouc2ltcGxlLXRpdGxlYmFyIGgxe2ZvbnQtc2l6ZToyMnB4fS5zaW1wbGUtdGl0bGViYXIgLnN0YXR1cy1yb3d7d2lkdGg6YXV0b30KLnNpbXBsZS1jb250cm9sc3twYWRkaW5nOjIycHg7ZGlzcGxheTpncmlkO2dhcDoxOHB4fS5zaW1wbGUtbW9kZXttYXJnaW46MDtjb2xvcjojYWViOWM5O2ZvbnQtc2l6ZToxNHB4fQojc2ltcGxlU3RhdGV7Zm9udC1zaXplOjIwcHg7Zm9udC13ZWlnaHQ6NzAwO2xpbmUtaGVpZ2h0OjEuMzV9I3NpbXBsZVN0YXRlW2RhdGEtc3RhdGU9ZXJyb3Jde2NvbG9yOiNmZjgyOTh9CiNzaW1wbGVTdGF0ZVtkYXRhLXN0YXRlPXJ1bm5pbmdde2NvbG9yOiM0OWRjYzh9LnNpbXBsZS1jb250cm9scyAuZnJlcS1ibG9ja3ttYXJnaW46MDtwb3NpdGlvbjpzdGF0aWN9Ci5zaW1wbGUtY29udHJvbHMgLmZyZXEtdG9vbHRpcHtwb3NpdGlvbjpzdGF0aWM7b3BhY2l0eToxO3RyYW5zZm9ybTpub25lO3BvaW50ZXItZXZlbnRzOm5vbmU7YmFja2dyb3VuZDpub25lO2JveC1zaGFkb3c6bm9uZTt0ZXh0LWFsaWduOmxlZnQ7Zm9udC1zaXplOjMycHg7cGFkZGluZzo4cHggMCAwfQouc2ltcGxlLWNvbnRyb2xzIC5mcmVxLXJvd3t3aWR0aDoxMDAlfS5zaW1wbGUtY29udHJvbHMgaW5wdXRbdHlwZT1yYW5nZV17d2lkdGg6MTAwJTttaW4taGVpZ2h0OjQwcHh9Ci5zaW1wbGUtY29udHJvbHMgLmJ1dHRvbi1yb3d7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDoxMnB4O21hcmdpbjowfQouc2ltcGxlLWNvbnRyb2xzIC5idXR0b24tcm93IC5idG57Zm9udC1zaXplOjE5cHg7bWluLWhlaWdodDo1NHB4fS5zaW1wbGUtY29udHJvbHMgLmVzdG9wLWJsb2Nre21hcmdpbjowfQouc2ltcGxlLWNvbnRyb2xzIC5idG4uZXN0b3AsLnNpbXBsZS1jb250cm9scyAuYnRuLmVzdG9wLmFjdGl2ZXtiYWNrZ3JvdW5kOiNjOTFkNDA7Y29sb3I6d2hpdGU7bWluLWhlaWdodDo0OHB4fQouc2ltcGxlLXJlYWRpbmdze2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDQsbWlubWF4KDAsMWZyKSk7Z2FwOjEwcHh9Ci5zaW1wbGUtcmVhZGluZ3tiYWNrZ3JvdW5kOiMxMDE1MWM7Ym9yZGVyOjFweCBzb2xpZCAjMjczMTNkO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjEycHggOHB4fQouc2ltcGxlLXJlYWRpbmcgc3BhbntkaXNwbGF5OmJsb2NrO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOiNhZWI5Yzk7bWFyZ2luLWJvdHRvbTo3cHh9LnNpbXBsZS1yZWFkaW5nIHN0cm9uZ3tmb250LXNpemU6MjBweH0KLnNpbXBsZS1ub3Rle21hcmdpbjowO2NvbG9yOiNhZWI5Yzk7Zm9udC1zaXplOjEzcHg7bGluZS1oZWlnaHQ6MS40NX0uc2ltcGxlLWRldGFpbHN7cGFkZGluZzoxNnB4IDIwcHh9Ci5zaW1wbGUtZGV0YWlscz5zdW1tYXJ5e2N1cnNvcjpwb2ludGVyO2ZvbnQtd2VpZ2h0OjYwMDtjb2xvcjojYmFjNWQ0fS5zaW1wbGUtZGV0YWlsc1tvcGVuXT5zdW1tYXJ5e21hcmdpbi1ib3R0b206MTZweH0KLnNpbXBsZS1kZXRhaWxzIC5ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9LnNpbXBsZS1kZXRhaWxzIC5wYW5lbHtib3gtc2hhZG93Om5vbmV9Ci5zaW1wbGUtc2hlbGwgLmJne2Rpc3BsYXk6bm9uZX1baGlkZGVuXXtkaXNwbGF5Om5vbmUhaW1wb3J0YW50fQpAbWVkaWEobWF4LXdpZHRoOjQyMHB4KXsuc2ltcGxlLXNoZWxse3BhZGRpbmc6MTRweCAxMnB4IDMycHh9LnNpbXBsZS1jb250cm9sc3twYWRkaW5nOjE3cHh9LnNpbXBsZS1yZWFkaW5nc3tncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDIsbWlubWF4KDAsMWZyKSl9fQo8L3N0eWxlPgo8bGluayByZWw9Imljb24iIGhyZWY9ImRhdGE6LCIgLz4KPC9oZWFkPgo8Ym9keT4KICA8ZGl2IGNsYXNzPSJiZyI+PC9kaXY+CiAgPG1haW4gY2xhc3M9InNoZWxsIHNpbXBsZS1zaGVsbCI+CjxkaXYgY2xhc3M9InNpbXBsZS10aXRsZWJhciI+PGgxPtCj0L/RgNCw0LLQu9C10L3QuNC1INCQ0JjQoDwvaDE+CjxoZWFkZXIgY2xhc3M9Imhlcm8iPgogICAgICA8ZGl2IGNsYXNzPSJzdGF0dXMtcm93Ij4KICAgICAgICA8ZGl2IGNsYXNzPSJzdGF0dXMtY2hpcCIgaWQ9ImNvbm5DaGlwIj4KICAgICAgICAgIDxzcGFuIGNsYXNzPSJkb3QiIGlkPSJjb25uRG90Ij48L3NwYW4+CiAgICAgICAgICA8c3BhbiBpZD0iY29ublRleHQiPtC+0YTQu9Cw0LnQvTwvc3Bhbj4KICAgICAgICA8L2Rpdj4KICAgICAgICAKICAgICAgPC9kaXY+CiAgICA8L2hlYWRlcj48L2Rpdj4KPHNlY3Rpb24gY2xhc3M9InBhbmVsIHNpbXBsZS1jb250cm9scyI+CiAgPGxhYmVsIGZvcj0iYWxnb3JpdGhtU2VsZWN0Ij7QkNC70LPQvtGA0LjRgtC8PC9sYWJlbD4KICA8c2VsZWN0IGlkPSJhbGdvcml0aG1TZWxlY3QiIHN0eWxlPSJjb2xvcjojZjJmNWZhO2JhY2tncm91bmQ6IzEwMTUxYztib3JkZXI6MXB4IHNvbGlkICMzNTQxNTE7Ym9yZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTJweDtmb250LXNpemU6MTZweDt3aWR0aDoxMDAlO21pbi1oZWlnaHQ6NDZweCIgZGlzYWJsZWQgYXJpYS1kZXNjcmliZWRieT0iYWxnb3JpdGhtTm90ZSI+CiAgICA8b3B0aW9uIHZhbHVlPSIxIj7QodC60LDQu9GP0YDQvdGL0LkgVi9mPC9vcHRpb24+PG9wdGlvbiB2YWx1ZT0iMiI+0JLQtdC60YLQvtGA0L3Ri9C5IEZPQzwvb3B0aW9uPgogICAgPG9wdGlvbiB2YWx1ZT0iMyI+Rk9DICsg0LDQtNCw0L/RgtC40LLQvdGL0Lkg0KjQmNCcPC9vcHRpb24+PG9wdGlvbiB2YWx1ZT0iNCI+0JjQt9C80LXRgNC10L3QuNC1INC/0LDRgNCw0LzQtdGC0YDQvtCyPC9vcHRpb24+CiAgPC9zZWxlY3Q+CiAgPHAgY2xhc3M9InNpbXBsZS1tb2RlIiBpZD0ic2ltcGxlTW9kZSI+0J7QttC40LTQsNC90LjQtSDRgNC10LbQuNC80LA8L3A+CiAgPHAgY2xhc3M9InNpbXBsZS1ub3RlIiBpZD0iYWxnb3JpdGhtTm90ZSIgcm9sZT0ic3RhdHVzIj7Ql9Cw0LPRgNGD0LfQutCw4oCmPC9wPgogIDxkaXYgaWQ9InNpbXBsZVN0YXRlIiByb2xlPSJzdGF0dXMiIGFyaWEtbGl2ZT0icG9saXRlIj7Qn9C+0LTQutC70Y7Rh9C10L3QuNC14oCmPC9kaXY+CjxkaXYgY2xhc3M9ImZyZXEtYmxvY2siPgogICAgICAgICAgPGRpdiBjbGFzcz0ibGFiZWwiPtCn0LDRgdGC0L7RgtCwICjQk9GGKTwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iZnJlcS1yb3ciPgogICAgICAgICAgICA8aW5wdXQgYXJpYS1sYWJlbD0i0JfQsNC00LDQvdC40LUg0YfQsNGB0YLQvtGC0Ysg0L/QvtC70Y8sINCT0YYiIGlkPSJmcmVxU2xpZGVyIiB0eXBlPSJyYW5nZSIgbWluPSIwIiBtYXg9IjUwIiBzdGVwPSIwLjEiIHZhbHVlPSIxMCIgLz4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iZnJlcS10b29sdGlwIiBpZD0iZnJlcVJlYWRvdXQiPjEwLjAg0JPRhjwvZGl2PgogICAgICAgIDwvZGl2PgogIDxwIGNsYXNzPSJzaW1wbGUtbm90ZSIgaWQ9InNpbXBsZUZpZWxkIj7Qp9Cw0YHRgtC+0YLQsCDQv9C+0LvRjzog4oCUPC9wPgo8ZGl2IGNsYXNzPSJidXR0b24tcm93Ij4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBzdGFydCIgaWQ9InN0YXJ0QnRuIj7Qn9GD0YHQujwvYnV0dG9uPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIHN0b3AiIGlkPSJzdG9wQnRuIj7QodGC0L7QvzwvYnV0dG9uPgogICAgICAgIDwvZGl2PjxkaXYgY2xhc3M9ImVzdG9wLWJsb2NrIj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBlc3RvcCBmdWxsIiBpZD0iZXN0b3BCdG4iPtCQ0LLQsNGA0LjQudC90YvQuSDRgdGC0L7QvzwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBmdWxsIiBpZD0ic2ltcGxlQ2xlYXIiIGhpZGRlbj7QodCx0YDQvtGB0LjRgtGMINCw0LLQsNGA0LjRjjwvYnV0dG9uPgogIDxkaXYgY2xhc3M9InNpbXBsZS1yZWFkaW5ncyI+CiAgICA8ZGl2IGNsYXNzPSJzaW1wbGUtcmVhZGluZyI+PHNwYW4+0KjQuNC90LAgREM8L3NwYW4+PHN0cm9uZyBpZD0ic2ltcGxlVmRjIj7igJQ8L3N0cm9uZz48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InNpbXBsZS1yZWFkaW5nIj48c3Bhbj7QotC+0LogVTwvc3Bhbj48c3Ryb25nIGlkPSJzaW1wbGVJMCI+4oCUPC9zdHJvbmc+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzaW1wbGUtcmVhZGluZyI+PHNwYW4+0KLQvtC6IFY8L3NwYW4+PHN0cm9uZyBpZD0ic2ltcGxlSTEiPuKAlDwvc3Ryb25nPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic2ltcGxlLXJlYWRpbmciPjxzcGFuPtCi0L7QuiBXPC9zcGFuPjxzdHJvbmcgaWQ9InNpbXBsZUkyIj7igJQ8L3N0cm9uZz48L2Rpdj4KICA8L2Rpdj4KICA8cCBjbGFzcz0ic2ltcGxlLW5vdGUiIGlkPSJzaW1wbGVDdXJyZW50Tm90ZSI+0KLQvtC60LggUk1TINC/0L4g0YjRg9C90YLQsNC8PC9wPgo8L3NlY3Rpb24+CjxkZXRhaWxzIGNsYXNzPSJwYW5lbCBzaW1wbGUtZGV0YWlscyIgaWQ9Im1hbnVhbFNldHRpbmdzIj48c3VtbWFyeT7QoNCw0LfQs9C+0L0g0Lgg0LfQsNC80LXQtNC70LXQvdC40LU8L3N1bW1hcnk+CjxkaXYgY2xhc3M9Im1hbnVhbC1jb25maWciIGlkPSJtYW51YWxDb25maWciIGhpZGRlbj4KICAgICAgICAgIDxsYWJlbD48aW5wdXQgaWQ9Im1hbnVhbENvbnRpbnVvdXMiIHR5cGU9ImNoZWNrYm94IiBjaGVja2VkIC8+INCg0LDQsdC+0YLQsCDQtNC+INC60L7QvNCw0L3QtNGLIMKr0KHRgtC+0L/CuzwvbGFiZWw+CiAgICAgICAgICA8cD7Qp9Cw0YHRgtC+0YLQsCDQv9C+0LvRjzogMOKAkzUwINCT0YYuIMKr0KHRgtC+0L/CuyDQuCAwINCT0YYg4oCUINGB0LLQvtCx0L7QtNC90YvQuSDQstGL0LHQtdCzLjwvcD4KICAgICAgICAgIDxsYWJlbD7QoNCw0LfQs9C+0L0sINCT0YYv0YEgPGlucHV0IGlkPSJtYW51YWxBY2NlbCIgdHlwZT0ibnVtYmVyIiBtaW49IjAuMSIgbWF4PSI1MCIgc3RlcD0iMC4xIiB2YWx1ZT0iNSIgLz48L2xhYmVsPgogICAgICAgICAgPGxhYmVsPtCX0LDQvNC10LTQu9C10L3QuNC1LCDQk9GGL9GBIDxpbnB1dCBpZD0ibWFudWFsRGVjZWwiIHR5cGU9Im51bWJlciIgbWluPSIwLjEiIG1heD0iNSIgc3RlcD0iMC4xIiB2YWx1ZT0iMSIgLz48L2xhYmVsPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IGZ1bGwiIGlkPSJtYW51YWxBcHBseSI+0J/RgNC40LzQtdC90LjRgtGMINGA0LDQt9Cz0L7QvSDQuCDQt9Cw0LzQtdC00LvQtdC90LjQtTwvYnV0dG9uPgogICAgICAgICAgPGxhYmVsPtCh0L3QuNC20LXQvdC40LUg0LfQsNC00LDQvdC40Y8gPHNlbGVjdCBpZD0ibWFudWFsRG93bm1vZGUiPjxvcHRpb24gdmFsdWU9IlJBTVAiPtCf0LvQsNCy0L3Qviwg0YEg0LrQvtC90YLRgNC+0LvQtdC8IERDLdGI0LjQvdGLPC9vcHRpb24+PG9wdGlvbiB2YWx1ZT0iQ09BU1QiPtCS0YvQsdC10LMsINC30LDRgtC10Lwg0L7RgtC00LXQu9GM0L3Ri9C5INC/0YPRgdC6PC9vcHRpb24+PC9zZWxlY3Q+PC9sYWJlbD4KICAgICAgICAgIDxkaXYgY2xhc3M9Imh2LWFybS1ub3RlIiBpZD0ibWFudWFsU3RhdGUiPtCd0LDRgdGC0YDQvtC50LrQuCDQtNC+0YHRgtGD0L/QvdGLINC/0L7RgdC70LUg0L/QvtC00LrQu9GO0YfQtdC90LjRjy48L2Rpdj4KICAgICAgICAgIDxsYWJlbD7Ql9Cw0LTQsNC90LjQtSwg0JPRhiA8aW5wdXQgaWQ9Im1hbnVhbEZyZXF1ZW5jeSIgdHlwZT0ibnVtYmVyIiBtaW49IjAiIG1heD0iNTAiIHN0ZXA9IjAuMSIgdmFsdWU9IjUiIC8+PC9sYWJlbD4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCBmdWxsIiBpZD0ibWFudWFsRnJlcXVlbmN5QXBwbHkiPtCX0LDQtNCw0YLRjCDRh9Cw0YHRgtC+0YLRgzwvYnV0dG9uPgogICAgICAgIDwvZGl2Pgo8L2RldGFpbHM+CjxkZXRhaWxzIGNsYXNzPSJwYW5lbCBzaW1wbGUtZGV0YWlscyIgaWQ9ImRpYWdub3N0aWNEZXRhaWxzIj48c3VtbWFyeT7QlNC40LDQs9C90L7RgdGC0LjQutCwINC4INCw0LvQs9C+0YDQuNGC0LzRizwvc3VtbWFyeT4KPGRpdiBjbGFzcz0ic3RhdHVzLWNoaXAgc3RhdHVzLW1vZGUiIGlkPSJzeXNDaGlwIj4KICAgICAgICAgIDxzcGFuIGlkPSJzeXNUZXh0Ij7QodCi0J7Qnzwvc3Bhbj4KICAgICAgICA8L2Rpdj4KICAgIAoKICAgIDxzZWN0aW9uIGNsYXNzPSJncmlkIj4KICAgICAgPGRpdiBjbGFzcz0icGFuZWwgY29udHJvbHMiPgogICAgICAgIDxkaXYgY2xhc3M9ImFjY2Vzcy1ibG9jayIgaWQ9ImNvbnRyb2xBY2Nlc3NCbG9jayIgaGlkZGVuPgogICAgICAgICAgPGRpdiBjbGFzcz0ibGFiZWwiPtCU0L7RgdGC0YPQvyDQuiDRgdGC0LXQvdC00YM8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImFjY2Vzcy1yb3ciPgogICAgICAgICAgICA8aW5wdXQgaWQ9ImNvbnRyb2xUb2tlbiIgY2xhc3M9ImFjY2Vzcy1pbnB1dCIgdHlwZT0icGFzc3dvcmQiIGF1dG9jb21wbGV0ZT0iY3VycmVudC1wYXNzd29yZCIgcGxhY2Vob2xkZXI9ItCa0LvRjtGHINGD0L/RgNCw0LLQu9C10L3QuNGPIiAvPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIGlkPSJjb250cm9sVG9rZW5TYXZlIiB0eXBlPSJidXR0b24iPtCf0YDQuNC80LXQvdC40YLRjDwvYnV0dG9uPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJhY2Nlc3Mtc3RhdHVzIiBpZD0iY29udHJvbEFjY2Vzc1N0YXR1cyI+0KLRgNC10LHRg9C10YLRgdGPINC60LvRjtGHINGD0L/RgNCw0LLQu9C10L3QuNGPPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0ibW9kZS1yb3ciPgogICAgICAgICAgPGRpdiBjbGFzcz0ibGFiZWwiPtCg0LXQttC40Lw8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNlZ21lbnRlZCIgaWQ9Im1vZGVUb2dnbGUiPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJzZWciIGRhdGEtbW9kZT0iVkYiPlZGPC9idXR0b24+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9InNlZyIgZGF0YS1tb2RlPSJGT0MiPkZPQzwvYnV0dG9uPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJzZWciIGRhdGEtbW9kZT0iTUlDIj5NSUM8L2J1dHRvbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIAogICAgICAgIAoKICAgICAgICAKICAgICAgICA8ZGl2IGNsYXNzPSJodi1hcm0tYmxvY2siIGlkPSJodkFybUJsb2NrIiBoaWRkZW4+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJhcm0tcHJvZmlsZS10b2dnbGUiIGlkPSJhcm1Qcm9maWxlVG9nZ2xlIiBhcmlhLWxhYmVsPSLQn9GA0L7RhNC40LvRjCDQt9Cw0L/Rg9GB0LrQsCI+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImFybS1wcm9maWxlLWJ0biIgdHlwZT0iYnV0dG9uIiBkYXRhLWFybS1wcm9maWxlPSJodiI+SFYgMzEwINCSPC9idXR0b24+CiAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImFybS1wcm9maWxlLWJ0biIgdHlwZT0iYnV0dG9uIiBkYXRhLWFybS1wcm9maWxlPSJsdiI+TFYgVEVTVDwvYnV0dG9uPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJodi1hcm0taGVhZCI+CiAgICAgICAgICAgIDxkaXY+CiAgICAgICAgICAgICAgPGRpdiBjbGFzcz0ibGFiZWwiIGlkPSJhcm1Qcm9maWxlTGFiZWwiPtCh0LjQu9C+0LLQsNGPINGI0LjQvdCwPC9kaXY+CiAgICAgICAgICAgICAgPHN0cm9uZyBpZD0iaHZBcm1TdGF0dXMiPkhWINC30LDQsdC70L7QutC40YDQvtCy0LDQvdCwPC9zdHJvbmc+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgICA8c3BhbiBjbGFzcz0iaHYtYXJtLXRpbWVyIiBpZD0iaHZBcm1UaW1lciI+MC4wINGBPC9zcGFuPgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8aW5wdXQKICAgICAgICAgICAgaWQ9Imh2QXJtQ29uZmlybSIKICAgICAgICAgICAgY2xhc3M9Imh2LWFybS1pbnB1dCIKICAgICAgICAgICAgdHlwZT0idGV4dCIKICAgICAgICAgICAgaW5wdXRtb2RlPSJ0ZXh0IgogICAgICAgICAgICBhdXRvY29tcGxldGU9Im9mZiIKICAgICAgICAgICAgYXV0b2NhcGl0YWxpemU9ImNoYXJhY3RlcnMiCiAgICAgICAgICAgIHBsYWNlaG9sZGVyPSLQktCy0LXQtNC40YLQtSBBUk0gMzEwViIKICAgICAgICAgIC8+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gaHYtYXJtIGZ1bGwiIGlkPSJodkFybUJ0biI+0KDQsNC30YDQtdGI0LjRgtGMIEhWINC90LAgMzAg0YHQtdC60YPQvdC0PC9idXR0b24+CiAgICAgICAgICA8cCBjbGFzcz0iaHYtYXJtLW5vdGUiIGlkPSJhcm1Qcm9maWxlTm90ZSI+0KDQsNC30YDQtdGI0LXQvdC40LUg0L7Qs9GA0LDQvdC40YfQtdC90L4g0L/QviDQstGA0LXQvNC10L3QuC4gU1RPUCwgRVNUT1AsINC/0LXRgNC10LfQsNC/0YPRgdC6LCDQv9C+0YLQtdGA0Y8g0LrQvtC90YLRgNC+0LvRjyDQuNC70Lgg0YLQsNC50Lwt0LDRg9GCINGB0L3QuNC80LDRjtGCINC10LPQvi48L3A+CiAgICAgICAgICA8ZGV0YWlscyBjbGFzcz0idmJ1cy1jYXB0dXJlLWJsb2NrIj48c3VtbWFyeT7QmtCw0LvQuNCx0YDQvtCy0LrQsCBEQy3RiNC40L3Rizwvc3VtbWFyeT4KICAgICAgICAgICAgPGlucHV0CiAgICAgICAgICAgICAgaWQ9InZidXNNZXRlcklucHV0IgogICAgICAgICAgICAgIGNsYXNzPSJodi1hcm0taW5wdXQiCiAgICAgICAgICAgICAgdHlwZT0ibnVtYmVyIgogICAgICAgICAgICAgIGlucHV0bW9kZT0iZGVjaW1hbCIKICAgICAgICAgICAgICBtaW49IjAiCiAgICAgICAgICAgICAgbWF4PSI0NTAiCiAgICAgICAgICAgICAgc3RlcD0iMC4xIgogICAgICAgICAgICAgIHBsYWNlaG9sZGVyPSLQndCw0L/RgNGP0LbQtdC90LjQtSDQvNGD0LvRjNGC0LjQvNC10YLRgNCwLCDQkiIKICAgICAgICAgICAgLz4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IGZ1bGwiIGlkPSJ2YnVzQ2FwdHVyZUJ0biI+0JfQsNC/0LjRgdCw0YLRjCDQv9C+0LrQsNC30LDQvdC40LUgVmJ1czwvYnV0dG9uPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJodi1hcm0tbm90ZSIgaWQ9InZidXNDYWxpYnJhdGlvblN0YXRlIj7QmtCw0LvQuNCx0YDQvtCy0LrQsCBWYnVzINC90LUg0L/QvtC00YLQstC10YDQttC00LXQvdCwLjwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJodi1hcm0tbm90ZSIgaWQ9InZidXNDYXB0dXJlUmVzdWx0Ij7QotC+0LvRjNC60L4g0LjQt9C80LXRgNC10L3QuNC1OiDRgNC10LvQtSDQuCDQqNCY0Jwg0L3QtSDQstC60LvRjtGH0LDRjtGC0YHRjy48L2Rpdj4KICAgICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IGZ1bGwiIGlkPSJ2YnVzUmVzZXRCdG4iPtCh0LHRgNC+0YHQuNGC0Ywg0LrQsNC70LjQsdGA0L7QstC60YMgVmJ1czwvYnV0dG9uPgogICAgICAgICAgPC9kZXRhaWxzPgogICAgICAgIDwvZGl2PgoKICAgICAgICA8ZGl2IGNsYXNzPSJpby1ibG9jayI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJsYWJlbCI+SVBNMTUgSS9PPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJpby1yb3ciPgogICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIGlkPSJwZmNCdG4iPlBGQzogT0ZGPC9idXR0b24+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImJyYWtlLXJvdyI+CiAgICAgICAgICAgIDxpbnB1dCBpZD0iYnJha2VTbGlkZXIiIHR5cGU9InJhbmdlIiBtaW49IjAiIG1heD0iMSIgc3RlcD0iMC4wNSIgdmFsdWU9IjAiIC8+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImJyYWtlLXJlYWRvdXQiIGlkPSJicmFrZVJlYWRvdXQiPkJSSyAwJTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJmYW4tcm93Ij4KICAgICAgICAgICAgPGlucHV0IGlkPSJmYW5TbGlkZXIiIHR5cGU9InJhbmdlIiBtaW49IjAiIG1heD0iMSIgc3RlcD0iMC4wNSIgdmFsdWU9IjAiIC8+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImZhbi1yZWFkb3V0IiBpZD0iZmFuUmVhZG91dCI+RkFOIDAlPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KCiAgICAgICAgCiAgICAgIDwvZGl2PgoKICAgICAgPGRpdiBjbGFzcz0icGFuZWwgc3RhdHVzIj4KICAgICAgICA8aDI+0KHRgtCw0YLRg9GBPC9oMj4KICAgICAgICA8ZGl2IGNsYXNzPSJzdGF0dXMtZ3JpZCI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KHQvtGB0YLQvtGP0L3QuNC1PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJzdGF0ZVZhbCI+U0FGRTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KDQtdC20LjQvDwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0ibW9kZVZhbCI+Rk9DPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QmtC+0L3RgtGD0YAgTnVjbGVvPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJiYWNrZW5kVmFsIj5EVVRZPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QodCy0Y/Qt9GMIFNUTTMyPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJsaW5rVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KjQmNCcPC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJwd21WYWwiPjA8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCh0LrQvtGA0L7RgdGC0Yw8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InNwZWVkVmFsIj4wINC+0LEv0LzQuNC9PC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj7QqNC40L3QsCBEQzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0idmRjVmFsIj4wLjAgVjwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0KDQsNC00LjQsNGC0L7RgCBJUE08L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InRlbXBWYWwiPi0tPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj5JYS9JYi9JYzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iY3VyclZhbCI+MCAvIDAgLyAwIEE8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPlBoYXNlIG1lYXMgQS9CL0M8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9InBoYXNlVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+SWQg0LfQsNC00LDQvdC+PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtdmFsdWUiIGlkPSJpZFJlZlZhbCI+MC4wMCBBPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLWxhYmVsIj5NSUMg0Y3QutC+0L3QvtC80LjRjzwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0ibWljU2F2ZVZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPlBGQy9CUks8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImlvVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC1sYWJlbCI+0JLQtdC90YLQuNC70Y/RgtC+0YA8L2Rpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZC12YWx1ZSIgaWQ9ImZhblZhbCI+LS08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNhcmQtbGFiZWwiPtCe0LHRgNCw0YLQvdCw0Y8g0YHQstGP0LfRjDwvZGl2PgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkLXZhbHVlIiBpZD0iZW5jVmFsIj4tLTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0ic3RhdHVzLWZvb3RlciI+CiAgICAgICAgICA8c3BhbiBpZD0ibGFzdFVwZGF0ZSI+0J3QtdGCINC00LDQvdC90YvRhTwvc3Bhbj4KICAgICAgICAgIDxidXR0b24gaWQ9ImJraW5UcmFjZUxvYWQiIGNsYXNzPSJidG4gZ2hvc3QiIHR5cGU9ImJ1dHRvbiI+0KHRh9C40YLQsNGC0Ywg0YHQvdC40LzQvtC6IEJLSU48L2J1dHRvbj4KICAgICAgICAgIDxzcGFuIGlkPSJia2luVHJhY2VTdGF0dXMiPtCh0L3QuNC80L7QuiDQv9C+0Y/QstC40YLRgdGPINC/0L7RgdC70LUg0YHRgNCw0LHQsNGC0YvQstCw0L3QuNGPINC30LDRidC40YLRiy48L3NwYW4+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgoKICAgIDxzZWN0aW9uIGNsYXNzPSJwYW5lbCIgaWQ9InJlc2VhcmNoUGFuZWwiPjxoMj7QmNGB0YHQu9C10LTQvtCy0LDRgtC10LvRjNGB0LrQsNGPINGB0LXRgNC40Y88L2gyPjxkaXYgaWQ9InJlc2VhcmNoQWxnb3JpdGhtcyI+0J7QttC40LTQsNC90LjQtSDQv9C+0LTRgtCy0LXRgNC20LTQtdC90LjRjyBOdWNsZW88L2Rpdj48L3NlY3Rpb24+CiAgICA8c2VjdGlvbiBjbGFzcz0icGFuZWwgbG9ncyI+CiAgICAgIDxkaXYgY2xhc3M9ImxvZy1yb3ciPgogICAgICAgIDxzcGFuIGNsYXNzPSJsb2ctdGl0bGUiPtCb0L7Qs9C4PC9zcGFuPgogICAgICAgIDxzZWxlY3QgaWQ9ImxvZ0hvdXJzIj4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9IjEiPjEg0YfQsNGBPC9vcHRpb24+CiAgICAgICAgICA8b3B0aW9uIHZhbHVlPSI2Ij42INGH0LDRgdC+0LI8L29wdGlvbj4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9IjI0IiBzZWxlY3RlZD4yNCDRh9Cw0YHQsDwvb3B0aW9uPgogICAgICAgIDwvc2VsZWN0PgogICAgICAgIDxidXR0b24gaWQ9ImxvZ0Rvd25sb2FkIiBjbGFzcz0iYnRuIGdob3N0IiB0eXBlPSJidXR0b24iPtCh0LrQsNGH0LDRgtGMPC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgPC9zZWN0aW9uPgogIAo8L2RldGFpbHM+CjwvbWFpbj4KCiAgPHNjcmlwdCBzcmM9ImFwcC5qcz91aT0zMDEzLWJvb3QtY2FwdHVyZSI+PC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPgo=')
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
