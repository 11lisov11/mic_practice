#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import select
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Deque, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import termios
except Exception:  # pragma: no cover - Windows/local dev without POSIX TTY
    termios = None

try:
    import msgpack
except Exception:  # pragma: no cover - allow text-only mode without msgpack
    msgpack = None

"""Pure read-only snapshot decoding; embedded into the prepared HMI server."""
import struct as _break_struct

_BREAK_FIELDS = (
    "magic", "schema", "bytes", "tick_ms", "tim_sr", "tim_dier", "tim_bdtr",
    "tim_cnt", "tim_arr", "tim_ccr1", "tim_ccr2", "tim_ccr3", "gpioa_idr",
    "context_valid", "context_tick_ms", "reference_speed_unit", "motor_state",
    "current_faults", "occurred_faults", "vbus_v", "temperature_deci_c",
    "command_sequence", "start_window")


def break_reject_status(kv):
    names=("valid", "code", "ms", "peer_fw", "fresh_off", "bp_status", "pwm", "rsp_age_ms", "good_before")
    result={}
    try:
        for name in names:
            value=int(kv.get("mc_break_reject_"+name, "0"))
            if not 0<=value<=0xffffffff: raise ValueError("reject field outside uint32")
            result["mc_break_reject_"+name]=value
        packet=kv.get("mc_break_reject_packet_hex", "-")
        result["mc_break_reject_packet_hex"]=packet
        reasons={1:"FRAME_CRC",2:"HEADER",3:"PAGE_LAYOUT",4:"PEER_BUILD",5:"NOT_FRESH_OFF",
                 6:"RESERVED",7:"PADDING",8:"DUPLICATE",9:"RECORD_CRC",10:"RECORD_ABI",11:"WINDOW_KIND"}
        code=result["mc_break_reject_code"]
        record_ok=(result["mc_break_reject_valid"]==1 and code in reasons and
            result["mc_break_reject_fresh_off"] in (0,1) and result["mc_break_reject_pwm"] in (0,1) and
            len(packet)==86 and all(c in "0123456789abcdefABCDEF" for c in packet))
        result["mc_break_reject_record_valid"]=int(record_ok)
        result["mc_break_reject_reason"]=reasons[code] if record_ok else "UNAVAILABLE"
        return result
    except (ValueError,TypeError):
        return {"mc_break_reject_record_valid":0,"mc_break_reject_reason":"INVALID_METADATA"}

def break_wire_status(kv):
    records = []
    for kind in (0, 1):
        item = {"kind": "first_since_boot" if kind == 0 else "first_start_window",
                "available": False, "captured": False}
        try:
            text = kv.get(f"mc_break{kind}_hex", "")
            age = int(kv.get(f"mc_break{kind}_age_ms", "-1"))
            peer_age = int(kv.get("bp_age_ms", "999999"))
            peer = int(kv.get("bp_fw_build", "0"))
            if not text or text == "-":
                item["reason"] = "not_received"
            elif len(text) != 184 or any(c not in "0123456789abcdefABCDEF" for c in text):
                item["reason"] = "invalid_hex"
            elif peer not in (2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493, 2026101412, 2026101414, 2026101502, 2026101504, 2026101506, 2026101702, 2026101806, 2026101808, 2026101810, 2026101812, 2026102002, 2026102102, 2026102104, 2026102402, 2026102406, 2026102408, 2026102410, 2026102412, 2026102502, 2026102506, 2026102508, 2026102510, 2026102602, 2026102604, 2026102702, 2026102704, 2026102706, 2026102708,2026102710,2026102812,2026102902,2026103016) or not 0 <= peer_age < 300 or not 0 <= age <= 0xFFFFFFFF:
                item["reason"] = "invalid_age"
            else:
                data = bytes.fromhex(text)
                raw = dict(zip(_BREAK_FIELDS, _break_struct.unpack("<23I", data)))
                item["age_ms"] = age
                if not any(data):
                    item.update(available=True, reason="no_recorded_break")
                elif (raw["magic"] != 0x314B5242 or raw["schema"] != 2 or raw["bytes"] != 92
                      or raw["context_valid"] not in (0, 1) or raw["start_window"] not in (0, 1)
                      or not raw["tim_sr"] & 0x180 or (kind == 1 and raw["start_window"] != 1)):
                    item["reason"] = "invalid_record"
                else:
                    for field in ("reference_speed_unit", "temperature_deci_c"):
                        if raw[field] & (1 << 31):
                            raw[field] -= 1 << 32
                    context = None
                    if raw["context_valid"]:
                        context = {k: raw[k] for k in _BREAK_FIELDS[14:22]}
                        context["age_at_irq_ms"] = (raw["tick_ms"] - raw["context_tick_ms"]) & 0xFFFFFFFF
                        context["reference_electrical_hz"] = raw["reference_speed_unit"] / 10.0
                        context["temperature_c"] = raw["temperature_deci_c"] / 10.0
                    raw_start_window = bool(raw["start_window"])
                    context_was_running = bool(context and context["motor_state"] == 6)
                    item.update(available=True, captured=True, reason="recorded", raw=raw,
                        event={"bif": bool(raw["tim_sr"] & 0x80), "b2if": bool(raw["tim_sr"] & 0x100),
                               "pa6_high_at_irq": bool(raw["gpioa_idr"] & 0x40),
                               "bke_at_irq": bool(raw["tim_bdtr"] & 0x1000),
                               "moe_at_irq": bool(raw["tim_bdtr"] & 0x8000),
                               "during_start_request_window": raw_start_window and not context_was_running,
                               "start_window_flag_raw": raw_start_window,
                               "start_window_flag_stale_after_run": raw_start_window and context_was_running},
                        cached_context=context)
        except (ValueError, TypeError, OverflowError):
            item["reason"] = "invalid_metadata"
        records.append(item)
    return {"mc_break_snapshots": records,
            "mc_break_transport": "passive_off_only_v1",
            "mc_break_limitations": ["Not live telemetry: delivery occurs only with outputs off",
                "Reference frequency is not measured rotor speed; context is cached",
                "PA6 is sampled at IRQ, not the electrical edge; pulse duration is unknown",
                "J4 voltage and qualified phase current are not measured",
                "Cannot uniquely identify overcurrent, undervoltage, or interference"]}


def uart_reject_status(data):
    """Read-only frozen command-receiver evidence; never authorizes a command."""
    try:
        if _as_int(data or {},'mc_fw_build',0) not in (2026101806,2026101808,2026101810,2026101812,2026102002,2026102102,2026102104,2026102402,2026102406,2026102408,2026102410,2026102412,2026102502,2026102506,2026102508,2026102510,2026102602,2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
            return {'available':False,'reason':'wrong_peer_build'}
        text=data.get('mc_uart_reject_hex','-')
        if text=='-':return {'available':False,'reason':'not_received'}
        if len(text)!=640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available':False,'reason':'invalid_hex'}
        raw=bytes.fromhex(text);h=_break_struct.unpack_from('<8I',raw)
        if h[:4]!=(0x31545255,1,320,_as_int(data,'mc_fw_build',0)) or h[4]>1 or h[5]!=1 or h[7]:
            return {'available':False,'reason':'invalid_record'}
        records=[]
        def crc32c(b):
            crc=0xffffffff
            for x in b:
                crc^=x
                for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
            return crc^0xffffffff
        for k in range(2):
            q=raw[32+144*k:32+144*(k+1)]
            if not h[4+k]:
                if any(q):return {'available':False,'reason':'invalid_record'}
                records.append(None);continue
            m=_break_struct.unpack_from('<14I',q);n=m[2]
            if not 2<=m[1]<=8 or n>43 or m[3]>43 or m[4]>15 or m[5] not in range(256) and m[5]!=0xffffffff or m[6]>2 or m[7]>2 or m[11]>3:
                return {'available':False,'reason':'invalid_record'}
            b=q[56:56+n];marks=q[100:100+n]
            if any(q[56+n:100]) or any(q[100+n:]) or any(x&~15 for x in marks):
                return {'available':False,'reason':'invalid_record'}
            if n==43:
                if m[12]!=int.from_bytes(b[39:43],'little') or m[13]!=crc32c(b[:39]):
                    return {'available':False,'reason':'invalid_record'}
            elif m[12] or m[13]:return {'available':False,'reason':'invalid_record'}
            records.append(dict(tick_ms=m[0],reason_code=m[1],length=n,speculative_prefix=m[3],
                uart_flags=m[4],last_committed_sequence=None if m[5]==0xffffffff else m[5],
                budget_used=m[6],recoverable_losses=m[7],dropped_before=m[8],last_valid_ms=m[9],
                candidate_started_ms=m[10],receiver_flags=m[11],raw_hex=b.hex(),marks_hex=marks.hex(),
                full_frame_crc_matches=None if n!=43 else m[12]==m[13],
                stored_crc=m[12] if n==43 else None,calculated_crc=m[13] if n==43 else None))
        fatal=records[1]
        if fatal['length']==43:
            kind='CRC полного кадра совпал' if fatal['full_frame_crc_matches'] else 'CRC полного кадра не совпал'
        else:kind=f"неполный кандидат/синхронизация ({fatal['length']} байт)"
        summary=f"UART Uno→Nucleo: {kind}; причина {fatal['reason_code']}, бюджет {fatal['budget_used']}/2. Сырые байты сохранены."
        return dict(available=True,reason='saved_command_reject',schema=1,records=records,
            speculative_prefix_expiries=h[6],summary_ru=summary,
            physical_cause_identified=False,limitations=['Parser observation times, not electrical edge timestamps',
            'Only the latest recovered rejection and first fatal rejection are retained until peer reset'])
    except (ValueError,TypeError,OverflowError):return {'available':False,'reason':'invalid_record'}


"""Observational reset decoding. No reset, acknowledgement or motor commands."""
def _boot_linux_id():
    try:
        with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as stream:
            value=stream.read().strip()
        return value if len(value)==36 else None
    except OSError:
        return None


BOOT_LINUX_ID=_boot_linux_id()


def boot_wire_status(kv):
    result={'linux_boot_id':BOOT_LINUX_ID,'native_boot':{'available':False,'reason':'not_received'}}
    try:
        raw=str(kv.get('mc_boot_packet_hex','-'))
        if raw=='-':return result
        p=bytes.fromhex(raw)
        def crc(data):
            c=0xffffffff
            for byte in data:
                c^=byte
                for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
            return c^0xffffffff
        def u(offset):return int.from_bytes(p[offset:offset+4],'little')
        fw=int(kv.get('bp_fw_build',kv.get('mc_fw_build','0')))
        if len(p)!=43 or p[:6]!=bytes.fromhex('55aae9010100') or p[38] or crc(p[:39])!=u(39) or u(6)!=fw:
            raise ValueError('invalid_frame_or_peer')
        seq,csr,previous,flags,tag,record_crc,tick=[u(i) for i in range(10,38,4)]
        words=[0x31525442,fw,seq,csr,previous,flags,tag]
        if not seq or flags&~15 or crc(b''.join(v.to_bytes(4,'little') for v in words))!=record_crc:
            raise ValueError('invalid_early_record')
        names=[name for mask,name in ((1<<25,'OPTION_BYTES'),(1<<26,'NRST_FLAG'),
              (1<<27,'POWER_ON_OR_BROWNOUT'),(1<<28,'SOFTWARE'),(1<<29,'IWDG'),
              (1<<30,'WWDG'),(1<<31,'LOW_POWER')) if csr&mask]
        fresh=str(kv.get('mc_boot_fresh','0'))=='1'
        continuity=bool(flags&1 and flags&2 and not csr&(1<<27))
        labels={'OPTION_BYTES':'загрузка option bytes','NRST_FLAG':'флаг NRST',
                'POWER_ON_OR_BROWNOUT':'подача питания или просадка напряжения',
                'SOFTWARE':'программный сброс','IWDG':'IWDG','WWDG':'WWDG','LOW_POWER':'low-power reset'}
        text=', '.join(labels[n] for n in names) or 'флаги причины отсутствуют'
        if tag==0x4D435031 and csr&(1<<28):text+='; команда MCSDK SW_RESET'
        if not continuity:text+='; предыдущая история не подтверждена'
        if not fresh:text+='; сохранённая запись, не свежий статус'
        result.update(mc_boot_packet_hex=raw,mc_boot_fresh=int(fresh),
            native_boot=dict(available=True,fresh=fresh,firmware=fw,
            retained_sequence=seq,sequence_is_power_cycle_persistent=False,
            csr_raw=csr,previous_csr_raw=previous,flags=flags,causes=names,
            previous_flags_cleared=bool(flags&2),current_flags_cleared=bool(flags&4),
            previous_boot_continuity=continuity,software_request_tag=tag,
            early_record_crc=record_crc,native_tick_ms=tick,summary_ru=text,
            exact_physical_cause_identified=False,
            limitation='BOR не отличает включение от просадки; NRST может сопутствовать другим причинам; первая запись может содержать накопленные флаги.'))
    except (ValueError,TypeError,OverflowError):
        result['native_boot']={'available':False,'reason':'invalid_record'}
    return result


def foc_runtime_status(kv):
    """Decode measured lower/upper timing bounds and immutable first fault."""
    names = {1: 'нет согласованного отсчёта АЦП', 2: 'отсчёт АЦП недействителен',
             3: 'превышен возраст отсчёта АЦП', 4: 'превышен возраст оценки наблюдателя',
             5: 'слишком длинный интервал окна наблюдателя', 6: 'превышен дедлайн быстрого расчёта',
             7: 'ошибка регулятора', 8: 'ошибка вычисления наблюдателя', 9: 'ошибка регулярного АЦП'}
    try:
        if int(kv.get('foc_runtime_valid', '0')) != 1:
            return {'foc_runtime': {'available': False, 'reason': 'not_received_or_stale'}}
        w = [int(kv.get('foc_runtime_w'+str(i), '0')) for i in range(42)]
        if not all(0 <= x <= 0xffffffff for x in w):
            raise ValueError('counter outside uint32')
        if w[1] > w[0] or w[0]-w[1] != w[2]:
            raise ValueError('inconsistent wall/IRQ/CPU counters')
        flags = int(kv.get('foc_runtime_flags', '0'))
        if flags not in (0, 1, 2, 3):
            raise ValueError('invalid runtime flags')
        fault = None
        if flags & 1:
            reason, code, at, adc, est, stamp, obs_begin = w[14:21]
            if reason not in names:
                raise ValueError('unknown frozen reason')
            fault = dict(reason_code=reason, reason_ru=names[reason], algorithm_fault=code,
                         at_cycles=at, adc_cycles=adc, estimate_cycles=est, bin_cycles=stamp,
                         observer_begin_cycles=obs_begin, adc_age_us=((at-adc)&0xffffffff)/170,
                         estimate_age_us=((at-est)&0xffffffff)/170,
                         window_dt_us=((stamp-est)&0xffffffff)/170,
                         last_observer_wall_us=w[21]/170, last_irq_body_lower_us=w[22]/170,
                         last_cpu_upper_us=w[23]/170, adc_sequence=w[24], sample_flags=w[25],
                         observer_inflight=bool(w[25]&8),
                         fast_elapsed_us=w[26]/170, observer_steps=w[27])
        if flags & 1 and w[14] == 9:
            reasons = {1: 'неподдерживаемая конфигурация АЦП', 2: 'нет готового отсчёта',
                       3: 'возраст отсчёта достиг 1 мс', 4: 'не получен согласованный снимок',
                       5: 'нет EOC предыдущей конверсии', 6: 'АЦП занят перед запуском',
                       7: 'неверный дескриптор канала'}
            sub, ident = w[15], w[18]
            if sub not in reasons or ident not in (0, 1) and sub != 7:
                raise ValueError('invalid regular ADC fault')
            fault = dict(reason_code=9, reason_ru='АЦП: '+reasons[sub], algorithm_fault=0,
                         at_cycles=w[16], regular_adc=dict(reason_code=sub, reason_ru=reasons[sub],
                         id=ident, channel={0:2, 1:8}.get(ident), at_cycles=w[16], stamp_cycles=w[17],
                         age_us=w[19]/170, timer_cnt=w[20], timer_cr1=w[21], adc_isr=w[22],
                         adc_cr=w[23], adc_sqr1=w[24], pending_id=w[25], flags=w[26], ipsr=w[27],
                         age_valid_for_expiry=sub==3))
        if fault is not None:
            if w[28] != 1 or w[29] not in range(6) or w[32] not in (0,1) or w[41] not in (0,1):
                raise ValueError('invalid observer publication record')
            fault['publication'] = dict(schema=w[28],stage=w[29],
                stage_name=['idle','compute','copy_inactive','committed','accounting','aborted'][w[29]],
                done_mark_cycles=w[30],commit_mark_cycles=w[31],published_index=w[32],
                slot_stamps=w[33:35],input_bin_cycles=w[35],foreground_stamp=w[36],
                measured_steps=w[37],math_steps=w[38],voltage_bin_cycles=w[39],
                voltage_sequence=w[40],index_after=w[41],index_stable=w[32]==w[41],
                limitation='Diagnostic marks, not an exemption from the unchanged2ms age limit')
        return {'foc_runtime': dict(available=True, observer_measured=w[0]>0,
                    source='OFF_synthetic_CPU_probe' if flags & 2 else 'runtime_observer',
                    observer_wall_us=w[0]/170, irq_body_lower_us=w[1]/170,
                    cpu_upper_us=w[2]/170, irq_root_count=w[3],
                    max_wall_us=w[4]/170, max_irq_body_lower_us=w[5]/170,
                    max_cpu_upper_us=w[6]/170, window_queue_us=w[7]/170,
                    input_age_us=w[8]/170, result_age_us=w[9]/170,
                    max_window_queue_us=w[10]/170, max_result_age_us=w[11]/170,
                    observer_steps=w[12], meter_errors=w[13], first_fault=fault,
                    limitation='CPU upper includes exception entry/return and profiler edge overhead; IRQ body time is a lower bound.')}
    except (TypeError, ValueError, OverflowError):
        return {'foc_runtime': {'available': False, 'reason': 'invalid_counters'}}


def sd_live_status(data):
    """A fresh GPIO observation is independent of the frozen first waveform."""
    unknown = {'available': False, 'level': None, 'summary_ru': 'Текущий SD: нет измерения'}
    try:
        if int(data.get('mc_fw_build', 0)) not in (2026101808,2026101810,2026101812,2026102002,2026102102,2026102104,2026102402,2026102406,2026102408,2026102410,2026102412,2026102502,2026102506,2026102508,2026102510,2026102602,2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
            return dict(unknown, reason='unsupported_peer')
        age = int(data.get('mc_age_ms', data.get('bp_age_ms', 999999)))
        if not 0 <= age < 300:
            return dict(unknown, reason='stale_peer')
        flags = int(data.get('bp_temp_flags', -1))
        if not 0 <= flags <= 255 or not flags & 4:
            return dict(unknown, reason='missing_validity')
        high = bool(flags & 8)
        config_ok = bool(flags & 128)
        level = 'HIGH' if high else 'LOW'
        summary = f'SD сейчас {level}: ' + ('защита отпущена' if high else 'вход защиты активен')
        if not config_ok:
            summary += '; конфигурация PA6/BKIN отличается от ожидаемой'
        return dict(available=True, reason='observed', level=level, age_ms=age,
            break_irq_enabled=bool(flags & 16), capture_running=bool(flags & 32),
            first_record_ready=bool(flags & 64), config_ok=config_ok,
            summary_ru=summary,
            limitation='Уровень на момент ответа UART; краткие импульсы между ответами здесь не измеряются')
    except (TypeError, ValueError, OverflowError):
        return dict(unknown, reason='invalid_metadata')


def dual_sd_wave_status(data):
    """Schema 5: two logic levels from each same GPIOA DMA read, not analog SD.

    A stored record does not prove live wiring, physical edge timing, or that
    an IPM itself generated a LOW. No cause is inferred from coincidence.
    """
    try:
        if _as_int(data or {}, 'mc_fw_build', 0) not in (2026102102,2026102104,2026102402,2026102406,2026102408,2026102410,2026102412,2026102502,2026102506,2026102508,2026102510,2026102602,2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
            return {'available': False, 'reason': 'wrong_peer_build'}
        text = data.get('mc_break_wave_hex', '')
        age = _as_int(data, 'mc_break_wave_age_ms', -1)
        if not text or text == '-': return {'available': False, 'reason': 'not_received'}
        if len(text) != 640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available': False, 'reason': 'invalid_hex'}
        if not 0 <= age <= 0xffffffff: return {'available': False, 'reason': 'invalid_age'}
        raw = bytes.fromhex(text)
        magic, schema, size, tick, period, flags, trigger, samples, n, mask, limit, post, pre, dma, remaining, config = _break_struct.unpack_from('<16I', raw)
        invalid = lambda: {'available': False, 'reason': 'invalid_record'}
        if (magic != 0x314e4b42 or schema != 5 or size != 320 or period != 200 or
            not flags & 1 or flags & ~633 or trigger > 2048 or samples > trigger + 500000 or
            n > 32 or mask != 0x50 or limit != 500000 or post != 320 or pre != 2048 or
            dma & ~15 or remaining > 8192 or config != 1 or flags & 512 and flags & 8): return invalid()
        runs = []; total = 0; previous = 4; quiet = 0
        for i in range(32):
            state, count = _break_struct.unpack_from('<2I', raw, 64 + 8*i)
            if i >= n:
                if state or count: return invalid()
                continue
            if state > 3 or not count or state == previous or count > samples-total: return invalid()
            runs.append({'state': state, 'pa6': state & 1, 'tp23_pa4': (state >> 1) & 1,
                         'samples': count, 'from_us': (total-trigger)*.2,
                         'to_us': (total+count-trigger)*.2})
            total += count; previous = state; quiet = count if state == 3 else 0
        if total != samples: return invalid()
        if flags & 512 and (samples < trigger+321 or quiet < 321): return invalid()
        errors = bool(flags & (16|32|64))
        if flags & 8 and not errors and samples != trigger+limit: return invalid()
        if not flags & (512|8|16|32|64): return invalid()
        channels = {}
        for name, bit in (('pa6_bkin', 0), ('tp23_pa4', 1)):
            intervals = []; position = 0; start = None
            for run in runs:
                high = (run['state'] >> bit) & 1
                if not high and start is None: start = position
                if high and start is not None:
                    intervals.append((start, position)); start = None
                position += run['samples']
            if start is not None: intervals.append((start, None))
            lows = []
            for begin, end in intervals:
                complete = begin != 0 and end is not None and not errors
                lows.append({'fall_sample': begin, 'rise_sample': end,
                    'from_us': (begin-trigger)*.2, 'to_us': None if end is None else (end-trigger)*.2,
                    'left_censored': begin == 0, 'right_censored': end is None,
                    'pulse_complete': complete,
                    'width_samples': end-begin if complete else None,
                    'width_us': (end-begin)*.2 if complete else None})
            preceding = [x for x in lows if x['fall_sample'] <= trigger]
            selected = preceding[-1] if preceding else (lows[0] if lows else None)
            channels[name] = {'low_intervals': lows, 'selected_pulse': selected,
                              'low_observed': bool(lows)}
        mismatch = sum(r['samples'] for r in runs if r['state'] in (1, 2))
        if errors: reason = 'dma_error' if flags & 16 else 'sampling_overrun' if flags & 32 else 'run_capacity_exceeded'
        elif flags & 8: reason = 'timeout_incomplete'
        else: reason = 'complete_window'
        def describe(name, title):
            pulse = channels[name]['selected_pulse']
            if pulse is None: return title + ': LOW не обнаружен'
            if not pulse['pulse_complete']: return title + ': LOW записан неполно; длительность не подтверждена'
            return title + f": LOW {pulse['width_us']:.1f} мкс"
        summary = describe('pa6_bkin', 'PA6/BKIN') + '; ' + describe('tp23_pa4', 'TP23→PA4')
        summary += f'; несовпадение уровней: {mismatch} отсч.'
        if errors or flags & 8: summary += '; окно неполное: ' + reason
        return {'available': True, 'reason': reason, 'schema': 5, 'stored_record': True,
            'event_tick_ms': tick, 'age_since_delivery_ms': age,
            'live_peer_fresh': 0 <= _as_int(data, 'mc_age_ms', 999999) < 300,
            'live_sd': sd_live_status(data), 'sample_period_us': .2, 'sample_rate_hz': 5000000,
            'trigger_index': trigger, 'sample_count': samples, 'runs': runs, 'channels': channels,
            'mismatch_samples': mismatch, 'mismatch_us': mismatch*.2,
            'post_complete': bool(flags & 512) and not errors, 'timeout': bool(flags & 8),
            'dma_error': bool(flags & 16), 'sampling_overrun': bool(flags & 32),
            'run_overflow': bool(flags & 64), 'flags': flags, 'dma_flags_raw': dma,
            'dma_remaining': remaining, 'input_configuration_verified': True,
            'summary_ru': summary,
            'trace_reference': 'Both bits from one GPIOA IDR DMA read; relative to Break IRQ publication',
            'limitations': ['Requested sample step 200 ns; hardware timing is not electrically qualified',
                'TP23 requires external wiring to PA4; firmware cannot detect an absent or wrong wire',
                'A LOW on both inputs does not prove intrinsic IPM fault; common-reference noise remains possible',
                '32 joint runs maximum; overflow and missing edges never imply a complete pulse',
                'First Break since boot; STOP/CLEAR do not overwrite evidence']}
    except (ValueError, TypeError, OverflowError):
        return {'available': False, 'reason': 'invalid_metadata'}


def bkin_wave_status(data):
    if _as_int(data or {}, "mc_fw_build", 0) in (2026102102,2026102104,2026102402,2026102406,2026102408,2026102410,2026102412,2026102502,2026102506,2026102508,2026102510,2026102602,2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
        return dual_sd_wave_status(data)
    """Schema 4: lossless runs of DMA samples, including post-trigger recovery.

    Immutable saved evidence is distinct from freshness of the live peer.
    Neither an IRQ timestamp nor an unfinished LOW is a measured pulse width.
    """
    unknown=0xffffffff
    try:
        if _as_int(data or {}, 'mc_fw_build', 0) not in (2026101806,2026101808,2026101810,2026101812,2026102002,2026102102,2026102104,2026102402,2026102406,2026102408,2026102410,2026102412,2026102502,2026102506,2026102508,2026102510,2026102602,2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
            return {'available':False,'reason':'wrong_peer_build'}
        text=data.get('mc_break_wave_hex','')
        age=_as_int(data,'mc_break_wave_age_ms',-1)
        if not text or text=='-': return {'available':False,'reason':'not_received'}
        if len(text)!=640 or any(c not in '0123456789abcdefABCDEF' for c in text):
            return {'available':False,'reason':'invalid_hex'}
        if not 0<=age<=unknown: return {'available':False,'reason':'invalid_age'}
        raw=bytes.fromhex(text)
        h=_break_struct.unpack_from('<16I',raw)
        magic,schema,size,tick,period,flags,trigger,samples,n,fall,rise,width,limit,dma,remaining,reserved=h
        invalid=lambda: {'available':False,'reason':'invalid_record'}
        if (magic!=0x314e4b42 or schema!=4 or size!=320 or period!=200 or
            not flags&1 or flags&~1023 or trigger>2048 or samples>trigger+500000 or
            n>32 or limit!=500000 or dma&~15 or remaining>8192 or reserved or
            flags&512 and flags&8 or flags&2 and flags&128): return invalid()
        runs=[]; total=0; previous=2; ef=er=unknown
        for i in range(32):
            high,count=_break_struct.unpack_from('<2I',raw,64+8*i)
            if i>=n:
                if high or count: return invalid()
                continue
            if high>1 or not count or high==previous or count>samples-total: return invalid()
            if not high and (ef==unknown or total<=trigger): ef,er=total,unknown
            elif high and ef!=unknown and er==unknown: er=total
            runs.append({'level':high,'samples':count,'from_us':(total-trigger)/5,'to_us':(total+count-trigger)/5})
            total+=count; previous=high
        if (total!=samples or fall!=ef or rise!=er or bool(flags&4)!=(rise!=unknown) or
            bool(flags&128)!=(fall==0) or bool(flags&2)!=(fall not in (unknown,0))): return invalid()
        errors=bool(flags&(16|32|64))
        expected_width=rise-fall if fall not in (unknown,0) and rise!=unknown and not errors else unknown
        if width!=expected_width: return invalid()
        if flags&512:
            if (samples<trigger+321 or bool(flags&256)!=(fall==unknown) or
                fall!=unknown and (rise==unknown or samples<rise+321)): return invalid()
        elif flags&256: return invalid()
        if not flags&(512|8|16|32|64): return invalid()
        complete=width!=unknown and not errors
        if errors:
            reason='dma_error' if flags&16 else 'sampling_overrun' if flags&32 else 'run_capacity_exceeded'
            summary='Запись PA6 неполная: ошибка DMA / потеря отсчётов / переполнение переходов. Длительность не подтверждена.'
        elif flags&256:
            reason='low_not_observed'
            summary='Break сохранён, LOW на PA6 не попал в отсчёты. Длительность неизвестна (разрешение 0,2 мкс).'
        elif flags&8:
            reason='timeout_low_unfinished' if rise==unknown else 'timeout_post_incomplete'
            summary=('В сохранённом окне PA6 оставался LOW до конца 100 мс. Текущий уровень этим не измерен; полная длительность неизвестна.'
                if rise==unknown else f'Оба фронта PA6 записаны: LOW {width/5:g} мкс. Окно 100 мс закончилось до завершения участка после импульса.')
        elif flags&128:
            reason='missing_falling_edge'
            summary='Возврат PA6 в HIGH записан, но начало LOW осталось за границей записи. Полная длительность неизвестна.'
        else:
            reason='complete_pulse'
            summary=f'Импульс PA6 записан целиком: LOW {width/5:g} мкс, оба фронта и участок после возврата HIGH. Разрешение 0,2 мкс.'
        peer_age=_as_int(data,'mc_age_ms',_as_int(data,'bp_age_ms',999999))
        return {'available':True,'reason':reason,'schema':4,'stored_record':True,
            'age_since_delivery_ms':age,'live_peer_fresh':0<=peer_age<300,
            'event_tick_ms':tick,'sample_period_us':0.2,'sample_rate_hz':5000000,
            'live_sd':sd_live_status(data),
            'sample_count':samples,'trigger_index':trigger,'runs':runs,
            'pulse_complete':complete,'pulse_width_us':None if width==unknown else width/5,
            'post_complete':bool(flags&512),
            'falling_edge_us':None if not flags&2 else (fall-trigger)/5,
            'rising_edge_us':None if rise==unknown else (rise-trigger)/5,
            'left_censored':bool(flags&128),'right_censored':rise==unknown and fall!=unknown,
            'timeout':bool(flags&8),'dma_error':bool(flags&16),'sampling_overrun':bool(flags&32),
            'run_overflow':bool(flags&64),'flags':flags,'dma_flags_raw':dma,
            'dma_remaining':remaining,'summary_ru':summary,
            'trace_reference':'200-ns DMA sample grid relative to Break IRQ publication; IRQ latency is not an electrical-edge timestamp',
            'limitations':['Pulses shorter than 0.2 us may be missed; edge positions are quantized to the sample grid',
                'First event since boot; STOP/CLEAR do not overwrite it',
                'Requested DMA rate requires hardware throughput validation; DMA flags cannot detect every missed timer request',
                'Only PA6/SD is measured; width alone cannot uniquely identify overcurrent, driver undervoltage, or interference']}
    except (ValueError,TypeError,OverflowError):
        return {'available':False,'reason':'invalid_metadata'}


STATE_NAMES = {
    0: "SAFE",
    1: "VF_RUN",
    2: "FOC_ALIGN",
    3: "FOC_RUN",
    4: "FAULT",
}
MODE_NAMES = {
    0: "VF",
    1: "FOC",
    2: "MIC",
    3: "DIAG",
    4: "DUTY",
}
STATE_CODES = {v: k for k, v in STATE_NAMES.items()}
MODE_CODES = {v: k for k, v in MODE_NAMES.items()}
MC_MODE_DIAG = 1
MC_MODE_DUTY = 2
MC_CAP_VF = 0x01
MC_CAP_FOC = 0x02
MC_CAP_MIC = 0x04
DEFAULT_REMOTEOCD = "/home/arduino/.arduino15/packages/arduino/tools/remoteocd/0.0.4-rc.4/remoteocd"
DEFAULT_REMOTEOCD_CFG = os.path.join(os.path.dirname(__file__), "flash_unoq_sketch_090.cfg")
DEFAULT_CMD_GUARD_MAX_VDC = 60.0
CMD_GUARD_MAX_AGE_MS = 1000.0
# Independent raw-ADC gate mirrored from the motor-controller firmware. The raw check does
# not trust the scaled Vbus field, but its calibration points must stay in sync
# with the firmware and are enforced by firmware_config_safety_check.py.
VBUS_RAW_MIN_VALID = 1
VBUS_RAW_MAX_VALID = 4094
VBUS_RAW_ZERO_CAL = 1966
VBUS_RAW_CAL = 3459
VBUS_RAW_CAL_V = 315.0
# Legacy compile-time override. Production remains False; an authenticated,
# persisted two-point verification is the normal way to unlock HV arming.
VBUS_HV_CALIBRATION_VALID = False
VBUS_RAW_WINDOW_MARGIN_V = 5.0
VBUS_RAW_ZERO_LOW_MARGIN = 128
DEFAULT_VBUS_CALIBRATION_FILE = os.path.expanduser("~/.config/mic-ai/vbus_calibration.json")
VBUS_CAL_ZERO_MAX_METER_V = 2.0
VBUS_CAL_ZERO_MAX_REPORTED_V = 5.0
VBUS_CAL_HV_MIN_METER_V = 250.0
VBUS_CAL_HV_MAX_METER_V = 360.0
VBUS_CAL_HV_MAX_ERROR_PERCENT = 3.0
VBUS_CAL_HV_MAX_ERROR_FLOOR_V = 5.0
VBUS_CAL_ZERO_MAX_STD_V = 0.5
VBUS_CAL_HV_MAX_STD_FLOOR_V = 1.0
VBUS_CAL_HV_MAX_STD_PERCENT = 0.5
VBUS_CAL_CAPTURE_SAMPLES = 20
DEFAULT_START_RUNLIMIT_SEC = 15.0
DEFAULT_HV_ARM_TTL_SEC = 30.0
DEFAULT_HV_ARM_MIN_VDC = 100.0
DEFAULT_HV_ARM_MAX_VDC = 400.0
DEFAULT_HV_ARM_CONFIRM = "ARM 310V"
DEFAULT_HV_ARM_MIN_TEMP_C = -20.0
DEFAULT_HV_ARM_MAX_TEMP_C = 90.0
DEFAULT_LV_ARM_TTL_SEC = 30.0
DEFAULT_LV_ARM_MIN_VDC = 0.0
DEFAULT_LV_ARM_MAX_VDC = 10.0
DEFAULT_LV_ARM_CONFIRM = "ARM LV HV OFF"
DEFAULT_LV_START_RUNLIMIT_SEC = 3.0
DEFAULT_OPERATOR_HEARTBEAT_TIMEOUT_SEC = 3.0
DEFAULT_RELAY_CONFIRM_TIMEOUT_SEC = 1.5
DEFAULT_RELAY_SETTLE_SEC = 0.35
DEFAULT_RUN_CONFIRM_TIMEOUT_SEC = 6.0
ARM_PROFILE_HV = "hv"
ARM_PROFILE_LV = "lv"
HV_RUNTIME_BAD_BURST_LIMIT = 3
HV_RUNTIME_BAD_WINDOW_SEC = 1.0
UART_V3_TRIAL_PAIR = (2026101007, 2026101006)
UART_V3_TRIAL_IMAGES = {
    "production_uno": "b521f692621f9374338b59805d0f0a233e086dfe802c6f9ec28e768b8e4a1e9b",
    "production_nucleo": "20530ef90893b8cdb074739e3b8fd02d0bb0c478016ab291e036192c4a784479",
}
UART_V3_SENDER_TRIAL_PAIR = (2026101008, 2026101006)
UART_V3_SENDER_TRIAL_IMAGES = {
    "production_uno": "1ebb68a6bf9180643ec471e240b4ab125c51866f8da1d69c974421bbd403708a",
    "production_nucleo": UART_V3_TRIAL_IMAGES["production_nucleo"],
}
UART_V3_TRIAL_CASES = ("carrier_5", "carrier_20", "STOP", "ESTOP", "FREQ_ZERO",
                      "RUNLIMIT", "ACTIVE_RPC", "TIM1_BREAK")
COAST30_PROFILE = "vf_30s_50hz_coast"


# Embedded only in the reviewed HMI for the installed 1108/1102 pair.
BOOT_TRIAL_PAIR = (2026101205, 2026101204)
BOOT_TRIAL_IMAGES = {'production_uno': 'afd0c72fc33c1519d9a85b6fd43356057a66048f82d20e1ebbbd56cd5e714714', 'production_nucleo': 'f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949'}
BOOT_TRIAL_SCHEMA = "mic_ai.powered_trial.local_stop1204.v1"
BOOT_TRIAL_EVIDENCE = {
    "pwm", "source_audit", "uno_install", "nucleo_install", "offline",
    "idle_wifi", "autonomous", "sd_sample", "calibration", "local_stop",
}


# Embedded into the HMI only with the exact reviewed retained evidence hashes.
LOCAL_STOP_FIXTURE_SCHEMA = "mic_ai.powered_trial.local_stop_fixture_delta.v1"
LOCAL_STOP_FIXTURE_PAIR = (2026101298, 2026101299)
LOCAL_STOP_FIXTURE_IMAGES = {'fixture_uno': '8b2cb321a52a44af07613c04fd96aabf1a2467b7081fb859344dff8236950428', 'fixture_nucleo': 'bc0c3dbfee861c2d4f68a4d5b59f20b44bec0cd2ed062046da489d1bcb633cd9'}
LOCAL_STOP_RETAINED_EVIDENCE = {'fixture_pwm': 'aec92987b878e8b963bb2f4c50589d4334edea9d40fc6fbf9702e93ba59e6130', 'fixture_capture': 'abade1d935e0f508bbd4d8c87d6f53f833e4c9728f8e0d3eaebe89e08be489e4', 'fixture_code': '1a1c7041f43a4367a2cc125cd2826ce0a4313b212aeb0df803142a20c287895f', 'fixture_selftest': '1f4778d569b0af7ad328b76b8e98820db86a9d12d3ca1beb41aaf7479da90ecb', 'production_idle': 'f34a87de8a052cc194b81c1b41e4c0ec30c9c076995dcbe413c87d7965b0d20b', 'production_restore_nucleo': 'f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949', 'production_restore_uno': 'ca91b8ade3b0cc3e17d8bfcbb466099e582cf9bc96cad3ca1347f082f4f186ee', 'baseline_offline': '5245d75f162c490cd8c1356256296280f295ab9c87a91ac0282a33edd368f4a4', 'calibration_contract': '6b4777039107dcfc2a3badc1d649b7c554b12b469642d0002937af1f67640464', 'sd_sample': '46929f05d7b758f1060e6fe74a93f46dd54e9f04a9809177955a01af6b6debe4', 'hmi_guards': '26e89c11c0a8861b7954e0269bcb6735f698c90e00a6a54c7493a43b78e779a8'}


def validate_local_stop_fixture_trial(proof):
    if not isinstance(proof, dict):
        return False, "local STOP fixture trial proof must be an object"
    if (proof.get("schema") != LOCAL_STOP_FIXTURE_SCHEMA
            or proof.get("pair") != list(BOOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != BOOT_TRIAL_IMAGES
            or proof.get("fixture_pair") != list(LOCAL_STOP_FIXTURE_PAIR)
            or any(type(x) is not int for x in proof["fixture_pair"])
            or proof.get("fixture_images") != LOCAL_STOP_FIXTURE_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "local_stop_fixture_equivalence_one_powered_trial"):
        return False, "local STOP fixture trial identity/scope mismatch"
    for key in ("fixture_six_pwm_and_local_stop_pass", "fixture_stop_source_identical",
                "fixture_ten_code_sections_identical", "production_images_restored_verified",
                "production_idle_wifi_pass", "production_calibration_contract_pass",
                "retained_sd_sample_operator_reported", "offline_pass"):
        if proof.get(key) is not True:
            return False, "local STOP fixture trial evidence missing: " + key
    # A fixture capture must never be relabelled as an active production/HV test.
    for key in ("new_pair_active_pwm_measured", "physical_idle_registers_current",
                "exact_button_to_off_latency_measured", "forced_enable_hardware_validated",
                "hv_release_approved", "current_telemetry_qualified"):
        if proof.get(key) is not False:
            return False, "local STOP fixture trial overclaims: " + key
    for key, value in (("max_run_s", 3), ("max_frequency_hz", 5)):
        if type(proof.get(key)) is not int or proof[key] != value:
            return False, "local STOP fixture trial is limited to 5 Hz / 3 s"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 57:
        return False, "local STOP fixture trial baseline regression missing"
    if proof.get("evidence_sha256") != LOCAL_STOP_RETAINED_EVIDENCE:
        return False, "local STOP fixture trial retained evidence changed"
    sample = proof.get("sd_sample_v")
    if type(sample) not in (int, float) or not math.isfinite(sample) or sample != 2.6:
        return False, "local STOP fixture trial retained SD sample mismatch"
    gap = proof.get("idle_tx_max_gap_us")
    if type(gap) is not int or not 0 < gap < 100000:
        return False, "local STOP fixture trial idle scheduling margin missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "local STOP fixture trial proof expired"
    return True, "one 5-Hz / 3-second trial from measured fixture and exact code equivalence"


def validate_boot_trial(proof):
    if not isinstance(proof, dict):
        return False, "boot trial proof must be an object"
    if (proof.get("schema") != BOOT_TRIAL_SCHEMA
            or proof.get("pair") != list(BOOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != BOOT_TRIAL_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "local_stop_with_hardware_pwm_validation"):
        return False, "boot trial identity/scope mismatch"
    for key in ("nucleo_local_stop_source_audit_pass", "local_stop_hardware_validated",
                "new_pair_active_pwm_measured", "physical_idle_registers_current", "calibration_contract_pass",
                "images_verified", "offline_pass", "idle_wifi_pass",
                "autonomous_boot_pass", "prestart_break_context_pass",
                "sd_sample_operator_reported"):
        if proof.get(key) is not True:
            return False, "boot trial evidence missing: " + key
    for key in ("hv_release_approved", "current_telemetry_qualified"):
        if proof.get(key) is not False:
            return False, "boot trial must retain its unmeasured limits: " + key
    for key, expected in (("max_run_s", 3), ("max_frequency_hz", 5)):
        if type(proof.get(key)) is not int or proof[key] != expected:
            return False, "boot trial is limited to 5 Hz / 3 seconds"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 57:
        return False, "boot trial regression missing"
    sample = proof.get("sd_sample_v")
    # Static operator sample, not a claim of pulse-free SD or live GPIO readback.
    # DS12589 Table 53: VIH=0.7*VDD; use maximum normal VDD=3.6 V.
    if type(sample) not in (int, float) or not math.isfinite(sample) or not 2.52 < sample <= 3.6:
        return False, "static SD sample does not meet the bounded HIGH assumption"
    gap = proof.get("idle_tx_max_gap_us")
    if type(gap) is not int or not 0 < gap < 100000:
        return False, "idle supervisory scheduling margin not demonstrated"
    evidence = proof.get("evidence_sha256")
    if (not isinstance(evidence, dict) or set(evidence) != BOOT_TRIAL_EVIDENCE
            or any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
                   for x in evidence.values())):
        return False, "boot trial evidence fingerprints missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "boot trial qualification expired"
    return True, "one conditional 5-Hz / 3-second trial; not general powered release"


# Embedded in the prepared HMI; explicit component transfer, not a new PWM capture.
RX_SNAPSHOT_TRIAL_PAIR = (2026101104, 2026101102)
RX_SNAPSHOT_TRIAL_IMAGES = {
    "production_uno": "987a869e146e115ba9f526bf991e50cd461095f0c9448263f5502071b964e15f",
    "production_nucleo": "d17b1ed8313b7e355e66681f90beaf84e7535e22504212f79ef44ce2bad5d37c",
}
RX_SNAPSHOT_SCHEMA = "mic_ai.powered_trial.rx_snapshot_delta.v1"


def validate_rx_snapshot_trial(proof):
    if (proof.get("pair") != list(RX_SNAPSHOT_TRIAL_PAIR)
            or any(type(x) is not int for x in proof["pair"])
            or proof.get("images") != RX_SNAPSHOT_TRIAL_IMAGES
            or proof.get("profile") != "short"
            or proof.get("scope") != "pwm_component_transfer_with_rx_and_snapshot_delta"
            or proof.get("pwm_evidence_pair") != list(UART_V3_TRIAL_PAIR)
            or proof.get("pwm_evidence_images") != UART_V3_TRIAL_IMAGES):
        return False, "RX snapshot component identity/scope mismatch"
    for key in ("pwm_core_equivalence_pass", "break_irq_delta_audited", "calibration_contract_pass",
                "images_verified", "offline_pass", "idle_wifi_pass", "physical_idle_pass"):
        if proof.get(key) is not True:
            return False, "RX snapshot qualification missing: " + key
    if (proof.get("new_pair_active_pwm_measured") is not False
            or proof.get("hv_release_approved") is not False
            or proof.get("current_telemetry_qualified") is not False
            or type(proof.get("max_run_s")) is not int or proof["max_run_s"] != 3
            or type(proof.get("max_frequency_hz")) is not int or proof["max_frequency_hz"] != 5):
        return False, "RX snapshot trial must be explicitly limited to 5 Hz / 3 s"
    cases = proof.get("cases")
    if (not isinstance(cases, dict) or set(cases) != set(UART_V3_TRIAL_CASES)
            or any(x is not True for x in cases.values())):
        return False, "retained baseline PWM scenario evidence missing"
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < 51:
        return False, "RX snapshot trial regression missing"
    hashes = proof.get("evidence_sha256")
    required = {"pwm", "physical_idle", "delta_audit", "uno_install", "nucleo_install", "offline", "idle_wifi"}
    if (not isinstance(hashes, dict) or set(hashes) != required
            or any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
                   for x in hashes.values())):
        return False, "RX snapshot evidence fingerprints missing"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires-issued <= 600 or not issued <= time.time() < expires):
        return False, "RX snapshot preparation expired"
    return True, "one 5-Hz / 3-second component-transfer trial only"


def validate_powered_trial_qualification(proof: object) -> tuple[bool, str]:
    """Authenticated host attestation, not certification or an MCU flash reader."""
    if not isinstance(proof, dict):
        return False, "missing powered-trial qualification"
    if proof.get("schema") == LOCAL_STOP_FIXTURE_SCHEMA:
        return validate_local_stop_fixture_trial(proof)
    if proof.get("schema") == BOOT_TRIAL_SCHEMA:
        return validate_boot_trial(proof)
    if proof.get("schema") == RX_SNAPSHOT_SCHEMA:
        return validate_rx_snapshot_trial(proof)
    coast30 = proof.get("schema") == "mic_ai.powered_trial.coast30.v1"
    sender_delta = coast30 or proof.get("schema") == "mic_ai.powered_trial.sender_delta.v1"
    if not sender_delta and proof.get("schema") != "mic_ai.powered_trial.v1":
        return False, "unknown powered-trial qualification schema"
    expected_pair = UART_V3_SENDER_TRIAL_PAIR if sender_delta else UART_V3_TRIAL_PAIR
    expected_images = UART_V3_SENDER_TRIAL_IMAGES if sender_delta else UART_V3_TRIAL_IMAGES
    if (proof.get("pair") != list(expected_pair)
            or any(type(v) is not int for v in proof["pair"])
            or proof.get("images") != expected_images):
        return False, "qualification image/pair mismatch"
    if sender_delta:
        if (proof.get("scope") != "unchanged_nucleo_pwm_plus_sender_delta"
                or proof.get("pwm_evidence_pair") != list(UART_V3_TRIAL_PAIR)
                or proof.get("pwm_evidence_images") != UART_V3_TRIAL_IMAGES
                or proof.get("new_pair_active_pwm_measured") is not False
                or any(proof.get(k) is not True for k in (
                    "sender_delta_verified", "sender_flash_verified", "fresh_idle_wifi_pass"))):
            return False, "sender trial needs explicit component-evidence transfer"
    if coast30:
        if (proof.get("profile") != COAST30_PROFILE
                or proof.get("coast_only") is not True
                or any(proof.get(k) is not True for k in (
                    "native_coast_profile_pass", "prior_rotation_operator_confirmed", "prior_active_health_clean"))
                or proof.get("prior_stop_cause_uniquely_verified") is not False
                or proof.get("current_telemetry_qualified") is not False):
            return False, "coast trial evidence or scope missing"
        cap = proof.get("dc_capacitance_uf")
        if type(cap) not in (int,float) or not math.isfinite(cap) or cap <= 0:
            return False, "confirmed capacitance required"
    cases = proof.get("cases")
    if (not isinstance(cases, dict) or set(cases) != set(UART_V3_TRIAL_CASES)
            or any(v is not True for v in cases.values())):
        return False, "eight retained zero-bus scenarios required"
    for key in ("normal_restore_verified", "offline_pass", "idle_wifi_pass", "physical_idle_pass"):
        if proof.get(key) is not True:
            return False, "qualification failed: " + key
    if type(proof.get("offline_suites")) is not int or proof["offline_suites"] < (44 if coast30 else 41 if sender_delta else 40):
        return False, "updated trial regression required"
    if proof.get("hv_release_approved") is not False:
        return False, "trial attestation must not claim general HV approval"
    digests = proof.get("evidence_sha256")
    expected_evidence = {"pwm", "offline", "idle_wifi", "physical_idle"}
    if sender_delta:
        expected_evidence |= {"sender_delta", "sender_install"}
    if coast30:
        expected_evidence |= {"coast_profile", "powered_review"}
    if not isinstance(digests, dict) or set(digests) != expected_evidence:
        return False, "qualification evidence missing"
    if any(not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
           for v in digests.values()):
        return False, "invalid evidence fingerprint"
    issued, expires = proof.get("issued_at"), proof.get("expires_at")
    if (type(issued) not in (int, float) or type(expires) not in (int, float)
            or not math.isfinite(issued) or not math.isfinite(expires)
            or not 0 < expires - issued <= 3600 or not issued <= time.time() < expires):
        return False, "qualification attestation expired or invalid"
    return True, "one bounded trial only"


class PoweredTrialGate:
    """One-use permission with fresh powered idle observations; never drives GPIO."""

    def __init__(self, valid_for_sec: float = 3600, pair=UART_V3_TRIAL_PAIR, profile="short", wait_without_deadline: bool = False) -> None:
        if type(wait_without_deadline) is not bool:
            raise ValueError("invalid wait policy")
        if wait_without_deadline and (pair != BOOT_TRIAL_PAIR or profile != "short"):
            raise ValueError("unreviewed unlimited preparation wait")
        if (type(valid_for_sec) not in (int, float) or not math.isfinite(valid_for_sec)
                or not 0 < valid_for_sec <= 3600):
            raise ValueError("trial preparation lifetime must be within (0,3600] seconds")
        if pair not in (UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR, RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR):
            raise ValueError("unreviewed trial pair")
        if profile not in ("short", COAST30_PROFILE) or (profile==COAST30_PROFILE and pair!=UART_V3_SENDER_TRIAL_PAIR):
            raise ValueError("unreviewed trial profile/pair")
        self.profile = profile
        self.max_run_s = 33 if profile==COAST30_PROFILE else 3
        self.stop_after_s = 30 if profile==COAST30_PROFILE else 3
        self.max_freq_hz = 5 if pair in (RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR) else (50 if profile==COAST30_PROFILE else 10)
        self.deadline_reason = f"powered trial independent {self.stop_after_s}-second deadline reached"
        self.pair = pair
        self._lock = threading.RLock()
        self.created = time.monotonic()
        self.expires_at = None if wait_without_deadline else self.created + valid_for_sec
        self.invalidated_reason = None
        self.consumed = False
        self.started_at = None
        self.reset_observation("awaiting fault-free powered idle telemetry")

    def reset_observation(self, reason: str) -> None:
        self.begin = None
        self.last_seen = None
        self.first_good = None
        self.last_good = None
        self.samples = 0
        self.reason = reason

    @staticmethod
    def live_check(data: Optional[dict], idle: bool = False,
                   pair=UART_V3_TRIAL_PAIR, allow_stopped_zero: bool = False, profile="short") -> tuple[bool, str]:
        if not isinstance(data, dict):
            return False, "trial telemetry unavailable"
        if profile not in ("short",COAST30_PROFILE) or (profile==COAST30_PROFILE and pair!=UART_V3_SENDER_TRIAL_PAIR):
            return False, "unreviewed trial profile/pair"
        if (any(type(data.get(k)) is not int for k in ("fw_build", "mc_fw_build"))
                or pair not in (UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR, RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR)
                or (data.get("fw_build"), data.get("mc_fw_build")) != pair):
            return False, "trial peer identity changed"
        if pair in (RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR):
            for key in ("uno_rx_dropped", "uno_rx_hw_errors", "uno_rx_hw_flags", "mc_break_rx_bad"):
                if type(data.get(key)) is not int or data[key] != 0:
                    return False, "RX snapshot trial transport unhealthy: " + key
        for key in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence", "mc_uart_error_flags",
                    "mc_last_uart_error_flags", "uno_tx_short_writes", "bp_transport_fault",
                    "mc_last_bad_reason", "bp_bad", "bp_bad_cnt"):
            if type(data.get(key)) is not int or data[key] != 0:
                return False, "trial transport unhealthy: " + key
        for key in ("mc_age_ms", "bp_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
            value = data.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 300:
                return False, "trial telemetry stale: " + key
        for key in ("vdc", "bp_vdc"):
            value = data.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 250 <= value <= 360:
                return False, "trial bus outside 250..360 V"
        if abs(data["vdc"] - data["bp_vdc"]) > 1:
            return False, "trial bus readings disagree"
        if any(data.get(k) != 1 for k in ("mc_diag_valid", "bp_vbus_valid", "bp_temp_valid",
                                         "bp_mcsdk_telemetry", "bp_softstart_ready")):
            return False, "trial diagnostics/measurements not ready"
        if data.get("estop") != 0 or (idle and data.get("pwm") != 0):
            return False, "trial observation requires outputs off"
        temp = data.get("bp_temp_c")
        if type(temp) not in (int, float) or not math.isfinite(temp) or not -20 <= temp <= 80:
            return False, "trial heatsink temperature invalid"
        raw = data.get("bp_vbus_raw")
        if type(raw) is not int or abs(raw*.1 - data["bp_vdc"]) > 1:
            return False, "trial bus word disagrees with scaled telemetry"
        if any(data.get(k) != 0 for k in ("bp_fault", "bp_temp_fault", "precharge", "pfc", "brake", "bp_ext")):
            return False, "trial fault or service output active"
        if data.get("mode") != "VF" or data.get("mc_capabilities") != MC_CAP_VF:
            return False, "trial requires V/f backend"
        freq = data.get("freq_cmd")
        stopped_zero = (allow_stopped_zero and not idle and freq == 0
            and data.get("state") == "SAFE" and data.get("pwm") == 0
            and not (_as_int(data, "bp_status", 0x22) & 0x22))
        if (type(freq) not in (int, float) or not math.isfinite(freq)
                or not ((freq==50 if profile==COAST30_PROFILE else 0 < freq <= (5 if pair in (RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR) else 10)) or stopped_zero)):
            return False, "trial frequency target must be within (0,10] Hz"
        if idle and (data.get("state") != "SAFE" or _as_int(data, "bp_status", 0x22) & 0x22):
            return False, "trial observation requires SAFE controller"
        return True, "ok"

    def observe(self, data: Optional[dict], calibrated: bool) -> None:
        with self._lock:
            self._observe(data, calibrated)

    def _observe(self, data: Optional[dict], calibrated: bool) -> None:
        now = time.monotonic()
        if self.consumed or self.invalidated_reason:
            return
        if self.expires_at is None and isinstance(data, dict) and (data.get("fw_build"), data.get("mc_fw_build")) != self.pair:
            self.invalidated_reason = "prepared peer identity changed"
            self.reset_observation(self.invalidated_reason)
            return
        ok, reason = self.live_check(data, idle=True, pair=self.pair, profile=self.profile)
        if not calibrated or not ok:
            self.reset_observation(reason if calibrated else "trial bus calibration invalid")
            return
        good = data.get("bp_good")
        if type(good) is not int or good < 0:
            self.reset_observation("trial valid-frame counter unavailable")
            return
        if self.expires_at is None and self.last_good is not None and good < self.last_good:
            self.invalidated_reason = "prepared controller restarted"
            self.reset_observation(self.invalidated_reason)
            return
        if (self.last_seen is not None and (now - self.last_seen > 2
                or good < self.last_good)):
            self.reset_observation("observation gap or controller restart")
        if self.begin is None:
            self.begin, self.first_good = now, good
        if self.last_good != good:
            self.samples += 1
        self.last_seen, self.last_good = now, good
        self.reason = "powered idle observation in progress"

    def ready(self, data: Optional[dict], calibrated: bool) -> tuple[bool, str]:
        with self._lock:
            return self._ready(data, calibrated)

    def _ready(self, data: Optional[dict], calibrated: bool) -> tuple[bool, str]:
        self.observe(data, calibrated)
        if self.consumed:
            return False, "one-shot powered trial already consumed"
        if self.invalidated_reason:
            return False, self.invalidated_reason
        if self.expires_at is not None and time.monotonic() >= self.expires_at:
            return False, "powered trial preparation expired"
        if (self.begin is None or time.monotonic() - self.begin < 30 or self.samples < 20
                or self.last_good - self.first_good < 100):
            return False, self.reason + "; need 30 seconds and 100 new valid frames"
        return True, f"powered idle qualified for one {self.stop_after_s}-second trial"

    def consume(self) -> None:
        with self._lock:
            self._consume()

    def _consume(self) -> None:
        if self.consumed:
            raise RuntimeError("powered trial already consumed")
        self.consumed = True
        self.started_at = time.monotonic()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {"hmi_powered_trial_enabled": 1, "hmi_powered_trial_used": int(self.consumed),
                "hmi_powered_trial_observed_s": round(0 if self.begin is None else time.monotonic()-self.begin, 1),
                "hmi_powered_trial_samples": self.samples, "hmi_powered_trial_reason": self.reason,
                "hmi_powered_trial_wait_limited": int(self.expires_at is not None),
                "hmi_powered_trial_remaining_s": None if self.expires_at is None else round(max(0, self.expires_at-time.monotonic()), 1),
                "hmi_powered_trial_max_run_s": self.max_run_s, "hmi_powered_trial_max_freq_hz": self.max_freq_hz,
                "hmi_powered_trial_stop_after_s": self.stop_after_s,
                "hmi_powered_trial_profile": self.profile}

TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

try:
    from active_pwm_guard import start_allowed_by_bench_gate
except Exception:  # pragma: no cover - fail closed if tooling import is broken
    start_allowed_by_bench_gate = None  # type: ignore[assignment]

def effective_mode(
    mode_code: int,
    mc_mode: int,
    diag_mode: Optional[int] = None,
    duty_mode: Optional[int] = None,
) -> tuple[int, str]:
    if diag_mode is not None:
        if int(diag_mode) != 0:
            return 3, MODE_NAMES[3]
    elif mc_mode == MC_MODE_DIAG:
        return 3, MODE_NAMES[3]
    if duty_mode is not None:
        if int(duty_mode) != 0:
            return 4, MODE_NAMES[4]
    elif mc_mode == MC_MODE_DUTY:
        return 4, MODE_NAMES[4]
    return mode_code, MODE_NAMES.get(mode_code, str(mode_code))


def _now_ts() -> float:
    return time.time()


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def termios_baud_constant(baud: int) -> int:
    if termios is None:
        raise RuntimeError("termios not available on this platform")
    name = f"B{int(baud)}"
    if not hasattr(termios, name):
        raise RuntimeError(f"termios baud {baud} is not supported by this platform")
    return int(getattr(termios, name))


class LogStore:
    def __init__(self, max_bytes: int, log_path: Optional[str], file_max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._total_bytes = 0
        self._items: Deque[Tuple[float, str]] = deque()
        self._lock = threading.Lock()
        self._log_path = log_path
        self._file_max_bytes = file_max_bytes
        if self._log_path:
            log_dir = os.path.dirname(self._log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

    def add(self, line: str) -> None:
        ts = _now_ts()
        entry = f"{_fmt_ts(ts)} {line}"
        size = len(entry) + 1
        with self._lock:
            self._items.append((ts, entry))
            self._total_bytes += size
            while self._total_bytes > self._max_bytes and self._items:
                _, old = self._items.popleft()
                self._total_bytes -= (len(old) + 1)
            if self._log_path:
                self._append_to_file(entry)

    def _append_to_file(self, entry: str) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            if self._file_max_bytes <= 0:
                return
            size = os.path.getsize(self._log_path)
            if size <= self._file_max_bytes:
                return
            self._truncate_file_tail()
        except Exception:
            pass

    def _truncate_file_tail(self) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                keep = min(size, self._file_max_bytes)
                f.seek(max(size - keep, 0))
                data = f.read()
            # Drop partial line at start
            nl = data.find(b"\n")
            if nl != -1:
                data = data[nl + 1 :]
            with open(self._log_path, "wb") as f:
                f.write(data)
        except Exception:
            pass

    @staticmethod
    def _parse_ts(entry: str) -> Optional[float]:
        try:
            ts_str = entry[:19]
            return time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return None

    def dump_since(self, since_ts: float) -> List[str]:
        if self._log_path and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
                out: List[str] = []
                for raw_line in lines:
                    # Concurrent legacy writers could leave sparse NUL bytes in
                    # the persistent log. Never expose them through /api/logs.
                    line = raw_line.replace("\x00", "").strip()
                    if not line:
                        continue
                    ts = self._parse_ts(line)
                    if ts is None or ts >= since_ts:
                        out.append(line)
                return out
            except Exception:
                pass
        with self._lock:
            return [entry for ts, entry in self._items if ts >= since_ts]


def _tail_text(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _as_float(data: dict, key: str, default: float = 0.0) -> float:
    if key.startswith("bp_") and f"mc_{key[3:]}" in data:
        key = f"mc_{key[3:]}"
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default


def _as_int(data: dict, key: str, default: int = 0) -> int:
    if key.startswith("bp_") and f"mc_{key[3:]}" in data:
        key = f"mc_{key[3:]}"
    try:
        return int(float(data.get(key, default)))
    except (TypeError, ValueError):
        return default


def local_stop_latched(data: Optional[dict]) -> int:
    """Derive the current latch from controller telemetry, independently of first fault."""
    return int(bool(_as_int(data or {}, "bp_status", 0) & 0x80))


# Imported as source into the HMI; no network or controller commands here.
def current_crc32c(raw):
    value = 0xffffffff
    for byte in raw:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82f63b78 if value & 1 else 0)
    return value ^ 0xffffffff


def with_shunt_currents(data):
    data.update(mc_current_telemetry_valid=0, mc_current_telemetry_source='nucleo_shunt_unavailable',
                mc_current_scale_qualified=0, mc_current_status='Нет свежих измерений шунтов',
                mc_current_rms_a=None, mc_current_peak_a=None, mc_current_instant_a=None,
                mc_current_zero_ready=0, mc_current_frozen=0,
                mc_current_raw_adc=None, mc_current_offsets_adc=None, mc_current_zero_samples=None,
                mc_current_zero_spans=None, mc_current_zero_attempts=None, mc_current_zero_stable=None,
                mc_current_flags=0, mc_current_coverage_pct=0, mc_current_reconstructed_mask=0,
                mc_current_window_ms=0, mc_current_rejected_samples=0)
    if (data.get('fw_build'), data.get('mc_fw_build')) not in ((2026102509, 2026102510), (2026102513, 2026102510), (2026102515, 2026102510), (2026102516, 2026102510), (2026102517, 2026102510), (2026102518, 2026102510), (2026102601, 2026102602),(2026102603, 2026102602),(2026102605, 2026102604),(2026102607, 2026102604),(2026102609, 2026102604),(2026102701, 2026102702),(2026102703, 2026102704),(2026102705, 2026102706),(2026102707, 2026102708),(2026102709, 2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026103015,2026103016)):
        return data

    def packet(key, version):
        raw = bytes.fromhex(data.get(key, '-'))
        if (len(raw) != 43 or raw[:3] != bytes((0x55, 0xaa, version)) or raw[38] != 1
                or int.from_bytes(raw[6:10], 'little') != int(data['mc_fw_build'])
                or current_crc32c(raw[:39]) != int.from_bytes(raw[39:], 'little')):
            raise ValueError('Invalid current record')
        return raw

    try:
        quality_age = int(data.get('mc_current_quality_age_ms', 999999))
        if 0 <= quality_age < 1500:
            quality = packet('mc_current_quality_hex', 0xd7)
            lows = [int.from_bytes(quality[i:i+2], 'little') for i in range(14, 22, 2)]
            highs = [int.from_bytes(quality[i:i+2], 'little') for i in range(22, 30, 2)]
            if quality[5] > 8 or quality[30] > 3 or quality[32:36] != bytes((3, 8, 0, 2)):
                raise ValueError('Invalid zero quality contract')
            if quality[36:38] != bytes((3,2)): raise ValueError('Invalid mean uncertainty contract')
            data.update(mc_current_zero_spans=[hi-lo for lo,hi in zip(lows,highs)],
                        mc_current_zero_attempts=quality[5], mc_current_zero_stable=quality[30],
                        mc_current_zero_last_reject=quality[31])
        detail_age = int(data.get('mc_current_detail_age_ms', 999999))
        if 0 <= detail_age < 1500:
            detail = packet('mc_current_detail_hex', 0xd6)
            data['mc_current_raw_adc'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(14, 22, 2)]
            data['mc_current_offsets_adc'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(22, 30, 2)]
            data['mc_current_zero_samples'] = [int.from_bytes(detail[i:i+2], 'little') for i in range(30, 38, 2)]
            data['mc_current_zero_ready'] = int(bool(detail[3] & 1))
            if detail[3] & 16:
                data['mc_current_status'] = 'Автоноль отклонён после проверки нескольких блоков; смотрите разброс каналов'
        raw = packet('mc_current_packet_hex', 0xd5)
        age = int(data.get('mc_current_age_ms', 999999))
        if not (0 <= age < 750 and 0 <= data.get('mc_age_ms', 999999) < 300):
            data['mc_current_status'] = 'Данные токов устарели'
            return data
        flags = raw[3]
        data.update(mc_current_flags=flags, mc_current_zero_ready=int(bool(flags & 1)),
                    mc_current_frozen=int(bool(flags & 4)), mc_current_coverage_pct=raw[5],
                    mc_current_reconstructed_mask=raw[32],
                    mc_current_window_tick_ms=int.from_bytes(raw[10:14], 'little'),
                    mc_current_window_ms=int.from_bytes(raw[34:36], 'little'),
                    mc_current_rejected_samples=int.from_bytes(raw[36:38], 'little'))
        if flags & 16:
            data['mc_current_status'] = 'Автоноль отклонён после проверки нескольких блоков; смотрите разброс каналов'
        elif not flags & 1:
            data['mc_current_status'] = 'Ожидается автоноль при выключенном ШИМ и низкой DC-шине'
        elif not flags & 2:
            data['mc_current_status'] = ('Недостоверное окно АЦП: недостаточное покрытие, фронты ШИМ, рассинхронизация или насыщение; смотрите флаги и долю принятых отсчётов'
                                         if flags & (32 | 64) else 'Автоноль готов; ожидается окно тока при работе')
        else:
            rms = [int.from_bytes(raw[i:i+2], 'little') / 1000 for i in range(14, 20, 2)]
            peak = [int.from_bytes(raw[i:i+2], 'little') / 1000 for i in range(20, 26, 2)]
            instant = [int.from_bytes(raw[i:i+2], 'little', signed=True) / 1000 for i in range(26, 32, 2)]
            data.update(mc_current_telemetry_valid=1, mc_current_telemetry_source='nucleo_three_shunt_nominal_scale',
                        mc_current_rms_a=rms, mc_current_peak_a=peak, mc_current_instant_a=instant)
            data['mc_current_status'] = ('Последнее окно перед остановом' if flags & 4 else 'Измерение при работе')
            data['mc_current_status'] += '; номинальный масштаб, ещё не проверен эталоном'
        return data
    except (ValueError, TypeError, OverflowError):
        return data

# Inserted into HMI after current_crc32c; decoder only, no controller writes.
"""Frozen observer diagnostics; all speeds/currents are model estimates."""
def decode_observer_trace_hex(value,expected):
    import struct
    import math
    raw=bytes.fromhex(value)
    if len(raw)!=1696:raise ValueError('observer record length')
    header=struct.unpack_from('<16I',raw)
    magic,schema,fw,size,capacity,count,oldest,stride,total,valid,invalid,loss,loss_step,flags,fault,want=header
    if (magic,schema,fw,size,capacity)!=(0x3144534f,1,expected,96,16) or not 1<=count<=16 or not 0<=oldest<16:
        raise ValueError('observer record ABI/peer/count')
    if not flags&1 or flags&~3 or loss not in (0,1) or valid+invalid!=total or count>total or stride!=334:
        raise ValueError('observer record counters/flags')
    c=0xffffffff
    for i,byte in enumerate(raw):
        c^=0 if 60<=i<64 else byte
        for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
    if c^0xffffffff!=want:raise ValueError('observer record CRC')
    reasons={1:'контур не работает',2:'профиль не разрешён',4:'меньше 500 шагов',8:'авария контура',
             16:'поток не выше половины задания',32:'NIS не меньше 25',64:'нечисловое значение'}
    def sample(offset):
        u=struct.unpack_from('<8I14f2I',raw,offset)
        cycles,steps,why,cs,ca,seq,adc,bin_tick=u[:8]
        if why&~127 or u[-1] not in (0,1):raise ValueError('observer sample flags')
        floats=[v if math.isfinite(v) else None for v in u[8:22]]
        rpm,fa,fb,nis,id_,iq,idref,iqref,reference,ia,ib,va,vb,dt=floats
        flux=math.hypot(fa,fb) if fa is not None and fb is not None else None
        return dict(cycles=cycles,steps=steps,reason_mask=why,estimate_valid=why==0,
            reasons_ru=[text for bit,text in reasons.items() if why&bit],
            control_sample_sequence=cs,control_adc_cycles=ca,observer_sample_sequence=seq,
            observer_adc_cycles=adc,bin_cycles=bin_tick,rpm_est=rpm,
            flux_alpha_wb=fa,flux_beta_wb=fb,flux_wb=flux,nis=nis,
            id_A=id_,iq_A=iq,id_ref_A=idref,iq_ref_A=iqref,reference_hz=reference,
            observer_ia_A=ia,observer_ib_A=ib,input_va_V=va,input_vb_V=vb,dt_s=dt,
            observer_fault=u[-2],published=bool(u[-1]))
    rows=[sample(64+96*((oldest+i)%16)) for i in range(count)]
    first=sample(64+96*16) if loss else None
    if first and first['steps']!=loss_step:raise ValueError('observer loss step')
    return dict(available=True,schema=schema,firmware=fw,count=count,total_observer_samples=total,
        valid_samples=valid,invalid_samples=invalid,first_loss=first,control_fault=fault,
        record_stride_steps=stride,samples=rows,
        summary_ru=('Первый отказ оценки: '+', '.join(first['reasons_ru'])) if first else 'После достоверной оценки отказ не записан',
        limitation='Id/Iq и задания относятся к последнему fast-кадру входного bin; поток/NIS — после шага наблюдателя. Это разные явно помеченные моменты. Значения по номинальному масштабу; фактическая скорость независимо не измерена.')


def with_observer_trace(data):
    value=data.get('mc_observer_trace_hex','-')
    data['observer_trace']={'available':False,'reason':'not_received'}
    if value in ('-',''):return data
    try:data['observer_trace']=decode_observer_trace_hex(value,int(data['mc_fw_build']))
    except (ValueError,TypeError,OverflowError):data['observer_trace']={'available':False,'reason':'invalid_record'}
    return data


def decode_adc_peak_hex(value, expected_build=2026102510):
    import struct
    raw = bytes.fromhex(value)
    if len(raw) != 1024:
        raise ValueError('ADC trace must contain 1024 bytes')
    checked = bytearray(raw)
    checked[60:64] = b'\0'*4
    if current_crc32c(checked) != int.from_bytes(raw[60:64], 'little'):
        raise ValueError('ADC trace record CRC mismatch')
    h = struct.unpack_from('<IHHII6H9I', raw)
    if (h[0:3] != (0x31435041, 1, 80) or h[3] != expected_build or h[4] != 1
            or h[5] != 12 or not 1 <= h[6] <= 12 or not 0 <= h[7] < 12
            or h[9:11] != (626, 6) or h[16:18] != (170000000, 42500000)):
        raise ValueError('Unexpected ADC trace layout or firmware')
    peak_seen = bool(h[15] & 1)
    if h[15] & ~7 or (peak_seen and not 0 <= h[8] < 12) or (not peak_seen and h[8] != 65535):
        raise ValueError('Invalid ADC trace trigger flags')
    rows = []
    for n in range(h[6]):
        slot = (h[7]+n) % 12
        s = struct.unpack_from('<8I8H14H2BH', raw, 64+80*slot)
        if s[30] > 2 or s[31] > 2 or any(x > 4095 for x in s[19:21]):
            raise ValueError('Invalid ADC sample channels or range')
        pair=s[30]; path1=1 if pair==2 else 0; path2=2 if pair==0 else 3
        phase1=1 if pair==2 else 0; phase2=1 if pair==0 else 2
        counts=[0,0,0]
        counts[phase1]=s[21+path1]-s[19]
        counts[phase2]=s[21+path2]-s[20]
        counts[3-phase1-phase2]=-counts[phase1]-counts[phase2]
        active=list(s[8:12]); trigger=active[3]
        excluded=0 if pair==2 else 1 if pair==1 else 2
        epoch_valid=s[2]==s[3] and not bool(s[25]&128)
        rows.append(dict(index=n,slot=slot,cycles=s[0],sequence=s[1],
            epoch_before=s[2],epoch_after=s[3],epoch_consistent=epoch_valid,
            adc_isr=[s[4],s[5]],adc_jsqr_after_conversion=[s[6],s[7]],
            ccr_at_update=active,ccr_preload=list(s[12:16]),
            timer_cnt_entry=s[16],timer_arr=s[17],timer_dir_entry=int(bool(s[18]&16)),
            raw_adc=list(s[19:21]),offsets_adc=list(s[21:25]),flags=s[25],
            timer_cnt_after_queue=s[26],timer_dir_after_queue=int(bool(s[25]&512)),reference_hz=s[27]/10,bus_v=s[28],
            timer_cnt_at_update=s[29],pair=pair,next_pair=s[31],timer_dir_at_update=int(bool(s[32]&16)),
            accepted_by_existing_monitor=bool(s[25]&64),accepted_by_monitor=bool(s[25]&64),
            three_leg_window_rejected=bool(s[25]&1024),queue_overflow_observed=bool(s[25]&256),
            publish_deadline_missed=bool(s[25]&2048),pending_epoch_mismatch=bool(s[25]&4096),injected_queue_not_empty=bool(s[25]&8192),
            timer_phase_entry_ticks=(2*s[17]-s[16]) if s[18]&16 else s[16],
            counts_uvw=counts,nominal_currents_a=[round(x*3.3/(4095*.04*2.1),6) for x in counts],
            excluded_compare_inside_assumed_acquisition=(trigger<=active[excluded]<=trigger+112) if epoch_valid else None,
            is_trigger=peak_seen and slot==h[8]))
    if any(rows[i]['sequence']+1 != rows[i+1]['sequence'] for i in range(len(rows)-1)):
        raise ValueError('ADC trace sample sequence is not contiguous')
    trigger_row=next((x for x in rows if x['is_trigger']),None)
    if peak_seen and (trigger_row is None or trigger_row['sequence']!=h[12]):
        raise ValueError('ADC trigger sample missing or inconsistent')
    return dict(schema=1,firmware=h[3],capture_id=h[4],sample_count=h[6],
        threshold_counts=h[9],threshold_nominal_a=round(626*3.3/(4095*.04*2.1),6),
        total_samples=h[11],trigger_sequence=h[12],frozen_sequence=h[13],frozen_ms=h[14],
        peak_seen=peak_seen,post_short=bool(h[15]&2),no_peak=bool(h[15]&4),
        trigger_reference_hz=trigger_row['reference_hz'] if trigger_row else None,
        cpu_hz=h[16],adc_hz=h[17],max_queue_publish_cycles=h[18],max_queue_publish_us=h[18]/170,samples=rows,scale_qualified=False,
        limitation='CCR-at-update is a software latch at the update IRQ, not direct active-register readback; epoch races are explicit. Raw ADC alone cannot certify actual motor current.')


def with_adc_peak(data):
    data.update(mc_adc_peak_valid=0,mc_adc_peak=None,mc_adc_peak_status='Ожидание захвата АЦП')
    if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102509,2026102510),(2026102513,2026102510),(2026102515,2026102510),(2026102516,2026102510),(2026102517,2026102510),(2026102518,2026102510),(2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102607,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704),(2026102705,2026102706),(2026102707,2026102708),(2026102709,2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026103015,2026103016)):
        return data
    if data.get('mc_adc_peak_hex','-') == '-':
        if data.get('mc_adc_peak_good',0):
            data['mc_adc_peak_status']='После STOP: принимаются страницы захвата АЦП'
        return data
    try:
        trace=decode_adc_peak_hex(data['mc_adc_peak_hex'],int(data['mc_fw_build']))
        data.update(mc_adc_peak_valid=1,mc_adc_peak=trace,
            mc_adc_peak_status=('Захват пика АЦП сохранён' if trace['peak_seen'] else 'Сохранены последние отсчёты: порог пика не достигнут'))
    except (ValueError,TypeError) as exc:
        data['mc_adc_peak_status']='Ошибка записи захвата АЦП: '+str(exc)
    return data


# Decoder only; no hardware commands. Inserted after current/peak decoders.
"""Decode frozen pre-reset I2C records; never infer physical waveform timing."""
import struct

CAUSES={2:'NACK',6:'DEADLINE',7:'SETUP',8:'BERR',9:'ARLO',10:'OVR',11:'BUSY',12:'SHORT'}

def crc32c(data):
    crc=0xffffffff
    for byte in data:
        crc^=byte
        for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
    return crc^0xffffffff

def decode(raw,peer,kind):
    if len(raw)!=160 or peer not in (2026102604,2026102702,2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016) or kind not in (0,1):raise ValueError('Unsupported I2C fault record')
    w=struct.unpack('<40I',raw)
    cause=w[4]&255;stage=(w[4]>>8)&255;state=(w[4]>>16)&255;n=((w[4]>>24)&3) if peer in (2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016) else w[4]>>24
    if w[0]!=0x31434649 or w[1]!=peer or cause not in CAUSES or stage>11 or state>4 or n>3 or not w[32]:
        raise ValueError('Invalid I2C fault record')
    if kind==1 and not(w[16]&32768):raise ValueError('PWM record lacks MOE evidence')
    names={2:'tick_ms',3:'cycles',5:'decision_isr',6:'isr_before_gpio',7:'gpiob_idr',8:'isr_after_gpio',
        9:'cr1',10:'cr2',11:'timingr',12:'gpiob_moder',13:'gpiob_otyper',14:'gpiob_afrh',15:'rcc_ccipr',
        16:'tim1_bdtr',17:'tim1_cnt',18:'tim1_cr1',19:'tim1_arr',20:'tim1_ccr1',21:'tim1_ccr2',22:'tim1_ccr3',
        23:'poll_gap_cycles',24:'max_poll_gap_cycles',25:'attempt_age_cycles',26:'errors_before',27:'reads_before',
        28:'previous_isr',29:'previous_cr2',30:'previous_gpio',31:'previous_cycles',32:'sysclk_hz',33:'rcc_cfgr',
        34:'gpio_sample_cycles',35:'post_reset_isr',36:'post_reset_cr1',37:'post_reset_cr2',38:'post_reset_gpio',39:'post_reset_cycles'}
    result={name:w[i] for i,name in names.items()}
    result.update(kind='first_since_boot' if kind==0 else 'first_with_pwm',cause=CAUSES[cause],cause_code=cause,
        stage=stage,driver_state=state,received_bytes=n,scl=bool(w[7]&(1<<8)),sda=bool(w[7]&(1<<9)),
        pwm_moe=bool(w[16]&32768),poll_gap_us=w[23]*1e6/w[32],attempt_age_us=w[25]*1e6/w[32],
        registers_changed_during_gpio_sample=w[6]!=w[8],record_crc32c=f'{crc32c(raw):08x}',
        limitation='Sequential MMIO snapshot before PE/reset; not an analog waveform or a simultaneous sample of all registers')
    if peer in (2026102704,2026102706,2026102708,2026102710,2026102812,2026102902,2026103016):
        for suffix in ('isr','cr1','cr2','gpio','cycles'):
            result['cleanup_terminal_'+suffix]=result.pop('post_reset_'+suffix)
        flags=w[4]>>26
        result.update(cleanup_flags=flags,cleanup_stop_seen=bool(flags&1),cleanup_forced=bool(flags&2),
            cleanup_arlo=bool(flags&4),cleanup_stop_requested=bool(flags&8),cleanup_expired=bool(flags&16),
            cleanup_no_transfer=bool(flags&32),cleanup_duration_us=((w[39]-w[3])&0xffffffff)*1e6/w[32])
    return result

def decode_i2c_release(raw,parent_raw,peer,kind):
    if peer not in (2026102706,2026102708,2026102710,2026102812,2026102902,2026103016) or len(raw)!=100 or len(parent_raw)!=160 or kind not in (0,1):
        raise ValueError('Unsupported PE release extension')
    decode(parent_raw,peer,kind)
    w=struct.unpack('<25I',raw);parent=struct.unpack('<40I',parent_raw)
    flags=w[3]&255;count=(w[3]>>8)&255;result=(w[3]>>16)&255;hz=w[6]
    if (w[0]!=0x31525053 or w[1]!=peer or w[3]>>24 or flags&~15 or count>3 or result>3
        or hz<1000000 or crc32c(raw[:96])!=w[24] or w[2]!=crc32c(parent_raw)
        or parent[0]!=0x31434649 or parent[1]!=peer or w[7]!=parent[2]
        or w[4]!=parent[39] or w[5]!=parent[38] or hz!=parent[32]):
        raise ValueError('Invalid PE release identity/CRC/link')
    if bool(count)!=bool(flags&1) or (not count and not(flags&4)):
        raise ValueError('Missing PE release observation')
    if flags&2 and (flags&12 or count!=2):raise ValueError('Invalid late sample flags')
    complete=not(flags&12) and (count==3 or (count==2 and flags&2))
    if not complete and not(flags&12):raise ValueError('Unfinished extension published')
    samples=[];levels=set()
    for i in range(3):
        s=w[8+5*i:13+5*i]
        if i>=count:
            if any(s):raise ValueError('Nonzero unused sample')
            continue
        cycles,isr,cr1,cr2,gpio=s
        if cr1&1:raise ValueError('I2C was re-enabled during release observation')
        if i:
            dt=((cycles-w[8])&0xffffffff)//(hz//1000000)
            if not (5 if i==1 else 20)<=dt<=1000:raise ValueError('Invalid sample timing')
        levels.add(bool(gpio&256))
        samples.append(dict(index=i,cycles=cycles,isr=isr,cr1=cr1,cr2=cr2,gpiob_idr=gpio,
            scl=bool(gpio&256),sda=bool(gpio&512),pe=False,
            after_PE0_us=((cycles-w[23])&0xffffffff)*1e6/hz))
    expected=0 if not complete else 3 if len(levels)==2 else 1 if True in levels else 2
    if result!=expected:raise ValueError('Inconsistent observed levels')
    labels={0:'Наблюдение после PE=0 неполное',1:'После PE=0: SCL HIGH',2:'После PE=0: SCL LOW',3:'После PE=0: SCL менял уровень'}
    return dict(kind='first_since_boot' if kind==0 else 'first_with_pwm',result=result,
        summary_ru=labels[result],flags=flags,count=count,complete=bool(complete),late_poll=bool(flags&2),
        cancelled=bool(flags&4),timeout=bool(flags&8),parent_crc32c=f'{w[2]:08x}',record_crc32c=f'{w[24]:08x}',wire_crc32c_residue=f'{crc32c(raw):08x}',
        terminal_cycles=w[4],terminal_gpio=w[5],pe_off_cycles=w[23],samples=samples,
        pe_was_enabled_before_disable=bool(parent[36]&1),scl_at_terminal=bool(w[5]&256),sda_at_terminal=bool(w[5]&512),
        immediate_delay_us=samples[0]['after_PE0_us'] if samples else None,
        source_attribution_proven=False,
        limitation='Sequential digital samples with actual times; neither an analog waveform nor proof of which device caused LOW')

def with_bus_clear(data):
    out=dict(data);text=out.get('enc_bus_clear_hex','-')
    out.update(enc_bus_clear_record=None,enc_bus_clear_decode_valid=1)
    if text=='-':return out
    try:
        b=bytes.fromhex(text);peer=int(out.get('mc_fw_build',0))
        if (peer not in (2026102708,2026102710,2026102812,2026102902,2026103016) or len(b)!=43 or b[:4]!=bytes((0x55,0xaa,0xde,1)) or
            struct.unpack_from('<I',b,6)[0]!=peer or current_crc32c(b[:39])!=int.from_bytes(b[39:],'little') or
            not 1<=b[4]<=6 or b[5]>9 or any(x>3 for x in b[10:13]) or b[13] or any(b[26:39]) or
            int.from_bytes(b[14:18],'little')>25000):raise ValueError('Invalid bus clear frame')
        result=b[4]
        if (result<=2 and b[12]!=3) or (result==1 and b[5]) or (result==2 and not b[5]):raise ValueError('Invalid bus clear result')
        parent=bytes.fromhex(out.get('enc_fault_first_hex','-'))
        if out.get('enc_fault_decode_valid')!=1 or crc32c(parent)!=int.from_bytes(b[22:26],'little'):raise ValueError('Wrong frozen parent')
        names={1:'I²C: линии освободились при переключении GPIO',2:'I²C: шина освобождена тактами SCL',3:'I²C: SDA осталась LOW после 9 тактов',4:'I²C: SCL не поднимается',5:'I²C: восстановление просрочено',6:'I²C: восстановление отменено'}
        out['enc_bus_clear_record']=dict(result=result,pulses=b[5],before_lines=b[10],gpio_release_lines=b[11],after_lines=b[12],duration_us=int.from_bytes(b[14:18],'little'),begin_cycles=int.from_bytes(b[18:22],'little'),parent_crc32c=b[22:26][::-1].hex(),summary_ru=names[result],read_only_target_registers=True)
    except (ValueError,TypeError,struct.error) as exc:
        out.update(enc_bus_clear_decode_valid=0,enc_bus_clear_error=str(exc))
    return out

def with_i2c_release(data):
    out=dict(data);records=[]
    for kind,(key,parent_key) in enumerate((('enc_release_first_hex','enc_fault_first_hex'),('enc_release_pwm_hex','enc_fault_pwm_hex'))):
        text=out.get(key,'-')
        if text=='-':continue
        try:
            if out.get('enc_fault_decode_valid')!=1:raise ValueError('Invalid parent capture')
            records.append(decode_i2c_release(bytes.fromhex(text),bytes.fromhex(out.get(parent_key,'-')),int(out.get('mc_fw_build',0)),kind))
        except (ValueError,TypeError,struct.error) as exc:
            out.update(enc_release_decode_valid=0,enc_release_records=[],enc_release_status='Ошибка дополнения PE=0: '+str(exc));return out
    selected=next((r for r in records if r['kind']=='first_with_pwm'),records[0] if records else None)
    out.update(enc_release_decode_valid=1,enc_release_records=records,
        enc_release_status=selected['summary_ru'] if selected else 'Ожидание захвата после PE=0')
    return out


def decode_i2c_wire(raw, parent_raw=None):
    if len(raw)!=1072:raise ValueError('Wrong I2C waveform length')
    w=[int.from_bytes(raw[i:i+4],'little') for i in range(0,48,4)]
    magic,fmt,size,peer,parent,hz,period,n,freeze,request,gpio,flags=w
    if (magic!=0x31574349 or fmt!=1 or size!=1072 or peer!=2026102812 or
        hz!=170000000 or period!=20 or not 0<=n<=4096 or flags&~15 or
        bool(flags&1)!=(n==4096) or flags&12 not in (4,8)):
        raise ValueError('Unsupported I2C waveform header')
    manual=bool(flags&4)
    if manual:
        if parent:raise ValueError('Manual waveform must have no fault parent')
    else:
        if parent_raw is None or len(parent_raw)!=160 or crc32c(parent_raw)!=parent:
            raise ValueError('PWM waveform parent not yet received or CRC mismatch')
        decode(parent_raw,peer,1)
        if int.from_bytes(parent_raw[4:8],'little')!=peer or not int.from_bytes(parent_raw[64:68],'little')&32768:
            raise ValueError('Wrong peer or inactive PWM parent')
        if int.from_bytes(parent_raw[12:16],'little')!=request:raise ValueError('Wrong event timestamp')
    samples=[(raw[48+i//4]>>((i%4)*2))&3 for i in range(n)]
    if any(((raw[48+i//4]>>((i%4)*2))&3) for i in range(n,4096)):
        raise ValueError('Nonzero unsampled positions')
    lag=(freeze-request)&0xffffffff
    edges=[];starts=[];stops=[];byte_values=[];bits=[];in_frame=False
    for i in range(1,n):
        old,new=samples[i-1],samples[i]
        if old==new:continue
        if (old&1) and (new&1) and bool(old&2)!=bool(new&2):
            if old&2:starts.append(i);bits=[];in_frame=True
            else:stops.append(i);bits=[];in_frame=False
        if not(old&1) and (new&1) and in_frame:
            bits.append(1 if new&2 else 0)
            if len(bits)==9:
                value=0
                for bit in bits[:8]:value=(value<<1)|bit
                byte_values.append(dict(sample=i,value=value,ack=bits[8]==0));bits=[]
        edges.append(dict(sample=i,scl=bool(new&1),sda=bool(new&2)))
    return dict(peer_build=peer,parent_crc32c=f'{parent:08x}',record_crc32c=f'{crc32c(raw):08x}',
      manual=manual,dma_error=bool(flags&2),full_history=bool(flags&1),samples=n,
      nominal_sample_hz=hz/period,nominal_history_us=n*period*1e6/hz,
      freeze_lag_us=lag*1e6/hz,freeze_gpio=gpio,freeze_cycles=freeze,request_cycles=request,
      starts=starts,stops=stops,bytes=byte_values,transitions=edges,
      digital_record_valid=not bool(flags&2) and n>0,hardware_timing_qualified=False,
      limitation='Digital GPIO samples at nominal timer cadence. DMA latency/jitter and analog voltage/rise time are not measured; sub-sample glitches may be missed.')

def with_i2c_wire(data):
    out=dict(data);out.update(enc_wire_decode_valid=1,enc_wire_record=None)
    text=out.get('enc_wire_hex','-')
    if text in ('-',None,''):return out
    try:
        raw=bytes.fromhex(text)
        if crc32c(raw)!=int(out.get('enc_wire_crc','-'),16):raise ValueError('Wrong waveform CRC')
        if int(out.get('mc_fw_build',0))!=2026102812:raise ValueError('Wrong live peer')
        parent=None
        if len(raw)>=48 and int.from_bytes(raw[44:48],'little')&8:
            if out.get('enc_fault_decode_valid')!=1:raise ValueError('Invalid parent fault')
            parent=bytes.fromhex(out.get('enc_fault_pwm_hex','-'))
        out['enc_wire_record']=decode_i2c_wire(raw,parent)
    except (TypeError,ValueError) as exc:
        out.update(enc_wire_decode_valid=0,enc_wire_error=str(exc))
    return out


def with_i2c_first_fault(data):
    out=dict(data or {});records=[]
    for kind,key in enumerate(('enc_fault_first_hex','enc_fault_pwm_hex')):
        raw=out.get(key,'-')
        if raw=='-':continue
        try:records.append(decode(bytes.fromhex(raw),int(out.get('mc_fw_build',0)),kind))
        except (ValueError,TypeError,struct.error):
            out['enc_fault_decode_valid']=0;out['enc_fault_records']=[];return out
    out['enc_fault_records']=records;out['enc_fault_decode_valid']=1
    out['enc_fault_capture_status']='Снимок первого сбоя сохранён' if records else 'Ожидание первого сбоя I²C'
    return with_i2c_wire(with_bus_clear(with_i2c_release(out)))


def with_zero_history(data):
    import struct
    import math
    data.update(mc_zero_history_valid=0,mc_zero_history=None,
                mc_zero_history_status='Ожидание истории блоков автонуля')
    if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102509,2026102510),(2026102513,2026102510),(2026102515,2026102510),(2026102516,2026102510),(2026102517,2026102510),(2026102518,2026102510),(2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102607,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704),(2026102705,2026102706),(2026102707,2026102708),(2026102709,2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026103015,2026103016)):
        return data
    value=data.get('mc_zero_history_hex','-')
    if value=='-':
        return data
    try:
        raw=bytes.fromhex(value)
        if len(raw)%43 or not 3<=len(raw)//43<=8:
            raise ValueError('invalid zero-history size')
        count=len(raw)//43
        blocks=[]
        for index in range(count):
            p=raw[43*index:43*(index+1)]
            if (p[:4]!=bytes((0x55,0xaa,0xd9,1)) or p[4:6]!=bytes((index,count))
                or int.from_bytes(p[6:10],'little')!=int(data['mc_fw_build'])
                or p[30:39]!=bytes((3,2,3,8,2,128,0,15,1)) or any(p[25:30])
                or current_crc32c(p[:39])!=int.from_bytes(p[39:43],'little')):
                raise ValueError('invalid zero-history packet/CRC')
            means=struct.unpack_from('<4H',p,10);spans=p[18:22]
            status,q7,path_bits=p[22:25];paths=path_bits&15;span_clipped=path_bits>>4
            stable=status&3;reject=status>>2
            if reject>15 or paths>15 or any(v>4095 for v in (*means,*spans)):
                raise ValueError('invalid zero-history block')
            why=[]
            if reject&1:why.append('оценка 3σ среднего больше 2 отсчётов')
            if reject&2:why.append('средний уровень вне 1600–2500')
            if reject&4:why.append('дрейф средних больше 2 отсчётов')
            if reject&8:why.append('сырой АЦП достиг границы диапазона')
            blocks.append(dict(block=index+1,means_adc=list(means),raw_spans_adc=list(spans),
                stable=stable,reject_flags=reject,failed_paths_mask=paths,
                failed_paths=[name for n,name in enumerate(('U1','V1','V2','W2')) if paths&(1<<n)],
                estimated_3sigma_mean_counts=round(3*math.sqrt(q7/128),3),
                uncertainty_quantized=True,uncertainty_lower_bound=q7==255,
                raw_spans_lower_bound_mask=span_clipped,
                variance_method='max(raw-sample mean variance, four64-sample-group mean variance)',reasons=why))
        data.update(mc_zero_history_valid=1,mc_zero_history=blocks,
            mc_zero_history_status='Блоки нуля: '+' | '.join(
                str(b['block'])+(': '+', '.join(b['reasons'])+' ['+'/'.join(b['failed_paths'])+']'
                    if b['reject_flags'] else ': стабилен '+str(b['stable'])+'/3') for b in blocks))
    except (ValueError,TypeError) as exc:
        data['mc_zero_history_status']='Ошибка истории автонуля: '+str(exc)
    return data


# Inserted in the frozen HMI server; historical decoders remain available.
# Embedded into the frozen HMI. Only native verified capabilities admit actuation.
RESEARCH_ORDER = ('VF_FIXED','FOC_FIXED','ADAPTIVE_PWM','FOC_CLASSICAL','AI_SHADOW','AI_ACTIVE','EXTREMUM_SEARCH')
RESEARCH_LABELS = {
    'VF_FIXED':'Скалярный V/f — старт/стоп и задания частоты',
    'FOC_FIXED':'Векторный FOC с фиксированным потоком',
    'ADAPTIVE_PWM':'Адаптивный ШИМ',
    'FOC_CLASSICAL':'FOC с классической оптимизацией потока',
    'AI_SHADOW':'ИИ — расчёт предложения без управления',
    'AI_ACTIVE':'ИИ — управление через ограничения',
    'EXTREMUM_SEARCH':'Ограниченный поиск экстремума',
}
RESEARCH_BLOCKS = {
    'FOC_FIXED':('FOC_KERNEL_AND_MOTOR_MODEL_REQUIRED','Нужны действующий FOC-контур, измеренные Rr/Lm/индуктивности и проверка наблюдателя.'),
    'ADAPTIVE_PWM':('ADAPTIVE_PWM_PORT_AND_ADC_QUALIFICATION_REQUIRED','Алгоритм из модели не перенесён; окна АЦП проверены для фиксированных 16 кГц.'),
    'FOC_CLASSICAL':('QUALIFIED_FOC_REQUIRED','Сначала нужен проверенный FOC и идентифицированная модель потерь.'),
    'AI_SHADOW':('TRAINED_MODEL_REQUIRED','Пока есть офлайн-инструменты обучения; модели, обученной на новых опытах АИР, нет.'),
    'AI_ACTIVE':('QUALIFIED_FOC_AND_AI_POLICY_REQUIRED','Нужны проверенный FOC, обученная политика и проверка ограничений.'),
    'EXTREMUM_SEARCH':('QUALIFIED_BASELINE_AND_POWER_MEASUREMENT_REQUIRED','Нужны пригодная базовая система и измерение активной мощности; RMS токов её не заменяет.'),
}


def research_catalog(data):
    known=(data.get('fw_build'),data.get('mc_fw_build'))==(2026103015,2026103016)
    native=known and data.get('research_native_valid')==1 and data.get('research_native_caps')==15
    rows=[]
    for name in RESEARCH_ORDER:
        ready=native and (name=='VF_FIXED' or name in ('FOC_FIXED','ADAPTIVE_PWM') and data.get('algorithm_qualification')==7)
        if name=='FOC_FIXED' and native and data.get('algorithm_qualification')==128:
            ready=bool(data.get('foc_experiment_flags',0)&1) and not data.get('foc_timing_fault',0)
        if ready:code,text='',('Расчётный FOC: только0–5Гц,5сек,без нагрузки; скорость оценочная.' if name=='FOC_FIXED' and data.get('algorithm_qualification')==128 else 'Алгоритм доступен; перед пуском проверяются питание, токи и защиты.')
        elif name=='VF_FIXED':code,text='NATIVE_CAPABILITIES_UNAVAILABLE','Нет свежего подтверждения режима от Nucleo.'
        elif name in ('FOC_FIXED','ADAPTIVE_PWM'):code,text='PHYSICAL_FOC_QUALIFICATION_REQUIRED','Код собран и проверен на модели; нужны идентификация двигателя, проверка ампер и времени расчёта на MCU.'
        else:code,text=RESEARCH_BLOCKS[name]
        rows.append(dict(id=name,label=RESEARCH_LABELS[name],hardware_ready=ready,
                         status='available' if ready else 'blocked',reason_code=code,reason=text))
    return rows


def with_research_suite(data):
    if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026103015,2026103016):return data
    data['research_algorithms']=research_catalog(data)
    data['research_suite_version']=1
    data['research_actuator_algorithm']={1:'VF_FIXED',2:'FOC_FIXED',3:'ADAPTIVE_PWM'}.get(data.get('algorithm_selected'))
    data['research_speed_source']='current_model_estimate'
    data['research_speed_is_measured']=False
    data['research_program_autostart']=False
    estimated=data.get('algorithm_qualification')==128
    data['algorithm_profile_kind']='calculated_experimental' if estimated else 'identified' if data.get('algorithm_qualification')==7 else 'unqualified'
    data['research_missing_motor_parameters']=[] if estimated else ['Rr','Lls','Llr','Lms','Imagn']
    data['foc_experiment_max_hz']=5 if estimated else None
    data['foc_experiment_runlimit_s']=5 if estimated else None
    data['foc_timing_ready']=estimated and bool(data.get('foc_experiment_flags',0)&1) and not data.get('foc_timing_fault',0)
    data['research_rotation_feedback_valid']=False
    return data


def with_current_only_profile(data):
    if (data.get('fw_build'), data.get('mc_fw_build')) not in ((2026102901,2026102902),(2026103015,2026103016)):
        return data
    data.update(research_profile='air56b2_current_only', configured_load_condition='unloaded',
                enc_source='disabled', enc_enabled=0, enc_ok=0, enc_speed_ok=0,
                enc_bus_ok=0, enc_rpm=None, enc_deg=None, enc_raw=None,
                speed_measured_rpm=None, speed_estimated_rpm=None,
                speed_estimate_valid=0, speed_source='unavailable',
                ai_control_enabled=False, rotation_labels_available=False)
    # Frequency is the electrical field reference, never a measured rotor speed.
    data['field_frequency_hz'] = (data.get('mc_frequency_reference_hz')
                                 if data.get('mc_frequency_reference_valid') == 1 else None)
    return data


def with_motor_controller_aliases(data: dict) -> dict:
    """Publish mc_* as the canonical API while retaining bp_* compatibility."""
    for key, value in list(data.items()):
        if key.startswith("mc_") and key not in ("mc_capabilities", "mc_supported_modes"):
            data[f"bp_{key[3:]}"] = value
    for key, value in list(data.items()):
        if key.startswith("bp_"):
            data.setdefault(f"mc_{key[3:]}", value)
    data["hmi_local_stop_latched"] = local_stop_latched(data)
    data["mc_fault_detail"] = motor_fault_detail(data)
    if _as_int(data, "bp_mcsdk_telemetry", 0) == 1:
        data["mc_current_telemetry_valid"] = 0
        data["mc_current_telemetry_source"] = ("not_acquired_mcsdk_backend"
            if data.get("uno_local_adc_acquired") == 0 else "uno_q_local_adc_unqualified")
        data=with_observer_trace(with_i2c_first_fault(with_zero_history(with_adc_peak(with_shunt_currents(data)))))
    return with_research_suite(with_current_only_profile(data))


MC_FAULT_REASONS = {
    0: "NONE", 1: "CRC", 2: "PROTOCOL_VERSION", 3: "ENABLE_REPLAY",
    4: "ESTOP", 5: "SERVICE_FIELD", 6: "COMMAND_REJECTED",
    7: "FREQUENCY_REJECTED", 8: "MCSDK_FAULT", 9: "BUS_OUT_OF_RANGE",
    10: "START_REJECTED", 11: "UART_TX_FAILED", 12: "UART_RX_ERROR",
    13: "LINK_TIMEOUT", 14: "RX_BUFFER_OVERFLOW",
}
MCSDK_FAULT_BITS = {
    0x0001: "MC_DURATION", 0x0002: "MC_OVER_VOLT", 0x0004: "MC_UNDER_VOLT",
    0x0008: "MC_OVER_TEMP", 0x0010: "MC_START_UP", 0x0020: "MC_SPEED_FDBK",
    0x0040: "MC_OVER_CURR", 0x0080: "MC_SW_ERROR", 0x0400: "MC_DP_FAULT",
}


def motor_fault_detail(data: dict) -> str:
    current = "current=LOCAL_STOP_PC13; " if local_stop_latched(data) else ""
    if _as_int(data, "mc_diag_valid", 0) != 1:
        return current + "cause unavailable in installed firmware"
    reason = _as_int(data, "mc_fault_reason", -1)
    label = MC_FAULT_REASONS.get(reason, f"UNKNOWN_REASON_{reason}")
    uart = _as_int(data, "mc_uart_error_flags", 0)
    uart_names = [name for bit, name in ((1, "PE"), (2, "FE"), (4, "NE"), (8, "ORE")) if uart & bit]
    masks = []
    for field in ("mc_fault_current_mask", "mc_fault_occurred_mask"):
        mask = _as_int(data, field, 0)
        names = [name for bit, name in MCSDK_FAULT_BITS.items() if mask & bit]
        unknown = mask & ~sum(MCSDK_FAULT_BITS)
        if unknown:
            names.append(f"UNKNOWN_BITS_0x{unknown:04X}")
        masks.append(f"0x{mask:04X}[{'|'.join(names) or 'NONE'}]")
    return (current + f"first={label} UART={'|'.join(uart_names) or 'NONE'} "
            f"MCSDK_current={masks[0]} MCSDK_occurred={masks[1]} "
            f"state={_as_int(data, 'mc_fault_motor_state', -1)} "
            f"seq={_as_int(data, 'mc_fault_sequence', -1)} "
            f"TX_status={_as_int(data, 'mc_fault_tx_status', 0)} "
            f"last_bad={MC_FAULT_REASONS.get(_as_int(data, 'mc_last_bad_reason', 0), 'UNKNOWN') if _as_int(data, 'mc_last_bad_valid', 0) == 1 else 'UNAVAILABLE'} "
            f"last_UART_flags=0x{_as_int(data, 'mc_last_uart_error_flags', 0):02X} "
            f"last_TX_status={_as_int(data, 'mc_last_tx_status', 0)}")


class MotorFaultRecorder:
    """Bounded, observational flight recorder; never sends control commands."""

    FIELDS = (
        "ts", "state", "mode", "pwm", "estop", "vdc", "freq", "freq_cmd",
        "fw_build", "mc_fw_build", "mc_status", "mc_fault", "mc_age_ms",
        "mc_seq", "mc_good_cnt", "mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
        "mc_vbus_raw", "mc_vbus_age_ms", "mc_vbus_valid", "mc_softstart_ready",
        "mc_temp_c", "mc_temp_fault", "mc_temp_age_ms", "mc_current_telemetry_valid",
        "mc_diag_valid", "mc_fault_reason", "mc_uart_error_flags", "mc_fault_motor_state",
        "mc_fault_current_mask", "mc_fault_occurred_mask", "mc_fault_sequence",
        "mc_fault_tx_status", "mc_last_bad_valid", "mc_last_bad_reason",
        "mc_last_uart_error_flags", "mc_last_tx_status", "enc_bus_ok", "enc_ok",
        "enc_speed_ok", "enc_reads", "enc_errors", "enc_io_error", "enc_age_ms",
        "enc_status", "hmi_hv_armed", "hmi_operator_heartbeat_age_s",
        "hmi_local_stop_latched",
        "uno_tx_all_max_gap_us",
        "uno_tx_last_gap_us",
        "uno_tx_gaps_over_watchdog",
        "uno_rx_poll_gap_max_ms",
        "uno_tx_call_max_us",
        "uno_rpc_max_us",
        "uno_rx_dropped",
        "uno_rx_hw_errors",
        "uno_rx_hw_flags",
        "uno_rx_high_water",
        "uno_rx_pending",
        "uno_rx_rejected_ms",
        "uno_rx_rejected_hex",
        "uno_tx_short_writes",
        "uno_tx_count",
        "uno_rx_count",
        "mc_transport_fault",
        "mc_break_rx_good",
        "mc_break_rx_bad",
        "mc_break_reject_record_valid", "mc_break_reject_reason", "mc_break_reject_code",
        "mc_break_reject_ms", "mc_break_reject_peer_fw", "mc_break_reject_fresh_off",
        "mc_break_reject_bp_status", "mc_break_reject_pwm", "mc_break_reject_rsp_age_ms",
        "mc_break_reject_good_before", "mc_break_reject_packet_hex",
    )
    KEY_FIELDS = (
        "mc_fault", "hmi_local_stop_latched",
        "mc_fw_build", "mc_diag_valid", "mc_fault_reason", "mc_uart_error_flags",
        "mc_fault_current_mask", "mc_fault_occurred_mask", "mc_fault_motor_state",
        "mc_fault_sequence", "mc_fault_tx_status", "mc_bad_cnt",
        "mc_last_bad_reason", "mc_last_uart_error_flags", "mc_last_tx_status",
    )

    def __init__(self) -> None:
        self._history = deque(maxlen=64)
        self._key = None
        self._event_id = ""
        self._boot_key = None
        self._boot_tick = None
        self._event_summary = ""
        self._last_sample = -math.inf
        self._post_until = -math.inf
        self._lock = threading.Lock()

    @staticmethod
    def compact(data: dict, now: float) -> dict:
        sample = {"observed_monotonic_s": round(now, 6), "observed_unix_s": _now_ts()}
        for key in MotorFaultRecorder.FIELDS:
            value = data.get(key)
            if key.startswith("mc_") and value is None:
                value = data.get("bp_" + key[3:])
            if type(value) in (str, bool, int) or value is None:
                sample[key] = value
            elif type(value) is float and math.isfinite(value):
                sample[key] = value
            else:
                sample[key] = None
        sample["hmi_local_stop_latched"] = local_stop_latched(data)
        return sample

    def observe(self, data: dict, now: Optional[float] = None) -> list[str]:
        now = time.monotonic() if now is None else now
        sample = self.compact(data, now)
        valid = _as_int(data, "mc_diag_valid", 0) == 1
        active = _as_int(data, "bp_fault", 0)
        first_reason = _as_int(data, "mc_fault_reason", 0)
        has_cause = bool(first_reason or active or local_stop_latched(data))
        key = tuple(sample.get(k) for k in self.KEY_FIELDS) if has_cause else None
        if key is not None and not valid:
            key += (active,)
        lines = []
        with self._lock:
            boot=data.get('native_boot',{})
            if boot.get('available') and boot.get('fresh'):
                boot_key=(data.get('linux_boot_id'),boot.get('firmware'),boot.get('retained_sequence'),boot.get('early_record_crc'))
                boot_tick=boot.get('native_tick_ms')
                if boot_key!=self._boot_key or (self._boot_tick is not None and boot_tick<self._boot_tick and self._boot_tick-boot_tick<0x80000000):
                    lines.append('MC_BOOT_RECORD '+json.dumps(dict(linux_boot_id=data.get('linux_boot_id'),observed_unix_s=_now_ts(),record=boot),separators=(',',':'),allow_nan=False))
                self._boot_key=boot_key;self._boot_tick=boot_tick
            changed = key is not None and key != self._key
            self._key = key
            if changed:
                recent_bad = (_as_int(data, "mc_last_bad_valid", 0) == 1
                              and _as_int(data, "bp_bad_cnt", 0) > 0
                              and _as_int(data, "mc_last_bad_reason", 0) != 0)
                reason = _as_int(data, "mc_last_bad_reason", 0) if recent_bad else first_reason
                flags = _as_int(data, "mc_last_uart_error_flags" if recent_bad else "mc_uart_error_flags", 0)
                uart_names = [name for bit, name in ((1, "PE"), (2, "FE"), (4, "NE"), (8, "ORE")) if flags & bit]
                label = MC_FAULT_REASONS.get(reason, "UNKNOWN") if valid else "DIAGNOSTICS_UNAVAILABLE"
                self._event_id = secrets.token_hex(8)
                current = "current=LOCAL_STOP_PC13; first=" if local_stop_latched(data) else ""
                self._event_summary = current + f"{label}; UART={'|'.join(uart_names) or 'NONE'}; physical source not identified"
                before = [s for s in self._history if 0 <= now - s["observed_monotonic_s"] <= 5]
                payload = {
                    "schema": "mic_ai.fault_context.v1", "event_id": self._event_id,
                    "phase": "fault", "summary": self._event_summary,
                    "physical_source_identified": False,
                    "controller_masks_are_first_fault_snapshot": True,
                    "time_basis": "Linux observation, not exact MCU interrupt timestamp",
                    "detail": motor_fault_detail(data), "before": before, "at": sample,
                    "history_samples": len(before), "post_window_s": 5,
                    "sampling_note": "observed RPC snapshots; intervening transients are not measured",
                }
                lines.append("MC_FAULT_CONTEXT " + json.dumps(payload, separators=(",", ":"), allow_nan=False))
                self._post_until = now + 5
            transition = bool(self._history and any(
                sample.get(field) != self._history[-1].get(field)
                for field in ("state", "pwm", "mc_fault", "enc_bus_ok", "enc_errors",
                              "uno_rx_dropped", "uno_rx_hw_errors", "uno_rx_hw_flags",
                              "uno_tx_gaps_over_watchdog", "mc_transport_fault")
            ))
            if changed or transition or now - self._last_sample >= .19:
                if not changed and now <= self._post_until:
                    lines.append("MC_FAULT_CONTEXT " + json.dumps({
                        "schema": "mic_ai.fault_context.v1", "event_id": self._event_id,
                        "phase": "after", "at": sample,
                    }, separators=(",", ":"), allow_nan=False))
                self._history.append(sample)
                self._last_sample = now
        return lines

    def snapshot(self) -> dict:
        with self._lock:
            return {"hmi_fault_log_schema": "mic_ai.fault_context.v1",
                    "hmi_last_fault_event_id": self._event_id,
                    "hmi_last_fault_summary": self._event_summary,
                    "hmi_fault_physical_source_identified": 0}


def supported_modes_from_caps(capabilities: int) -> list[str]:
    modes: list[str] = []
    if capabilities & MC_CAP_VF:
        modes.append("VF")
    if capabilities & MC_CAP_FOC:
        modes.append("FOC")
    if capabilities & MC_CAP_MIC:
        modes.append("MIC")
    return modes


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _vbus_calibration_identity(data: dict) -> dict:
    return {
        "fw_build": _as_int(data, "fw_build", -1),
        "mc_fw_build": _as_int(data, "mc_fw_build", -1),
        "rpc_schema_version": _as_int(data, "rpc_schema_version", -1),
        "mc_capabilities": _as_int(data, "mc_capabilities", -1),
        "mc_mcsdk_telemetry": _as_int(data, "bp_mcsdk_telemetry", 0),
    }


def _vbus_calibration_identity_matches(stored: dict, current: dict) -> bool:
    if stored == current:
        return True
    # Audited diagnostic-only updates retain the same Vbus word (0.1 V/LSB).
    # Keep the original capture identities; do not authorize unknown firmware.
    firmware_pairs = {
        (2026092901, 2026100601), (2026100612, 2026100601),
        (2026100701, 2026100601), (2026100701, 2026100701),
        (2026100702, 2026100601), (2026100702, 2026100701), (2026100702, 2026100702),
        (2026100703, 2026100601), (2026100703, 2026100701),
        (2026100703, 2026100702), (2026100703, 2026100703),
        (2026100704, 2026100601), (2026100704, 2026100701),
        (2026100704, 2026100702), (2026100704, 2026100703), (2026100704, 2026100704),
        (2026100705, 2026100704), (2026100705, 2026100705),
        (2026100706, 2026100705),
        (2026100707, 2026100707),
        (2026100708, 2026100707), (2026100708, 2026100708),
        (2026100709, 2026100708), (2026100709, 2026100710), (2026100709, 2026100801),
        (2026100802, 2026100801),
        (2026100803, 2026100801),
        (2026100804, 2026100801),
        (2026101001, 2026100801),
        (2026101002, 2026100801),
        (2026101004, 2026101003),
        (2026101005, 2026101003),
        (2026101007, 2026101006),
        (2026101008, 2026101006),
        RX_SNAPSHOT_TRIAL_PAIR,
        BOOT_TRIAL_PAIR,
        (2026101108, 2026101102),
        # Retained measurement scale/divider; corrected IIR bias was audited.
        # Same stand: zero check0.32/0 V and working check316/319 V (20 samples).
        # Keep original capture identities and points. Unknown/fixture pairs fail.
        (2026101411, 2026101410),
        (2026101413, 2026101412),
        (2026101415, 2026101414),
        (2026101501, 2026101502),
        (2026101503, 2026101502),
        (2026101505, 2026101504),
        (2026101507, 2026101506),
        (2026101703, 2026101702),
        (2026101711, 2026101710),
        (2026101803, 2026101802),
        (2026101805, 2026101804),
        (2026101807, 2026101806),
        (2026101809, 2026101808),
        (2026101811, 2026101810),
        (2026101813, 2026101812),
        (2026102001, 2026102002),
        (2026102101, 2026102102),
        (2026102103, 2026102104),
        (2026102401, 2026102402),
        (2026102403, 2026102402),
        (2026102405, 2026102406),
        (2026102407, 2026102408),
        (2026102409, 2026102410),
        (2026102411, 2026102412),
        (2026102501, 2026102502),
        (2026102503, 2026102502),
        (2026102505, 2026102506),
        (2026102507, 2026102508),
        (2026102509, 2026102510),
        (2026102513, 2026102510), (2026102515, 2026102510), (2026102516, 2026102510), (2026102517, 2026102510), (2026102518, 2026102510), (2026102601, 2026102602),(2026102603, 2026102602),(2026102605, 2026102604),(2026102607, 2026102604),(2026102609, 2026102604),(2026102701, 2026102702),(2026102703, 2026102704),(2026102705, 2026102706),(2026102707, 2026102708),(2026102709, 2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026102921,2026102922), (2026102931,2026102932), (2026102933,2026102934), (2026102935,2026102936), (2026102937,2026102938), (2026102939,2026103016), (2026103015,2026103016),
    }
    contract = {
        "rpc_schema_version": 3,
        "mc_capabilities": MC_CAP_VF,
        "mc_mcsdk_telemetry": 1,
    }
    expected_keys = set(contract) | {"fw_build", "mc_fw_build"}
    return (
        set(stored) == expected_keys
        and set(current) == expected_keys
        and isinstance(stored["fw_build"], int) and isinstance(stored["mc_fw_build"], int)
        and isinstance(current["fw_build"], int) and isinstance(current["mc_fw_build"], int)
        and (stored["fw_build"], stored["mc_fw_build"]) in firmware_pairs
        and (current["fw_build"], current["mc_fw_build"]) in firmware_pairs
        and all(stored[key] == value and current[key] == value
                for key, value in contract.items())
    )


class VbusCalibrationStore:
    SCHEMA = "mic_ai.vbus_calibration.v1"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = os.path.abspath(os.path.expanduser(path)) if path else None
        self._lock = threading.RLock()
        self._record: dict = {}
        self._load_error = ""
        self._load()

    @staticmethod
    def _digest(record: dict) -> str:
        payload = dict(record)
        payload.pop("integrity_sha256", None)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as source:
                record = json.load(source)
            if not isinstance(record, dict) or record.get("schema") != self.SCHEMA:
                raise ValueError("unsupported calibration schema")
            expected = str(record.get("integrity_sha256", ""))
            if not expected or not secrets.compare_digest(expected, self._digest(record)):
                raise ValueError("calibration integrity check failed")
            self._record = record
        except Exception as exc:
            self._record = {}
            self._load_error = str(exc)

    def _save_locked(self) -> None:
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, mode=0o700, exist_ok=True)
        self._record["integrity_sha256"] = self._digest(self._record)
        temporary = f"{self.path}.tmp.{os.getpid()}.{threading.get_ident()}"
        try:
            with open(temporary, "w", encoding="utf-8", newline="\n") as target:
                json.dump(self._record, target, indent=2, sort_keys=True, ensure_ascii=True)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

    def _evaluate_locked(self, status: Optional[dict] = None) -> tuple[bool, str]:
        if VBUS_HV_CALIBRATION_VALID:
            return True, "compile-time calibration override"
        if self._load_error:
            return False, f"stored calibration rejected: {self._load_error}"
        if not self._record:
            return False, "zero-point capture is required"
        if self._record.get("schema") != self.SCHEMA:
            return False, "stored calibration schema is invalid"
        points = self._record.get("points")
        if not isinstance(points, dict):
            return False, "stored calibration points are missing"
        zero = points.get("zero")
        high = points.get("high")
        if not isinstance(zero, dict):
            return False, "zero-point capture is required"
        if not isinstance(high, dict):
            return False, "known-HV capture is required"
        identity = self._record.get("identity")
        if not isinstance(identity, dict):
            return False, "calibration identity is missing"
        if (
            _as_int(identity, "fw_build", -1) <= 0
            or _as_int(identity, "mc_fw_build", -1) <= 0
            or _as_int(identity, "rpc_schema_version", -1) < 3
            or _as_int(identity, "mc_mcsdk_telemetry", 0) != 1
        ):
            return False, "calibration identity is incomplete"
        if status is not None and not _vbus_calibration_identity_matches(
            identity, _vbus_calibration_identity(status)
        ):
            return False, "firmware or telemetry identity changed; recalibration is required"
        try:
            meter_span = float(high.get("meter_vdc")) - float(zero.get("meter_vdc"))
            reported_span = float(high.get("mc_vdc_mean")) - float(zero.get("mc_vdc_mean"))
        except (TypeError, ValueError):
            return False, "calibration point values are invalid"
        if not (math.isfinite(meter_span) and math.isfinite(reported_span)):
            return False, "calibration point values are invalid"
        if meter_span < (VBUS_CAL_HV_MIN_METER_V - VBUS_CAL_ZERO_MAX_METER_V) or reported_span <= 0.0:
            return False, "calibration span is invalid"
        gain = meter_span / reported_span
        if gain < 0.97 or gain > 1.03:
            return False, f"calibration gain mismatch: {gain:.5f}"
        return True, "two-point Vbus verification passed"

    def is_valid(self, status: Optional[dict] = None) -> bool:
        with self._lock:
            valid, _ = self._evaluate_locked(status)
            return valid

    def snapshot(self, status: Optional[dict] = None) -> dict:
        with self._lock:
            valid, reason = self._evaluate_locked(status)
            points = self._record.get("points", {}) if isinstance(self._record, dict) else {}
            zero = points.get("zero") if isinstance(points, dict) else None
            high = points.get("high") if isinstance(points, dict) else None
            return {
                "valid": bool(valid),
                "reason": reason,
                "zero_captured": isinstance(zero, dict),
                "high_captured": isinstance(high, dict),
                "zero_meter_vdc": zero.get("meter_vdc") if isinstance(zero, dict) else None,
                "zero_mc_vdc": zero.get("mc_vdc_mean") if isinstance(zero, dict) else None,
                "high_meter_vdc": high.get("meter_vdc") if isinstance(high, dict) else None,
                "high_mc_vdc": high.get("mc_vdc_mean") if isinstance(high, dict) else None,
                "updated_at": self._record.get("updated_at") if isinstance(self._record, dict) else None,
            }

    def record_capture(self, capture: dict, status: dict) -> tuple[bool, str, dict]:
        meter_vdc = capture.get("meter_vdc")
        try:
            meter = float(meter_vdc)
            reported = float(capture["mc_vdc"]["mean"])
            reported_std = float(capture["mc_vdc"]["std"])
            raw_mean = float(capture["mc_vbus_raw"]["mean"])
            bad_min = int(capture["mc_bad"]["min"])
            bad_max = int(capture["mc_bad"]["max"])
            sample_count = int(capture["mc_vdc"]["samples"])
        except (KeyError, TypeError, ValueError):
            return False, "calibration capture is incomplete", self.snapshot(status)
        if sample_count != VBUS_CAL_CAPTURE_SAMPLES:
            return False, (
                f"calibration capture requires {VBUS_CAL_CAPTURE_SAMPLES} samples; got {sample_count}"
            ), self.snapshot(status)
        if not all(math.isfinite(value) for value in (meter, reported, reported_std, raw_mean)):
            return False, "calibration capture contains non-finite values", self.snapshot(status)
        if _as_int(status, "bp_mcsdk_telemetry", 0) != 1 or _as_int(status, "bp_vbus_valid", 0) != 1:
            return False, "MCSDK Vbus telemetry is not valid", self.snapshot(status)
        if _as_int(status, "mc_fw_build", 0) <= 0:
            return False, "Nucleo firmware identity is not available", self.snapshot(status)
        if abs((raw_mean * 0.1) - reported) > 1.0:
            return False, "MCSDK Vbus telemetry fields disagree", self.snapshot(status)
        if bad_min != bad_max:
            return False, "motor-controller UART error counter changed during capture", self.snapshot(status)

        if 0.0 <= meter <= VBUS_CAL_ZERO_MAX_METER_V:
            kind = "zero"
            if reported < 0.0 or reported > VBUS_CAL_ZERO_MAX_REPORTED_V:
                return False, f"reported zero-bus voltage is too high: {reported:.2f} V", self.snapshot(status)
            if reported_std > VBUS_CAL_ZERO_MAX_STD_V:
                return False, f"zero-point capture is unstable: std={reported_std:.3f} V", self.snapshot(status)
            if abs(reported - meter) > VBUS_CAL_ZERO_MAX_METER_V:
                return False, f"zero-point mismatch is too large: meter={meter:.2f} V, MCSDK={reported:.2f} V", self.snapshot(status)
        elif VBUS_CAL_HV_MIN_METER_V <= meter <= VBUS_CAL_HV_MAX_METER_V:
            kind = "high"
            if bad_max != 0:
                return False, "clear motor-controller UART error counters before known-HV capture", self.snapshot(status)
            allowed_error = max(VBUS_CAL_HV_MAX_ERROR_FLOOR_V, meter * VBUS_CAL_HV_MAX_ERROR_PERCENT / 100.0)
            if abs(reported - meter) > allowed_error:
                return False, (
                    f"known-HV mismatch is too large: meter={meter:.2f} V, "
                    f"MCSDK={reported:.2f} V, allowed={allowed_error:.2f} V"
                ), self.snapshot(status)
            allowed_std = max(VBUS_CAL_HV_MAX_STD_FLOOR_V, meter * VBUS_CAL_HV_MAX_STD_PERCENT / 100.0)
            if reported_std > allowed_std:
                return False, f"known-HV capture is unstable: std={reported_std:.3f} V", self.snapshot(status)
        else:
            return False, "meter voltage must be 0..2 V for zero or 250..360 V for known HV", self.snapshot(status)

        identity = _vbus_calibration_identity(status)
        point = {
            "kind": kind,
            "captured_at": _now_ts(),
            "meter_vdc": round(meter, 6),
            "mc_vdc_mean": round(reported, 6),
            "mc_vdc_std": round(reported_std, 6),
            "mc_vbus_raw_mean": round(raw_mean, 6),
            "samples": sample_count,
        }
        with self._lock:
            if kind == "zero":
                self._record = {
                    "schema": self.SCHEMA,
                    "updated_at": _now_ts(),
                    "identity": identity,
                    "points": {"zero": point},
                }
                self._load_error = ""
                self._save_locked()
                valid, reason = self._evaluate_locked(status)
            else:
                points = self._record.get("points", {}) if isinstance(self._record, dict) else {}
                stored_identity = self._record.get("identity")
                if (not isinstance(stored_identity, dict)
                        or not _vbus_calibration_identity_matches(stored_identity, identity)
                        or not isinstance(points.get("zero"), dict)):
                    valid, reason = False, "capture a new zero point before the known-HV point"
                    return valid, reason, self.snapshot(status)
                points["high"] = point
                self._record["points"] = points
                self._record["updated_at"] = _now_ts()
                self._save_locked()
                valid, reason = self._evaluate_locked(status)
            snapshot = self.snapshot(status)
        return valid or kind == "zero", reason, snapshot

    def reset(self) -> dict:
        with self._lock:
            self._record = {}
            self._load_error = ""
            if self.path:
                try:
                    os.remove(self.path)
                except FileNotFoundError:
                    pass
            return self.snapshot()


def _cmd_tokens(cmd: str) -> list[str]:
    return cmd.strip().split()


def _cmd_head(cmd: str) -> str:
    parts = _cmd_tokens(cmd)
    return parts[0].upper() if parts else ""


def _on_off_arg(parts: list[str], index: int = 1) -> Optional[bool]:
    if len(parts) <= index:
        return None
    val = parts[index].strip().upper()
    if val in ("1", "ON", "TRUE", "YES"):
        return True
    if val in ("0", "OFF", "FALSE", "NO"):
        return False
    return None


def _positive_arg(parts: list[str], index: int) -> bool:
    if len(parts) <= index:
        return False
    try:
        return float(parts[index]) > 0.0001
    except (TypeError, ValueError):
        return False


def identification_point_complete(data,initial):
    """A completed native bounded measurement may precede the HTTP response.
    This never authorizes START and cannot acknowledge any protection fault.
    """
    if not data or not initial:return False
    if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026103015,2026103016):return False
    if data.get('algorithm_selected')!=4 or initial.get('algorithm_selected')!=4:return False
    if data.get('state')!='SAFE' or data.get('pwm')!=0 or data.get('bp_status',0x22)&0x22:return False
    if not 0<=data.get('mc_age_ms',99999)<300 or data.get('id_valid')!=1:return False
    if any(data.get(k)!=0 for k in ('estop','mc_fault_current_mask','mc_fault_occurred_mask','mc_transport_fault','id_fault')):return False
    if data.get('id_flags',0)&12!=12 or not data.get('id_result_crc'):return False
    if not initial.get('id_config_crc') or data.get('id_config_crc')!=initial.get('id_config_crc') or data.get('id_run_id')!=initial.get('id_run_id'):return False
    if data.get('run_id')!=((initial.get('run_id',-2)+1)&0xffffffff):return False
    elapsed=data.get('run_elapsed_ms',-1);duration=initial.get('id_duration_ms',0)
    return 2000<=duration<=10000 and duration<=elapsed<=duration+1500


def command_requests_start(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    return len(parts) == 1 and parts[0].upper() == "START"


def command_requests_service_output(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    if not parts:
        return False
    head = parts[0].upper()
    if head == "IOTEST":
        return _on_off_arg(parts) is True
    if head in ("MCFOC", "BPFOC"):
        return _on_off_arg(parts) is True
    if head in ("PFC", "PRECHARGE"):
        return _on_off_arg(parts) is True
    if head == "FAN":
        if len(parts) == 2:
            arg = parts[1].upper()
            if arg == "ON":
                return True
            if arg == "OFF":
                return False
            return _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return _positive_arg(parts, 2)
        return False
    if head == "BRAKE":
        if len(parts) == 2:
            if parts[1].upper() == "OFF":
                return False
            return _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return _positive_arg(parts, 2)
        return False
    return False


def command_releases_service_output(cmd: str) -> bool:
    parts = _cmd_tokens(cmd)
    if not parts:
        return False
    head = parts[0].upper()
    if head in ("IOTEST", "MCFOC", "BPFOC", "PFC", "PRECHARGE"):
        return _on_off_arg(parts) is False
    if head == "FAN":
        if len(parts) == 2:
            return parts[1].upper() == "OFF" or not _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return not _positive_arg(parts, 2)
    if head == "BRAKE":
        if len(parts) == 2:
            return parts[1].upper() == "OFF" or not _positive_arg(parts, 1)
        if len(parts) == 3 and parts[1].upper() in ("PWM", "DUTY"):
            return not _positive_arg(parts, 2)
    return False


def status_has_active_outputs(data: Optional[dict]) -> bool:
    if data is None:
        return True
    return bool(
        _as_int(data, "pwm", 1) != 0
        or _as_int(data, "precharge", 1) != 0
        or (_as_int(data, "bp_ext", 0xFF) & 0x0E) != 0
        or _as_int(data, "pfc", 1) != 0
        or _as_int(data, "brake", 1) != 0
        or _as_float(data, "brake_duty", 1.0) > 0.0001
        or _as_float(data, "fan_duty", 1.0) > 0.0001
        or _as_float(data, "bp_fan_duty", 1.0) > 0.0001
    )


class CommandGuardConfig:
    def __init__(
        self,
        max_vdc: float,
        allow_hv: bool = False,
        disabled: bool = False,
        bench_gate_url: str = "",
        bench_gate_runner: Optional[Callable[[Callable[[str], None], Optional[str]], bool]] = None,
        local_bench_gate: bool = False,
    ) -> None:
        self.max_vdc = max_vdc
        self.allow_hv = allow_hv
        self.disabled = disabled
        self.bench_gate_url = bench_gate_url
        self.bench_gate_runner = bench_gate_runner
        self.local_bench_gate = local_bench_gate


def start_bench_gate_check(cfg: CommandGuardConfig) -> tuple[bool, str]:
    if cfg.local_bench_gate:
        return True, "standalone live safety gate"
    logs: list[str] = []
    if cfg.bench_gate_runner is not None:
        ok = bool(cfg.bench_gate_runner(logs.append, cfg.bench_gate_url or None))
    elif start_allowed_by_bench_gate is not None:
        ok = bool(start_allowed_by_bench_gate(logs.append, url=cfg.bench_gate_url or None))
    else:
        ok = False
        logs.append("active_pwm_guard import failed")
    if ok:
        return True, "ok"
    detail = "; ".join(logs) if logs else "bench gate refused START"
    return False, f"bench gate blocked START: {detail}"


def validate_bench_gate_attestation(payload: object, now: Optional[float] = None) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "attestation payload is not an object"
    if payload.get("ready_for_active_pwm") is not True:
        return False, "attestation is not green"
    current = time.time() if now is None else float(now)
    try:
        issued_at = float(payload.get("issued_at"))
        expires_at = float(payload.get("expires_at"))
    except (TypeError, ValueError):
        return False, "attestation timestamps are missing"
    if not (math.isfinite(issued_at) and math.isfinite(expires_at)):
        return False, "attestation timestamps are invalid"
    if issued_at > current + 1.0:
        return False, "attestation was issued in the future"
    if current - issued_at > 10.0:
        return False, "attestation is stale"
    if expires_at < current:
        return False, "attestation has expired"
    if expires_at - issued_at > 10.0:
        return False, "attestation validity window is too long"
    return True, "ok"


def attested_bench_gate_runner(log_fn: Callable[[str], None], url: Optional[str]) -> bool:
    target = str(url or "").strip()
    if not target:
        log_fn("bench-gate attestation URL is missing")
        return False
    try:
        request = urllib.request.Request(target, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=12.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log_fn(f"bench-gate attestation request failed: {type(exc).__name__}: {exc}")
        return False
    ok, detail = validate_bench_gate_attestation(payload)
    if not ok:
        log_fn(f"bench-gate attestation rejected: {detail}")
    return ok


def _status_mc_bad(data: dict) -> int:
    values = [
        _as_int(data, key, 999999)
        for key in ("mc_bad_cnt", "mc_bad", "bp_bad_cnt", "bp_bad")
        if key in data
    ]
    if not values:
        return 999999
    return max(values)


def _status_vdc(data: dict) -> float:
    values: list[float] = []
    for key in ("vdc", "mc_vdc", "bp_vdc"):
        if key not in data:
            continue
        value = _as_float(data, key, float("nan"))
        if math.isfinite(value) and value >= 0.0:
            values.append(value)
    return max(values) if values else float("nan")


def _vbus_raw_for_voltage(vdc: float) -> float:
    span = float(VBUS_RAW_CAL - VBUS_RAW_ZERO_CAL)
    return float(VBUS_RAW_ZERO_CAL) + max(0.0, float(vdc)) * span / float(VBUS_RAW_CAL_V)


def raw_vbus_window_check(data: dict, min_vdc: float, max_vdc: float) -> tuple[bool, str]:
    if _as_float(data, "bp_vbus_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "raw DC bus telemetry is stale"
    if "bp_vbus_raw" not in data and "mc_vbus_raw" not in data:
        return False, "raw DC bus telemetry is missing"
    raw = _as_int(data, "bp_vbus_raw", -1)
    if _as_int(data, "bp_mcsdk_telemetry", 0) == 1:
        if _as_int(data, "bp_vbus_valid", 0) != 1:
            return False, "MCSDK DC bus telemetry is not valid"
        if raw < 0 or raw > 5000:
            return False, f"MCSDK DC bus telemetry is invalid: decivolts={raw}"
        direct_vdc = float(raw) * 0.1
        scaled_vdc = _status_vdc(data)
        if not math.isfinite(scaled_vdc) or abs(scaled_vdc - direct_vdc) > 1.0:
            return False, "MCSDK DC bus telemetry fields disagree"
        if direct_vdc < min_vdc or direct_vdc > max_vdc:
            return False, f"MCSDK DC bus is outside window: vdc={direct_vdc:.1f} V"
        return True, "ok"
    if raw < VBUS_RAW_MIN_VALID or raw > VBUS_RAW_MAX_VALID:
        return False, f"raw DC bus telemetry is invalid: raw={raw}"

    if max_vdc <= DEFAULT_CMD_GUARD_MAX_VDC:
        raw_min = VBUS_RAW_ZERO_CAL - VBUS_RAW_ZERO_LOW_MARGIN
        raw_max = math.ceil(_vbus_raw_for_voltage(max_vdc + VBUS_RAW_WINDOW_MARGIN_V))
        if raw < raw_min or raw > raw_max:
            label = "zero-bus" if max_vdc <= DEFAULT_LV_ARM_MAX_VDC else "low-voltage"
            return False, f"raw DC bus is outside the calibrated {label} window: raw={raw} expected={raw_min}..{raw_max}"
    if min_vdc >= DEFAULT_HV_ARM_MIN_VDC:
        raw_min = math.floor(_vbus_raw_for_voltage(min_vdc - VBUS_RAW_WINDOW_MARGIN_V))
        if raw < raw_min:
            return False, f"raw DC bus does not confirm an energized HV bus: raw={raw} expected>={raw_min}"
    return True, "ok"


def vbus_capture_precheck(data: Optional[dict], meter_vdc: Optional[float] = None) -> tuple[bool, str]:
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"
    if _as_float(data, "bp_vbus_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "DC bus telemetry is stale"
    if "bp_vbus_raw" not in data and "mc_vbus_raw" not in data:
        return False, "raw DC bus telemetry is missing"
    raw = _as_int(data, "bp_vbus_raw", -1)
    raw_max = 5000 if _as_int(data, "bp_mcsdk_telemetry", 0) == 1 else 4095
    if raw < 0 or raw > raw_max:
        return False, f"raw DC bus telemetry is invalid: raw={raw}"
    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "scaled DC bus telemetry is not readable"
    if _as_int(data, "bp_mcsdk_telemetry", 0) != 1 or _as_int(data, "bp_vbus_valid", 0) != 1:
        return False, "MCSDK Vbus telemetry is not valid"
    if _as_int(data, "bp_temp_valid", 0) != 1 or _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature protection is not healthy"
    if not math.isfinite(_as_float(data, "bp_temp_c", float("nan"))):
        return False, "heatsink temperature is not readable"
    for key in ("precharge", "pfc", "brake", "bp_ext"):
        if _as_int(data, key, 0) != 0:
            return False, f"output must be off during Vbus capture: {key}={_as_int(data, key, 0)}"
    zero_capture = meter_vdc is not None and 0.0 <= float(meter_vdc) <= VBUS_CAL_ZERO_MAX_METER_V
    if zero_capture:
        # MCSDK normally reports undervoltage while the bus is discharged. The
        # zero-point path may observe that fault, but still requires SAFE,
        # fresh telemetry, healthy temperature sensing and every output off.
        if vdc > VBUS_CAL_ZERO_MAX_REPORTED_V:
            return False, f"DC bus is too high for zero-point capture: vdc={vdc:.2f} V"
    else:
        if _as_int(data, "bp_fault", 255) != 0:
            return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
        if _status_mc_bad(data) != 0:
            return False, "motor-controller bad-frame counter is non-zero"
    return True, "ok"


def vbus_capture_summary(samples: list[dict], meter_vdc: Optional[float]) -> dict:
    def stats(values: list[float]) -> dict:
        count = len(values)
        mean = sum(values) / count
        variance = sum((value - mean) ** 2 for value in values) / count
        return {
            "samples": count,
            "mean": mean,
            "std": math.sqrt(variance),
            "min": min(values),
            "max": max(values),
        }

    raw_values = [float(_as_int(sample, "bp_vbus_raw", -1)) for sample in samples]
    vdc_values = [float(_status_vdc(sample)) for sample in samples]
    temp_values = [float(_as_float(sample, "bp_temp_c", float("nan"))) for sample in samples]
    bad_values = [float(_status_mc_bad(sample)) for sample in samples]
    return with_motor_controller_aliases({
        "timestamp": _now_ts(),
        "meter_vdc": meter_vdc,
        "outputs_commanded": False,
        "state": "SAFE",
        "pwm": 0,
        "bp_vbus_raw": stats(raw_values),
        "bp_vdc": stats(vdc_values),
        "bp_temp_c": stats(temp_values),
        "bp_bad": stats(bad_values),
    })


def _status_link_live(data: dict) -> bool:
    if data.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("mc_rsp_age_ms", "mc_age_ms", "bp_rsp_age_ms", "bp_age_ms"):
        if key in data:
            ages.append(_as_float(data, key, 999999.0))
    if data.get("last_rx_age_s") is not None:
        ages.append(_as_float(data, "last_rx_age_s", 999999.0) * 1000.0)
    return (bool(ages) and all(math.isfinite(age) and age >= 0 for age in ages)
            and min(ages) <= CMD_GUARD_MAX_AGE_MS)


def command_guard_check(cmd: str, data: Optional[dict], cfg: CommandGuardConfig) -> tuple[bool, str]:
    if not (command_requests_start(cmd) or command_requests_service_output(cmd)):
        return True, "not guarded"
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, f"PWM is not off: pwm={_as_int(data, 'pwm', 1)}"
    if _as_int(data, "estop", 1) != 0:
        return False, f"ESTOP is active: estop={_as_int(data, 'estop', 1)}"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_mc_bad(data)
    if bad != 0:
        return False, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"
    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if not (cfg.allow_hv or cfg.disabled):
        if vdc > cfg.max_vdc:
            return False, f"DC bus too high for command: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    if command_requests_start(cmd):
        return start_bench_gate_check(cfg)
    return True, "ok"


class HvArmConfig:
    def __init__(
        self,
        enabled: bool = False,
        ttl_sec: float = DEFAULT_HV_ARM_TTL_SEC,
        min_vdc: float = DEFAULT_HV_ARM_MIN_VDC,
        max_vdc: float = DEFAULT_HV_ARM_MAX_VDC,
        confirm: str = DEFAULT_HV_ARM_CONFIRM,
        min_temp_c: float = DEFAULT_HV_ARM_MIN_TEMP_C,
        max_temp_c: float = DEFAULT_HV_ARM_MAX_TEMP_C,
        profile: str = "hv",
        trial_gate: Optional[PoweredTrialGate] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.ttl_sec = max(1.0, float(ttl_sec))
        self.min_vdc = float(min_vdc)
        self.max_vdc = float(max_vdc)
        self.confirm = str(confirm)
        self.min_temp_c = float(min_temp_c)
        self.max_temp_c = float(max_temp_c)
        self.profile = str(profile).strip().lower() or "hv"
        self.trial_gate = trial_gate

    @property
    def profile_label(self) -> str:
        return self.profile.upper()


def hv_arm_precheck(
    data: Optional[dict], cfg: HvArmConfig, vbus_calibrated: Optional[bool] = None
) -> tuple[bool, str]:
    if not cfg.enabled:
        return False, "standalone arm mode is disabled"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101502,2026101504,2026101506,2026101702,2026101806) and (_as_int(data or {}, "fw_build", -1),_as_int(data or {}, "mc_fw_build", -1)) not in ((2026101505,2026101504),(2026101507,2026101506),(2026101703,2026101702),(2026101807,2026101806)):
        return False, "manual scalar image requires its matching supervisory firmware"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101414 and _as_int(data or {}, "fw_build", -1) != 2026101415:
        return False, "working motor-controller image requires its matching supervisory firmware"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101412 and _as_int(data or {}, "fw_build", -1) != 2026101413:
        return False, "working motor-controller image requires its matching supervisory firmware"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101410 and _as_int(data or {}, "fw_build", -1) != 2026101411:
        return False, "working motor-controller image requires its matching supervisory firmware"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101493):
        return False, "PWM/filter update awaits new calibration and physical qualification"
    calibration_ready = VBUS_HV_CALIBRATION_VALID if vbus_calibrated is None else bool(vbus_calibrated)
    if cfg.profile == ARM_PROFILE_HV and not calibration_ready:
        if cfg.trial_gate is not None:
            cfg.trial_gate.observe(data, False)
        return False, "HV Vbus calibration is incomplete; capture a known-voltage point before arming"
    if data is None:
        return False, "status unavailable"
    if cfg.profile == ARM_PROFILE_HV and (
        _as_int(data, "fw_build", -1), _as_int(data, "mc_fw_build", -1)
    ) in ((2026101004, 2026101003), (2026101005, 2026101003), (2026101007, 2026101006),
          (2026101008, 2026101006), RX_SNAPSHOT_TRIAL_PAIR, (2026101105, 2026101102), (2026101106, 2026101102), (2026101107, 2026101102), (2026101108, 2026101102)):
        if cfg.trial_gate is None:
            return False, "UART v3 requires an explicitly prepared bounded powered trial"
    if cfg.trial_gate is not None:
        ok, reason = cfg.trial_gate.ready(data, calibration_ready)
        if not ok:
            return False, reason
    if cfg.profile == ARM_PROFILE_HV and _as_int(data, "mc_fw_build", -1) in (2026101201, 2026101203, 2026101204) and cfg.trial_gate is None:
        return False, "local STOP image awaits physical qualification"
    if _as_int(data, "bp_status", 0) & 0x80:
        return False, "local Nucleo STOP is latched; release button and explicitly CLEAR"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_mc_bad(data)
    if bad != 0:
        return False, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"

    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if vdc < cfg.min_vdc or vdc > cfg.max_vdc:
        return False, f"DC bus is outside {cfg.profile_label} arm window: vdc={vdc:.1f} V"
    raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
    if not raw_ok:
        return False, raw_reason

    if _as_int(data, "bp_temp_valid", 0) != 1:
        return False, "heatsink temperature is invalid"
    if _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature fault is active"
    if _as_float(data, "bp_temp_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "heatsink temperature is stale"
    temp_c = _as_float(data, "bp_temp_c", float("nan"))
    if not math.isfinite(temp_c) or temp_c < cfg.min_temp_c or temp_c > cfg.max_temp_c:
        return False, f"heatsink temperature is implausible: temp={temp_c:.1f} C"
    return True, "ok"


def arm_profile_switch_precheck(data: Optional[dict], cfg: HvArmConfig) -> tuple[bool, str]:
    """Allow profile changes only while every commanded power output is inactive."""
    if data is None:
        return False, "status unavailable"
    state = str(data.get("state", "")).upper()
    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
    if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
        return False, f"not SAFE: state={data.get('state')}"
    if _as_int(data, "pwm", 1) != 0:
        return False, "PWM is not off"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "precharge", 1) != 0:
        return False, "precharge relay is active"
    if _as_int(data, "pfc", 1) != 0:
        return False, "PFC output is active"
    if _as_int(data, "brake", 1) != 0 or _as_float(data, "brake_duty", 1.0) > 0.0001:
        return False, "brake output is active"
    restoring_hv_while_discharged = (
        cfg.profile == ARM_PROFILE_HV
        and (_as_int(data, "fw_build", -1), _as_int(data, "mc_fw_build", -1)) == (2026101002, 2026100801)
        and _as_int(data, "bp_fault", 255) == 5
        and _as_int(data, "mc_diag_valid", 0) == 1
        and _as_int(data, "mc_fault_reason", -1) == 8
        and _as_int(data, "mc_fault_current_mask", -1) == 4
        and _as_int(data, "mc_fault_occurred_mask", -1) == 4
        and _as_int(data, "mc_uart_error_flags", -1) == 0
        and _as_int(data, "mc_last_uart_error_flags", -1) == 0
        and _as_int(data, "bp_vbus_valid", 0) == 1
        and 0 <= _as_float(data, "bp_vbus_age_ms", 999999.0) < 300.0
        and 0 <= _as_int(data, "bp_vbus_raw", -1) <= 20
        and not (_as_int(data, "bp_status", 0x22) & 0x22)
        and all(math.isfinite(_as_float(data, key, float("nan")))
                and 0 <= _as_float(data, key, -1) <= 2 for key in ("vdc", "bp_vdc"))
    )
    # Selecting a disarmed profile is not ARM/START. Only the expected, measured
    # zero-bus undervoltage may permit returning to the stricter HV profile.
    if _as_int(data, "bp_fault", 255) != 0 and not restoring_hv_while_discharged:
        return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_mc_bad(data)
    if bad != 0:
        return False, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"

    if cfg.profile == ARM_PROFILE_LV:
        # LV selection itself is fail-closed. Arming repeats the complete check.
        vdc = _status_vdc(data)
        if not math.isfinite(vdc) or vdc < cfg.min_vdc or vdc > cfg.max_vdc:
            return False, f"DC bus is outside {cfg.profile_label} profile window: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    return True, "ok"


def hv_runtime_check(
    data: Optional[dict], cfg: HvArmConfig, allow_nonzero_bad: bool = False,
    vbus_calibrated: Optional[bool] = None,
) -> tuple[bool, str]:
    calibration_ready = VBUS_HV_CALIBRATION_VALID if vbus_calibrated is None else bool(vbus_calibrated)
    if cfg.profile == ARM_PROFILE_HV and not calibration_ready:
        return False, "HV Vbus calibration is incomplete"
    if data is None:
        return False, "status unavailable"
    if cfg.trial_gate is not None:
        ok, reason = cfg.trial_gate.live_check(data, pair=cfg.trial_gate.pair,
                                              allow_stopped_zero=cfg.trial_gate.consumed,
                                              profile=cfg.trial_gate.profile)
        if not ok:
            return False, reason
        if (cfg.trial_gate.started_at is not None
                and time.monotonic() - cfg.trial_gate.started_at >= cfg.trial_gate.stop_after_s):
            return False, cfg.trial_gate.deadline_reason
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_mc_bad(data)
    if bad != 0 and not allow_nonzero_bad:
        return False, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"

    vdc = _status_vdc(data)
    if not math.isfinite(vdc) or vdc < cfg.min_vdc or vdc > cfg.max_vdc:
        return False, f"DC bus is outside {cfg.profile_label} runtime window: vdc={vdc:.1f} V"
    raw_ok, raw_reason = raw_vbus_window_check(data, cfg.min_vdc, cfg.max_vdc)
    if not raw_ok:
        return False, raw_reason

    if _as_int(data, "bp_temp_valid", 0) != 1:
        return False, "heatsink temperature is invalid"
    if _as_int(data, "bp_temp_fault", 1) != 0:
        return False, "heatsink temperature fault is active"
    if _as_float(data, "bp_temp_age_ms", 999999.0) > CMD_GUARD_MAX_AGE_MS:
        return False, "heatsink temperature is stale"
    temp_c = _as_float(data, "bp_temp_c", float("nan"))
    if not math.isfinite(temp_c) or temp_c < cfg.min_temp_c or temp_c > cfg.max_temp_c:
        return False, f"heatsink temperature is implausible: temp={temp_c:.1f} C"
    return True, "ok"


def output_sequence_health_check(
    data: Optional[dict], arm_cfg: HvArmConfig, guard_cfg: CommandGuardConfig,
    vbus_calibrated: Optional[bool] = None,
) -> tuple[bool, str]:
    if arm_cfg.enabled:
        return hv_runtime_check(data, arm_cfg, vbus_calibrated=vbus_calibrated)
    if data is None:
        return False, "status unavailable"
    if _as_int(data, "estop", 1) != 0:
        return False, "ESTOP is active"
    if _as_int(data, "bp_fault", 255) != 0:
        return False, f"motor-controller fault is active: mc_fault={_as_int(data, 'bp_fault', 255)}"
    bad = _status_mc_bad(data)
    if bad != 0:
        return False, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
    if not _status_link_live(data):
        return False, "motor-controller link is stale or down"
    vdc = _status_vdc(data)
    if not math.isfinite(vdc):
        return False, "DC bus telemetry is not readable"
    if not (guard_cfg.allow_hv or guard_cfg.disabled):
        if vdc > guard_cfg.max_vdc:
            return False, f"DC bus too high for command: vdc={vdc:.1f} V"
        raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, guard_cfg.max_vdc)
        if not raw_ok:
            return False, raw_reason
    return True, "ok"


class HvRuntimeBadFrameMonitor:
    """Trip on an error burst, not on one CRC-rejected frame under PWM EMI."""

    def __init__(
        self,
        burst_limit: int = HV_RUNTIME_BAD_BURST_LIMIT,
        window_sec: float = HV_RUNTIME_BAD_WINDOW_SEC,
    ) -> None:
        self.burst_limit = max(1, int(burst_limit))
        self.window_sec = max(0.1, float(window_sec))
        self._previous: dict[str, int] = {}
        self._events: Deque[tuple[float, int]] = deque()

    def reset(self) -> None:
        self._previous.clear()
        self._events.clear()

    def observe(self, data: dict, now: Optional[float] = None) -> tuple[bool, str]:
        timestamp = _now_ts() if now is None else float(now)
        delta = 0
        current: dict[str, int] = {}
        for key in ("mc_bad_cnt", "mc_bad", "bp_bad_cnt", "bp_bad"):
            if key not in data:
                continue
            value = max(0, _as_int(data, key, 999999))
            current[key] = value
            previous = self._previous.get(key, 0)
            if value >= previous:
                delta += value - previous
        self._previous = current

        if delta > 0:
            self._events.append((timestamp, delta))
        cutoff = timestamp - self.window_sec
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        burst = sum(count for _, count in self._events)
        if burst >= self.burst_limit:
            return False, f"motor-controller UART error burst: {burst} errors/{self.window_sec:.1f}s"
        if delta > 0:
            return True, f"isolated motor-controller UART errors: delta={delta}, window={burst}"
        return True, "ok"


def bounded_run_complete(data, before, limit_s):
    """Accept late delivery of one completed MCU run, never initiate/retry it.

    Caller must also pass the existing runtime voltage/temperature/link gates.
    Times describe MCU dispatch, not a qualified oscilloscope measurement.
    """
    if not data or not before or type(limit_s) not in (int, float) or not math.isfinite(limit_s) or limit_s<=0:
        return False
    if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102516,2026102510),(2026102517,2026102510),(2026102518,2026102510),(2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102607,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704),(2026102705,2026102706),(2026102707,2026102708),(2026102709,2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026103015,2026103016)):
        return False
    keys=('run_id','run_start_ms','run_stop_ms','run_limit_ms','run_elapsed_ms','run_reason')
    if any(type(data.get(k)) is not int or not 0<=data[k]<=0xffffffff for k in keys):
        return False
    if type(before.get('run_id')) is not int or data['run_id']!=((before['run_id']+1)&0xffffffff):
        return False
    limit=round(limit_s*1000)
    return (data['run_reason']==1 and data['run_limit_ms']==limit
        and limit<=data['run_elapsed_ms']<=limit+100
        and ((data['run_stop_ms']-data['run_start_ms'])&0xffffffff)==data['run_elapsed_ms']
        and data.get('state')=='SAFE' and data.get('pwm')==0 and data.get('estop')==0
        and data.get('bp_status',0x22)&0x22==0 and _status_link_live(data)
        and all(data.get(k)==0 for k in ('mc_fault','bp_fault','mc_transport_fault','bp_transport_fault',
            'mc_fault_current_mask','mc_fault_occurred_mask')))


def manual_scalar_supported(data):
    return bool(data and (_as_int(data,"fw_build",0),_as_int(data,"mc_fw_build",0)) in ((2026101505,2026101504),(2026101507,2026101506),(2026101703,2026101702),(2026101807,2026101806),(2026101813,2026101812),(2026102001,2026102002),(2026102101,2026102102),(2026102103,2026102104),(2026102401,2026102402),(2026102403,2026102402),(2026102405,2026102406),(2026102407,2026102408),(2026102409,2026102410),(2026102411,2026102412),(2026102501,2026102502),(2026102503,2026102502),(2026102505,2026102506),(2026102507,2026102508),(2026102509,2026102510),(2026102513,2026102510),(2026102515,2026102510),(2026102516,2026102510),(2026102517,2026102510),(2026102518,2026102510),(2026102601,2026102602),(2026102603,2026102602),(2026102605,2026102604),(2026102607,2026102604),(2026102609,2026102604),(2026102701,2026102702),(2026102703,2026102704),(2026102705,2026102706),(2026102707,2026102708),(2026102709,2026102710), (2026102811,2026102812), (2026102813,2026102812), (2026102901,2026102902), (2026103015,2026103016)) and _as_int(data,"manual_scalar_capable",0)==1)

def manual_status_reference(data):
    if (manual_scalar_supported(data) and _as_int(data,"mc_frequency_reference_valid",0)==1
            and 0 <= _as_int(data,"bp_age_ms",999999) < 300):
        data["local_ramp_reference_hz"]=data["freq"]
        data["freq"]=data["mc_frequency_reference_hz"]
        data["speed"]=data["freq"]*60.0  # electrical reference, not measured rotor RPM
    return data

class HvArmState:
    def __init__(
        self,
        cfg: HvArmConfig,
        calibration_provider: Optional[Callable[[Optional[dict]], bool]] = None,
    ) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._expires_at = 0.0
        self._started = False
        self._manual_session = False
        self._calibration_provider = calibration_provider

    def set_calibration_provider(
        self, provider: Optional[Callable[[Optional[dict]], bool]]
    ) -> None:
        with self._lock:
            self._calibration_provider = provider

    def _calibration_valid(self, data: Optional[dict]) -> Optional[bool]:
        provider = self._calibration_provider
        return provider(data) if provider is not None else None

    def arm(self, confirm: str, data: Optional[dict]) -> tuple[bool, str]:
        if not secrets.compare_digest(str(confirm), self.cfg.confirm):
            return False, "confirmation phrase mismatch"
        ok, reason = hv_arm_precheck(data, self.cfg, self._calibration_valid(data))
        if not ok:
            return False, reason
        with self._lock:
            self._expires_at = _now_ts() + self.cfg.ttl_sec
            self._started = False
            self._manual_session = False
        return True, "armed"

    def disarm(self) -> None:
        with self._lock:
            self._expires_at = 0.0
            self._started = False
            self._manual_session = False

    def set_config(self, cfg: HvArmConfig) -> None:
        with self._lock:
            self.cfg = cfg
            self._expires_at = 0.0
            self._started = False
            self._manual_session = False

    def command_allowed(self, data: Optional[dict]) -> tuple[bool, str]:
        with self._lock:
            remaining = self._expires_at - _now_ts()
            if remaining <= 0.0 and not (self._started and self._manual_session):
                if not self._started:
                    self._expires_at = 0.0
                return False, f"{self.cfg.profile_label} arm is not active"
        return hv_arm_precheck(data, self.cfg, self._calibration_valid(data))

    def set_manual_session(self, enabled: bool) -> None:
        with self._lock:
            self._manual_session = bool(enabled)

    def mark_started(self) -> None:
        with self._lock:
            if self._expires_at > _now_ts():
                self._started = True

    def mark_stopped(self) -> None:
        with self._lock:
            self._started = False
            self._manual_session = False

    def take_expired_session_action(self) -> bool:
        with self._lock:
            if self._started and self._manual_session:
                return False
            if self._expires_at <= 0.0:
                return False
            if self._expires_at > _now_ts():
                return False
            must_stop = self._started
            self._expires_at = 0.0
            self._started = False
            self._manual_session = False
            return must_stop

    def runtime_monitor_required(self) -> bool:
        with self._lock:
            return self._started and (self._manual_session or self._expires_at > _now_ts())

    def snapshot(self) -> dict:
        with self._lock:
            remaining = max(0.0, self._expires_at - _now_ts())
            if remaining <= 0.0 and not self._started:
                self._expires_at = 0.0
            return {
                "hmi_hv_enabled": int(self.cfg.enabled),
                "hmi_hv_armed": int(remaining > 0.0 or (self._started and self._manual_session)),
                "hmi_hv_started": int(self._started and (self._manual_session or remaining > 0.0)),
                "hmi_run_continuous": int(self._started and self._manual_session),
                "hmi_hv_remaining_s": round(remaining, 1),
                "hmi_hv_min_vdc": self.cfg.min_vdc,
                "hmi_hv_max_vdc": self.cfg.max_vdc,
                "hmi_arm_profile": self.cfg.profile if self.cfg.enabled else "none",
                "hmi_arm_confirm": self.cfg.confirm if self.cfg.enabled else "",
            }


class ControlAccessConfig:
    def __init__(self, token_file: Optional[str] = None) -> None:
        self.token_file = token_file

    @property
    def enabled(self) -> bool:
        return bool(self.token_file)

    def read_token(self) -> Optional[str]:
        if not self.token_file:
            return None
        try:
            with open(os.path.expanduser(self.token_file), "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError:
            return None
        if len(token) < 16:
            return None
        return token


class FirmwareUpdateConfig:
    def __init__(
        self,
        token_file: Optional[str],
        upload_dir: str,
        remoteocd_bin: str,
        remoteocd_cfg: str,
        max_bytes: int,
        timeout_sec: float,
        max_vdc: float,
    ) -> None:
        self.token_file = token_file
        self.upload_dir = upload_dir
        self.remoteocd_bin = remoteocd_bin
        self.remoteocd_cfg = remoteocd_cfg
        self.max_bytes = max_bytes
        self.timeout_sec = timeout_sec
        self.max_vdc = max_vdc

    @property
    def enabled(self) -> bool:
        return bool(self.token_file)

    def read_token(self) -> Optional[str]:
        if not self.token_file:
            return None
        try:
            with open(os.path.expanduser(self.token_file), "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError:
            return None
        if len(token) < 16:
            return None
        return token


class RouterClient:
    def __init__(self, endpoint: str) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._unpacker = None

    def _connect(self) -> None:
        if self._sock is not None:
            return
        endpoint = self._endpoint
        if endpoint.startswith("unix:"):
            path = endpoint[5:]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
        elif "/" in endpoint or endpoint.startswith("."):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(endpoint)
        else:
            host, port = self._parse_tcp(endpoint)
            sock = socket.create_connection((host, port), timeout=1.0)
        sock.settimeout(0.2)
        self._sock = sock
        self._unpacker = msgpack.Unpacker(raw=False)

    @staticmethod
    def _parse_tcp(endpoint: str) -> tuple[str, int]:
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
        else:
            host, port_str = endpoint, "7501"
        host = host or "127.0.0.1"
        try:
            port = int(port_str)
        except ValueError:
            port = 7501
        return host, port

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._sock is None or self._unpacker is None:
                        raise RuntimeError("no socket")
                    msgid = self._msgid
                    self._msgid += 1
                    self._sock.sendall(self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        try:
                            data = self._sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            raise RuntimeError("router closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("router timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class SerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._unpacker = None

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[3] = 0  # lflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        baud_const = termios_baud_constant(self._baud)
        attrs[4] = baud_const
        attrs[5] = baud_const
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd
        self._unpacker = msgpack.Unpacker(raw=False)

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._fd is None or self._unpacker is None:
                        raise RuntimeError("serial not open")
                    msgid = self._msgid
                    self._msgid += 1
                    os.write(self._fd, self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        r, _, _ = select.select([self._fd], [], [], 0.05)
                        if not r:
                            continue
                        data = os.read(self._fd, 4096)
                        if not data:
                            raise RuntimeError("serial closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class TextSerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._lock = threading.Lock()
        self._rx_buf = bytearray()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._rx_buf.clear()

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        baud_const = termios_baud_constant(self._baud)
        attrs[4] = baud_const
        attrs[5] = baud_const
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd

    def _read_lines(self, deadline: float) -> list[str]:
        lines: list[str] = []
        while _now_ts() < deadline:
            if self._fd is None:
                break
            r, _, _ = select.select([self._fd], [], [], 0.05)
            if not r:
                continue
            data = os.read(self._fd, 4096)
            if not data:
                raise RuntimeError("serial closed")
            self._rx_buf.extend(data)
            while True:
                nl = self._rx_buf.find(b"\n")
                if nl == -1:
                    break
                line = self._rx_buf[:nl].decode("utf-8", errors="ignore").strip()
                del self._rx_buf[: nl + 1]
                if line:
                    lines.append(line)
        return lines

    def _write_line(self, text: str) -> None:
        if self._fd is None:
            raise RuntimeError("serial not open")
        if not text.endswith("\n"):
            text += "\n"
        os.write(self._fd, text.encode("utf-8"))

    def cmd(self, cmd: str, timeout: float = 0.5, retries: int = 1) -> bool:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line(cmd)
                    for line in self._read_lines(_now_ts() + timeout):
                        if line == "OK" or line.startswith("OK "):
                            return True
                        if line.startswith("ERR") or line.startswith("ERROR"):
                            return False
                    raise RuntimeError("serial command not acknowledged")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return False

    def get(self, timeout: float = 1.0, retries: int = 1) -> Optional[str]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line("GET")
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        lines = self._read_lines(deadline)
                        for line in lines:
                            if line.startswith("DATA"):
                                return line
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class RpcBridge:
    def __init__(self, endpoint: str, serial_baud: int = 115200) -> None:
        self._router: Optional[RouterClient] = None
        self._serial: Optional[SerialClient] = None
        self._serial_text: Optional[TextSerialClient] = None
        if endpoint.startswith("serial:"):
            self._serial_text = TextSerialClient(endpoint.replace("serial:", "", 1), baud=serial_baud)
        elif endpoint.startswith("/dev/"):
            self._serial_text = TextSerialClient(endpoint, baud=serial_baud)
        else:
            try:
                self._router = RouterClient(endpoint)
            except RuntimeError:
                self._router = None
            # The router owns its UART. A text fallback would steal MsgPack
            # frames and inject ASCII commands into the same byte stream.

    def _call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        if self._router is not None:
            resp = self._router.call(method, params, timeout=timeout, retries=retries)
            if resp is not None:
                return resp
        return None

    def cmd(self, cmd: str) -> Tuple[bool, Optional[str]]:
        resp = self._call("cmd", [cmd], timeout=0.8, retries=0 if _cmd_head(cmd) in ("START", "CLEAR") else 2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, str(err)
            if resp[3] is False:
                return False, "rejected"
            return True, None
        if self._serial_text is not None:
            ok = self._serial_text.cmd(cmd, timeout=0.8, retries=0 if _cmd_head(cmd) in ("START", "CLEAR") else 2)
            return (ok, None if ok else "no response")
        return False, "no response"

    def get(self) -> Tuple[bool, Optional[dict], Optional[str]]:
        resp = self._call("get", [], timeout=2.0, retries=2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, None, str(err)
            result = resp[3]
            if isinstance(result, str):
                parsed = self._parse_status_string(result)
                if parsed is None:
                    return False, None, "bad result"
                return True, parsed, None
            if not isinstance(result, list) or len(result) < 9:
                return False, None, "bad result"
            state_code = int(result[0])
            mode_code = int(result[1])
            mc_mode = int(result[29]) if len(result) >= 31 else 0
            diag_mode = int(result[45]) if len(result) >= 47 else None
            duty_mode = int(result[46]) if len(result) >= 47 else None
            mode_code_eff, mode_name_eff = effective_mode(mode_code, mc_mode, diag_mode, duty_mode)
            data = {
                "state_code": state_code,
                "state": STATE_NAMES.get(state_code, str(state_code)),
                "mode_code": mode_code_eff,
                "mode": mode_name_eff,
                "pwm": int(result[2]),
                "freq": float(result[3]),
                "speed": float(result[4]),
                "ia": float(result[5]),
                "ib": float(result[6]),
                "ic": float(result[7]),
                "vdc": float(result[8]),
                "ts": int(_now_ts() * 1000.0),
            }
            if len(result) >= 12:
                data["id"] = float(result[9])
                data["iq"] = float(result[10])
                data["i_rms"] = float(result[11])
            else:
                ia = data["ia"]
                ib = data["ib"]
                ic = data["ic"]
                data["i_rms"] = float(((ia * ia + ib * ib + ic * ic) / 3.0) ** 0.5)
            if len(result) >= 15:
                data["mic_active"] = int(result[12])
                data["id_ref"] = float(result[13])
                data["mic_saving_pct"] = float(result[14])
            else:
                data["mic_active"] = 0
                data["id_ref"] = 0.0
                data["mic_saving_pct"] = 0.0
            if len(result) >= 17:
                data["freq_cmd"] = float(result[15])
                data["estop"] = int(result[16])
            else:
                data["freq_cmd"] = data.get("freq", 0.0)
                data["estop"] = 0
            if len(result) >= 21:
                data["ntc"] = int(result[17])
                data["pfc"] = int(result[18])
                data["brake"] = int(result[19])
                data["brake_duty"] = float(result[20])
            else:
                data["ntc"] = 0
                data["pfc"] = 0
                data["brake"] = 0
                data["brake_duty"] = 0.0

            # Optional extended telemetry (keep in sync with UNOQ_MOTOR/UNOQ_MOTOR.ino rpc_send_response_get()).
            if len(result) >= 24:
                data["enc_raw"] = int(result[21])
                data["enc_ok"] = int(result[22])
                data["enc_deg"] = float(result[23])
            else:
                data["enc_raw"] = 0
                data["enc_ok"] = 0
                data["enc_deg"] = 0.0

            if len(result) >= 27:
                data["bp_good"] = int(result[24])
                data["bp_bad"] = int(result[25])
                data["bp_age_ms"] = int(result[26])
            else:
                data["bp_good"] = 0
                data["bp_bad"] = 999999
                data["bp_age_ms"] = 999999

            if len(result) >= 31:
                data["bp_status"] = int(result[27])
                data["bp_pwm_active"] = 1 if (data["bp_status"] & 0x20) else 0
                data["bp_fault"] = int(result[28])
                data["bp_mode"] = mc_mode
                data["bp_seq"] = int(result[30])
            else:
                data["bp_status"] = 0
                data["bp_pwm_active"] = 0
                data["bp_fault"] = 255
                data["bp_mode"] = 0
                data["bp_seq"] = 0

            if len(result) >= 33:
                data["bp_ping_pairs"] = int(result[31])
                data["bp_ping_age_ms"] = int(result[32])
            else:
                data["bp_ping_pairs"] = 0
                data["bp_ping_age_ms"] = 999999

            if len(result) >= 34:
                data["bp_rsp_age_ms"] = int(result[33])
            else:
                data["bp_rsp_age_ms"] = 999999

            # Optional extended encoder telemetry (append-only after bp_rsp_age_ms).
            if len(result) >= 37:
                data["enc_rpm"] = float(result[34])
                data["enc_mech_hz"] = float(result[35])
                data["enc_elec_hz"] = float(result[36])
            else:
                data["enc_rpm"] = 0.0
                data["enc_mech_hz"] = 0.0
                data["enc_elec_hz"] = 0.0
            if len(result) >= 45:
                data["mic_gated"] = int(result[37])
                data["mic_enable_ai"] = int(result[38])
                data["mic_enc_used"] = int(result[39])
                data["mic_freq_meas_hz"] = float(result[40])
                data["mic_speed_err_hz"] = float(result[41])
                data["mic_speed_tol_hz"] = float(result[42])
                data["mic_link_flags"] = int(result[43])
                data["mic_status_flags"] = int(result[44])
            else:
                data["mic_gated"] = 0
                data["mic_enable_ai"] = 0
                data["mic_enc_used"] = 0
                data["mic_freq_meas_hz"] = 0.0
                data["mic_speed_err_hz"] = 0.0
                data["mic_speed_tol_hz"] = 0.0
                data["mic_link_flags"] = 0
                data["mic_status_flags"] = 0
            if len(result) >= 47:
                data["diag_mode"] = int(result[45])
                data["duty_mode"] = int(result[46])
            else:
                data["diag_mode"] = 1 if mode_code_eff == 3 else 0
                data["duty_mode"] = 1 if mode_code_eff == 4 else 0
            if len(result) >= 50:
                data["bp_vbus_raw"] = int(result[47])
                data["bp_vdc"] = float(result[48])
                data["bp_vbus_age_ms"] = int(result[49])
                data["vdc"] = data["bp_vdc"]
            else:
                data["bp_vbus_raw"] = 0
                data["bp_vdc"] = 0.0
                data["bp_vbus_age_ms"] = 999999
            if len(result) >= 54:
                temp_flags = int(result[53])
                data["bp_temp_raw"] = int(result[50])
                data["bp_temp_v"] = float(result[51])
                data["bp_temp_c"] = float(result[52])
                data["bp_temp_flags"] = temp_flags
                data["bp_temp_valid"] = 1 if (temp_flags & 0x01) else 0
                data["bp_temp_fault"] = 1 if (temp_flags & 0x02) else 0
                data["bp_temp_age_ms"] = data.get("bp_rsp_age_ms", 999999)
            else:
                data["bp_temp_raw"] = 0
                data["bp_temp_v"] = 0.0
                data["bp_temp_c"] = 0.0
                data["bp_temp_flags"] = 0
                data["bp_temp_valid"] = 0
                data["bp_temp_fault"] = 0
                data["bp_temp_age_ms"] = 999999
            if len(result) >= 62:
                phase_flags = int(result[60])
                data["bp_phase_a_raw"] = int(result[54])
                data["bp_phase_b_raw"] = int(result[55])
                data["bp_phase_c_raw"] = int(result[56])
                data["bp_phase_a_v"] = float(result[57])
                data["bp_phase_b_v"] = float(result[58])
                data["bp_phase_c_v"] = float(result[59])
                data["bp_phase_flags"] = phase_flags
                data["bp_phase_valid"] = 1 if (phase_flags & 0x01) else 0
                data["bp_phase_c_virtual"] = 1 if (phase_flags & 0x02) else 0
                data["bp_phase_age_ms"] = int(result[61])
            else:
                data["bp_phase_a_raw"] = 0
                data["bp_phase_b_raw"] = 0
                data["bp_phase_c_raw"] = 0
                data["bp_phase_a_v"] = 0.0
                data["bp_phase_b_v"] = 0.0
                data["bp_phase_c_v"] = 0.0
                data["bp_phase_flags"] = 0
                data["bp_phase_valid"] = 0
                data["bp_phase_c_virtual"] = 0
                data["bp_phase_age_ms"] = 999999
            if len(result) >= 63:
                data["bp_ext"] = int(result[62])
            else:
                data["bp_ext"] = 0
            if len(result) >= 64:
                data["iotest"] = int(result[63])
            else:
                data["iotest"] = 0
            if len(result) >= 65:
                data["precharge"] = int(result[64])
            else:
                data["precharge"] = 0
            if len(result) >= 68:
                data["fan_duty"] = float(result[65])
                data["bp_fan_duty"] = float(result[66])
                data["bp_fan_rpm"] = float(result[67])
            else:
                data["fan_duty"] = 0.0
                data["bp_fan_duty"] = 0.0
                data["bp_fan_rpm"] = 0.0
            if len(result) >= 70:
                data["bp_foc_backend"] = int(result[68])
                data["bp_cmd_mode"] = int(result[69])
            else:
                data["bp_foc_backend"] = 0
                data["bp_cmd_mode"] = data.get("bp_mode", 0)
            data["fw_build"] = int(result[70]) if len(result) >= 71 else 0
            data["matrix_test"] = int(result[71]) if len(result) >= 72 else 0
            data["bp_mcsdk_telemetry"] = int(result[72]) if len(result) >= 73 else 0
            data["bp_vbus_valid"] = int(result[73]) if len(result) >= 74 else 0
            data["bp_precharge_managed"] = int(result[74]) if len(result) >= 75 else 0
            data["rpc_schema_version"] = int(result[75]) if len(result) >= 76 else 1
            if data["rpc_schema_version"] >= 2 and len(result) >= 78:
                data["bp_softstart_ready"] = int(result[76])
                data["mc_capabilities"] = int(result[77])
            else:
                # Fail closed for the ambiguous 75-element transition format.
                data["bp_softstart_ready"] = 0
                data["mc_capabilities"] = 0
            data["mc_fw_build"] = (
                int(result[78])
                if data["rpc_schema_version"] >= 3 and len(result) >= 79
                else 0
            )
            data["mc_supported_modes"] = supported_modes_from_caps(data["mc_capabilities"])
            for index, field in enumerate(("mc_diag_valid", "mc_fault_reason", "mc_uart_error_flags",
                                           "mc_fault_motor_state", "mc_fault_current_mask",
                                           "mc_fault_occurred_mask", "mc_fault_sequence", "mc_fault_tx_status"), 79):
                data[field] = int(result[index]) if len(result) >= 87 else 0
            for index, field in enumerate(("mc_last_bad_valid", "mc_last_bad_reason",
                                           "mc_last_uart_error_flags", "mc_last_tx_status"), 87):
                data[field] = int(result[index]) if len(result) >= 91 else 0
            if len(result) >= 99:
                data.update(manual_scalar_capable=int(result[91]),manual_run_mode=int(result[92]),
                    accel_hz_per_s=float(result[93]),decel_hz_per_s=float(result[94]),
                    downmode_coast=int(result[95]),mc_frequency_reference_hz=float(result[96]),
                    mc_frequency_reference_valid=int(result[97]),mc_decel_bus_hold=int(result[98]))
                if manual_scalar_supported(data) and data["mc_frequency_reference_valid"]==1 and _as_int(data,"bp_age_ms",999999)<300:
                    data["local_ramp_reference_hz"]=data["freq"]
                    data["freq"]=data["mc_frequency_reference_hz"]
                    data["speed"]=data["freq"]*60.0  # audited AIR56B2: one pole pair; reference, not rotor speed
            return True, with_motor_controller_aliases(data), None
        if self._serial_text is not None:
            line = self._serial_text.get(timeout=1.2, retries=2)
            if not line:
                return False, None, "no response"
            parsed = self._parse_status_string(line)
            if parsed is None:
                return False, None, "bad result"
            return True, parsed, None
        return False, None, "no response"

    @staticmethod
    def _parse_status_string(text: str) -> Optional[dict]:
        # Expected format: DATA freq=.. speed=.. ia=.. ib=.. ic=.. vdc=.. state=.. mode=.. pwm=..
        try:
            parts = text.replace("DATA", "").strip().split()
            kv = {}
            for part in parts:
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                kv[k.strip()] = v.strip()
            state_s = kv.get("state", "")
            mode_s = kv.get("mode", "")
            state_code = STATE_CODES.get(state_s, -1)
            mode_code = MODE_CODES.get(mode_s, -1)
            diag_mode = int(float(kv.get("diag", "0")))
            duty_mode = int(float(kv.get("duty", "0")))
            mode_code_eff, mode_name_eff = effective_mode(mode_code, int(float(kv.get("bp_mode", "0"))), diag_mode, duty_mode)
            capabilities = int(float(kv.get("mc_caps", "0")))
            return with_motor_controller_aliases(manual_status_reference({
                "state_code": int(state_code),
                "state": state_s or str(state_code),
                "mode_code": int(mode_code_eff),
                "mode": mode_name_eff,
                "pwm": int(float(kv.get("pwm", "0"))),
                "freq": float(kv.get("freq", "0")),
                "speed": float(kv.get("speed", "0")),
                "ia": float(kv.get("ia", "0")),
                "ib": float(kv.get("ib", "0")),
                "ic": float(kv.get("ic", "0")),
                "vdc": float(kv.get("vdc", "0")),
                "id": float(kv.get("id", "0")),
                "iq": float(kv.get("iq", "0")),
                "i_rms": float(kv.get("irm", "0")),
                "mic_active": int(float(kv.get("mic", "0"))),
                "id_ref": float(kv.get("idref", "0")),
                "mic_saving_pct": float(kv.get("save", "0")),
                "freq_cmd": float(kv.get("freqcmd", kv.get("freq", "0"))),
                "estop": int(float(kv.get("estop", "0"))),
                "iotest": int(float(kv.get("iotest", "0"))),
                "ntc": int(float(kv.get("ntc", "0"))),
                "pfc": int(float(kv.get("pfc", "0"))),
                "precharge": int(float(kv.get("precharge", "0"))),
                "brake": int(float(kv.get("brake", "0"))),
                "brake_duty": float(kv.get("brake_duty", "0")),
                "fan_duty": float(kv.get("fan_duty", "0")),
                "bp_fan_duty": float(kv.get("bp_fan_duty", "0")),
                "bp_fan_rpm": float(kv.get("bp_fan_rpm", "0")),
                "enc_raw": int(float(kv.get("enc_raw", "0"))),
                "enc_ok": int(float(kv.get("enc_ok", "0"))),
                "rpc_response_timeouts": int(kv.get("rpc_response_timeouts","0")),
                "rpc_send_timeouts": int(kv.get("rpc_send_timeouts","0")),
                "rpc_late_responses": int(kv.get("rpc_late_responses","0")),
                "rpc_unknown_methods": int(kv.get("rpc_unknown_methods","0")),
                "rpc_stack_budget": int(kv.get("rpc_stack_budget","0")),
                "rpc_stack_free": int(kv.get("rpc_stack_free","4294967295")),
                **boot_wire_status(kv),
                **foc_runtime_status(kv),
                **{k:int(kv.get(k,"0")) for k in ("mc_observer_trace_complete","mc_observer_trace_good","mc_observer_trace_bad")},
                "foc_runtime_valid": int(kv.get("foc_runtime_valid","0")),
                "foc_runtime_flags": int(kv.get("foc_runtime_flags","0")),
                "foc_runtime_good": int(kv.get("foc_runtime_good","0")),
                "foc_runtime_bad": int(kv.get("foc_runtime_bad","0")),
                "foc_runtime_w0": int(kv.get("foc_runtime_w0","0")),
                "foc_runtime_w1": int(kv.get("foc_runtime_w1","0")),
                "foc_runtime_w2": int(kv.get("foc_runtime_w2","0")),
                "foc_runtime_w3": int(kv.get("foc_runtime_w3","0")),
                "foc_runtime_w4": int(kv.get("foc_runtime_w4","0")),
                "foc_runtime_w5": int(kv.get("foc_runtime_w5","0")),
                "foc_runtime_w6": int(kv.get("foc_runtime_w6","0")),
                "foc_runtime_w7": int(kv.get("foc_runtime_w7","0")),
                "foc_runtime_w8": int(kv.get("foc_runtime_w8","0")),
                "foc_runtime_w9": int(kv.get("foc_runtime_w9","0")),
                "foc_runtime_w10": int(kv.get("foc_runtime_w10","0")),
                "foc_runtime_w11": int(kv.get("foc_runtime_w11","0")),
                "foc_runtime_w12": int(kv.get("foc_runtime_w12","0")),
                "foc_runtime_w13": int(kv.get("foc_runtime_w13","0")),
                "foc_runtime_w14": int(kv.get("foc_runtime_w14","0")),
                "foc_runtime_w15": int(kv.get("foc_runtime_w15","0")),
                "foc_runtime_w16": int(kv.get("foc_runtime_w16","0")),
                "foc_runtime_w17": int(kv.get("foc_runtime_w17","0")),
                "foc_runtime_w18": int(kv.get("foc_runtime_w18","0")),
                "foc_runtime_w19": int(kv.get("foc_runtime_w19","0")),
                "foc_runtime_w20": int(kv.get("foc_runtime_w20","0")),
                "foc_runtime_w21": int(kv.get("foc_runtime_w21","0")),
                "foc_runtime_w22": int(kv.get("foc_runtime_w22","0")),
                "foc_runtime_w23": int(kv.get("foc_runtime_w23","0")),
                "foc_runtime_w24": int(kv.get("foc_runtime_w24","0")),
                "foc_runtime_w25": int(kv.get("foc_runtime_w25","0")),
                "foc_runtime_w26": int(kv.get("foc_runtime_w26","0")),
                "foc_runtime_w27": int(kv.get("foc_runtime_w27","0")),
                "foc_runtime_w28": int(kv.get("foc_runtime_w28","0")),
                "foc_runtime_w29": int(kv.get("foc_runtime_w29","0")),
                "foc_runtime_w30": int(kv.get("foc_runtime_w30","0")),
                "foc_runtime_w31": int(kv.get("foc_runtime_w31","0")),
                "foc_runtime_w32": int(kv.get("foc_runtime_w32","0")),
                "foc_runtime_w33": int(kv.get("foc_runtime_w33","0")),
                "foc_runtime_w34": int(kv.get("foc_runtime_w34","0")),
                "foc_runtime_w35": int(kv.get("foc_runtime_w35","0")),
                "foc_runtime_w36": int(kv.get("foc_runtime_w36","0")),
                "foc_runtime_w37": int(kv.get("foc_runtime_w37","0")),
                "foc_runtime_w38": int(kv.get("foc_runtime_w38","0")),
                "foc_runtime_w39": int(kv.get("foc_runtime_w39","0")),
                "foc_runtime_w40": int(kv.get("foc_runtime_w40","0")),
                "foc_runtime_w41": int(kv.get("foc_runtime_w41","0")),
                "research_native_valid": int(kv.get("research_native_valid","0")),
                "research_native_caps": int(kv.get("research_native_caps","0")),
                "research_native_good": int(kv.get("research_native_good","0")),
                "research_native_bad": int(kv.get("research_native_bad","0")),
                "algorithm_selected": int(kv.get("algorithm_selected","0")),
                "algorithm_requested": int(kv.get("algorithm_requested","0")),
                "algorithm_qualification": int(kv.get("algorithm_qualification","0")),
                "algorithm_profile_crc": int(kv.get("algorithm_profile_crc","0")),
                "foc_experiment_flags": int(kv.get("foc_experiment_flags","0")),
                "foc_timing_fault": int(kv.get("foc_timing_fault","0")),
                "foc_timing_cases": int(kv.get("foc_timing_cases","0")),
                "algorithm_fast_cycles": int(kv.get("algorithm_fast_cycles","0")),
                "algorithm_observer_cycles": int(kv.get("algorithm_observer_cycles","0")),
                "algorithm_fault": int(kv.get("algorithm_fault","0")),
                "rpm_est": float(kv.get("rpm_est","0")),
                "rpm_est_valid": int(kv.get("rpm_est_valid","0")),
                "id_valid": int(kv.get("id_valid","0")),
                "id_timing_cycles": int(kv.get("id_timing_cycles","0")),
                "id_flags": int(kv.get("id_flags","0")),
                "id_config_crc": int(kv.get("id_config_crc","0")),
                "id_result_crc": int(kv.get("id_result_crc","0")),
                "id_run_id": int(kv.get("id_run_id","0")),
                "id_kind": int(kv.get("id_kind","0")),
                "id_duration_ms": int(kv.get("id_duration_ms","0")),
                "id_fault": int(kv.get("id_fault","0")),
                "id_wire_good": int(kv.get("id_wire_good","0")),
                "id_wire_bad": int(kv.get("id_wire_bad","0")),
                "id_complete": int(kv.get("id_complete","0")),
                "noise_complete": int(kv.get("noise_complete","0")),
                "noise_crc": int(kv.get("noise_crc","0")),
                "noise_good": int(kv.get("noise_good","0")),
                "noise_bad": int(kv.get("noise_bad","0")),
                "noise_view_page": int(kv.get("noise_view_page","0")),
                "noise_page_hex": kv.get("noise_page_hex","-"),
                "id_view_page": int(kv.get("id_view_page","0")),
                "id_frequency": float(kv.get("id_frequency","0")),
                "id_page_hex": kv.get("id_page_hex","-"),
                "enc_source": kv.get("enc_source", "motor_controller_uart"),
                **{"enc_health_"+name: int(kv.get("enc_health_"+name,"0")) for name in
                   ("nack","deadline","busy","arlo","ovr","short","setup","berr_clears","clean_stops","forced_resets","stop_requests","cleanup_expired","normal_parks","cleanup_flags")},
                "enc_wire_state": int(kv.get("enc_wire_state","0")),
                "enc_wire_valid": int(kv.get("enc_wire_valid","0")),
                "enc_wire_good": int(kv.get("enc_wire_good","0")),
                "enc_wire_bad": int(kv.get("enc_wire_bad","0")),
                "enc_peer_epoch": int(kv.get("enc_peer_epoch","0")),
                "enc_previous_epoch": int(kv.get("enc_previous_epoch","0")),
                "enc_previous_records_retained": int(kv.get("enc_previous_records_retained","0")),
                "enc_wire_hex": kv.get("enc_wire_hex","-"),
                "enc_wire_crc": kv.get("enc_wire_crc","-"),
                "enc_previous_record_crcs": kv.get("enc_previous_record_crcs","-"),
                "enc_bus_clear_hex": kv.get("enc_bus_clear_hex","-"),
                "enc_release_first_hex": kv.get("enc_release_first_hex","-"),
                "enc_release_pwm_hex": kv.get("enc_release_pwm_hex","-"),
                "enc_release_good": int(kv.get("enc_release_good","0")),
                "enc_release_bad": int(kv.get("enc_release_bad","0")),
                "enc_fault_first_hex": kv.get("enc_fault_first_hex","-"),
                "enc_fault_pwm_hex": kv.get("enc_fault_pwm_hex","-"),
                "enc_fault_good": int(kv.get("enc_fault_good","0")),
                "enc_fault_bad": int(kv.get("enc_fault_bad","0")),
                "enc_peer_good": int(kv.get("enc_peer_good","0")),
                "enc_peer_bad": int(kv.get("enc_peer_bad","0")),
                "enc_diag_category_counts_available": int(kv.get("enc_diag_category_counts_available","1")),
                "enc_bus_ok": int(float(kv.get("enc_bus_ok", "0"))),
                "enc_status": int(float(kv.get("enc_status", "0"))),
                "enc_speed_ok": int(float(kv.get("enc_speed_ok", "0"))),
                "enc_reads": int(float(kv.get("enc_reads", "0"))),
                "enc_errors": int(float(kv.get("enc_errors", "0"))),
                "enc_io_error": int(float(kv.get("enc_io_error", "0"))),
                "enc_init_error": int(float(kv.get("enc_init_error", "0"))),
                "enc_diag_mode": int(float(kv.get("enc_diag_mode", "0"))),
                "enc_diag_berr_count": int(kv.get("enc_diag_berr_count", "0")),
                "enc_diag_arlo_count": int(kv.get("enc_diag_arlo_count", "0")),
                "enc_diag_busy_count": int(kv.get("enc_diag_busy_count", "0")),
                "enc_diag_graceful_cleanups": int(kv.get("enc_diag_graceful_cleanups", "0")),
                "enc_diag_post_reset_busy": int(kv.get("enc_diag_post_reset_busy", "0")),
                "enc_diag_kernel_hz": int(kv.get("enc_diag_kernel_hz", "0")),
                "enc_diag_timingr": int(kv.get("enc_diag_timingr", "0")),
                "enc_diag_cr1": int(kv.get("enc_diag_cr1", "0")),
                "enc_diag_event_count": int(kv.get("enc_diag_event_count", "0")),
                "enc_diag_events_hex": kv.get("enc_diag_events_hex", "-"),
                "enc_diag_sched_sections": int(kv.get("enc_diag_sched_sections", "0")),
                "enc_diag_sched_max_hold_us": int(kv.get("enc_diag_sched_max_hold_us", "0")),
                "enc_diag_isr": int(kv.get("enc_diag_isr", "0")),
                "enc_diag_last_isr": int(kv.get("enc_diag_last_isr", "0")),
                "enc_diag_controller_resets": int(kv.get("enc_diag_controller_resets", "0")),
                "enc_diag_timeout_count": int(kv.get("enc_diag_timeout_count", "0")),
                "enc_diag_nack_count": int(kv.get("enc_diag_nack_count", "0")),
                "run_id": int(kv.get("run_id", "0")),
                "run_start_ms": int(kv.get("run_start_ms", "0")),
                "run_stop_ms": int(kv.get("run_stop_ms", "0")),
                "run_limit_ms": int(kv.get("run_limit_ms", "0")),
                "run_reason": int(kv.get("run_reason", "0")),
                "run_elapsed_ms": int(kv.get("run_elapsed_ms", "0")),
                "enc_diag_thread_priority": int(float(kv.get("enc_diag_thread_priority", "0"))),
                "enc_diag_cfg_expected": int(float(kv.get("enc_diag_cfg_expected", "0"))),
                "enc_diag_cfg_before": int(float(kv.get("enc_diag_cfg_before", "0"))),
                "enc_diag_cfg_after": int(float(kv.get("enc_diag_cfg_after", "0"))),
                "enc_diag_cfg_match": int(float(kv.get("enc_diag_cfg_match", "0"))),
                "enc_diag_last_cfg_before": int(float(kv.get("enc_diag_last_cfg_before", "0"))),
                "enc_diag_last_cfg_after": int(float(kv.get("enc_diag_last_cfg_after", "0"))),
                "enc_diag_tx_byte": int(float(kv.get("enc_diag_tx_byte", "0"))),
                "enc_diag_tx_echo": int(float(kv.get("enc_diag_tx_echo", "0"))),
                "enc_diag_tx_bits": int(float(kv.get("enc_diag_tx_bits", "0"))),
                "enc_diag_last_tx_byte": int(float(kv.get("enc_diag_last_tx_byte", "0"))),
                "enc_diag_last_tx_echo": int(float(kv.get("enc_diag_last_tx_echo", "0"))),
                "enc_diag_last_tx_bits": int(float(kv.get("enc_diag_last_tx_bits", "0"))),
                "enc_diag_epoch": int(float(kv.get("enc_diag_epoch", "0"))),
                "enc_diag_stage": int(float(kv.get("enc_diag_stage", "0"))),
                "enc_diag_cause": int(float(kv.get("enc_diag_cause", "0"))),
                "enc_diag_us": int(float(kv.get("enc_diag_us", "0"))),
                "enc_diag_wait_us": int(float(kv.get("enc_diag_wait_us", "0"))),
                "enc_diag_first_ms": int(float(kv.get("enc_diag_first_ms", "0"))),
                "enc_diag_first_stage": int(float(kv.get("enc_diag_first_stage", "0"))),
                "enc_diag_first_cause": int(float(kv.get("enc_diag_first_cause", "0"))),
                "enc_diag_first_us": int(float(kv.get("enc_diag_first_us", "0"))),
                "enc_diag_last_ms": int(float(kv.get("enc_diag_last_ms", "0"))),
                "enc_diag_last_mode": int(float(kv.get("enc_diag_last_mode", "0"))),
                "enc_diag_last_stage": int(float(kv.get("enc_diag_last_stage", "0"))),
                "enc_diag_last_cause": int(float(kv.get("enc_diag_last_cause", "0"))),
                "enc_diag_last_us": int(float(kv.get("enc_diag_last_us", "0"))),
                "enc_scl": int(float(kv.get("enc_scl", "-1"))),
                "enc_sda": int(float(kv.get("enc_sda", "-1"))),
                "enc_age_ms": int(float(kv.get("enc_age_ms", "999999"))),
                "enc_deg": float(kv.get("enc_deg", "0")),
                "enc_rpm": float(kv.get("enc_rpm", "0")),
                "enc_mech_hz": float(kv.get("enc_mech_hz", "0")),
                "enc_elec_hz": float(kv.get("enc_elec_hz", "0")),
                "mic_gated": int(float(kv.get("mic_gated", "0"))),
                "mic_enable_ai": int(float(kv.get("mic_enable_ai", "0"))),
                "mic_enc_used": int(float(kv.get("mic_enc_used", "0"))),
                "mic_freq_meas_hz": float(kv.get("mic_fmeas", "0")),
                "mic_speed_err_hz": float(kv.get("mic_ferr", "0")),
                "mic_speed_tol_hz": float(kv.get("mic_ftol", "0")),
                "mic_link_flags": int(float(kv.get("mic_lflags", "0"))),
                "mic_status_flags": int(float(kv.get("mic_sflags", "0"))),
                "diag_mode": diag_mode,
                "duty_mode": duty_mode,
                "bp_good": int(float(kv.get("bp_good", "0"))),
                "bp_bad": int(float(kv.get("bp_bad", "999999"))),
                "uno_rx_rescued": int(kv.get("uno_rx_rescued", "0")),
                **{k: int(kv[k]) for k in ("uno_rx_dropped", "uno_rx_hw_errors",
                    "uno_rx_hw_flags", "uno_rx_high_water", "uno_rx_pending",
                    "uno_rx_poll_gap_max_ms", "uno_rx_rejected_ms") if k in kv},
                **{k: int(kv[k]) for k in ("uno_bridge_service_priority", "uno_control_priority", "uno_rpc_priority", "uno_local_adc_acquired", "uno_tx_all_max_gap_us",
                    "uno_tx_last_gap_us", "uno_tx_gaps_over_watchdog") if k in kv},
                "uno_rx_rejected_hex": kv.get("uno_rx_rejected_hex", "-"),
                **{key: kv.get(key, "-") for key in ("mc_current_packet_hex", "mc_current_detail_hex", "mc_current_quality_hex", "mc_adc_peak_hex", "mc_zero_history_hex", "mc_observer_trace_hex")},
                **{key: int(kv.get(key, "999999" if "age_ms" in key else "0")) for key in
                   ("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_quality_age_ms", "mc_current_good", "mc_current_bad", "mc_adc_peak_good", "mc_adc_peak_bad", "mc_adc_peak_complete", "mc_zero_history_good", "mc_zero_history_bad")},
                "mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),
                "mc_uart_reject_good_pages": int(kv.get("mc_uart_reject_good_pages", "0")),
                "mc_uart_reject_bad_pages": int(kv.get("mc_uart_reject_bad_pages", "0")),
                "mc_break_wave_hex": kv.get("mc_break_wave_hex", "-"),
                "mc_break_wave_age_ms": int(kv.get("mc_break_wave_age_ms", "999999")),
                "mc_break_wave_good_pages": int(kv.get("mc_break_wave_good_pages", "0")),
                "mc_break_wave_bad_pages": int(kv.get("mc_break_wave_bad_pages", "0")),
                "bp_bad_integrity": int(float(kv["bp_bad_integrity"])) if "bp_bad_integrity" in kv else None,
                "bp_bad_sequence": int(float(kv["bp_bad_sequence"])) if "bp_bad_sequence" in kv else None,
                **{key: int(kv[key]) if key in kv else None for key in (
                    "bp_ne_accepted", "bp_ne_observed", "bp_ne_flags", "bp_transport_fault", "bp_recovered_drops")},
                "bp_superseded": int(float(kv["bp_superseded"])) if "bp_superseded" in kv else None,
                "bp_clear_pending": int(float(kv["bp_clear_pending"])) if "bp_clear_pending" in kv else None,
                "bp_age_ms": int(float(kv.get("bp_age_ms", "999999"))),
                "bp_status": int(float(kv.get("bp_status", "0"))),
                "bp_fault": int(float(kv.get("bp_fault", "255"))),
                **break_wire_status(kv),
                **break_reject_status(kv),
                "mc_break_rx_good": int(kv.get("mc_break_rx_good", "0")),
                "mc_break_rx_bad": int(kv.get("mc_break_rx_bad", "0")),
                "mc_diag_valid": int(float(kv.get("mc_diag_valid", "0"))),
                "mc_fault_reason": int(float(kv.get("mc_fault_reason", "0"))),
                "mc_uart_error_flags": int(float(kv.get("mc_uart_error_flags", "0"))),
                "mc_fault_motor_state": int(float(kv.get("mc_fault_motor_state", "0"))),
                "mc_fault_current_mask": int(float(kv.get("mc_fault_current_mask", "0"))),
                "mc_fault_occurred_mask": int(float(kv.get("mc_fault_occurred_mask", "0"))),
                "mc_fault_sequence": int(float(kv.get("mc_fault_sequence", "0"))),
                "mc_fault_tx_status": int(float(kv.get("mc_fault_tx_status", "0"))),
                "mc_last_bad_valid": int(float(kv.get("mc_last_bad_valid", "0"))),
                "mc_last_bad_reason": int(float(kv.get("mc_last_bad_reason", "0"))),
                "mc_last_uart_error_flags": int(float(kv.get("mc_last_uart_error_flags", "0"))),
                "mc_last_tx_status": int(float(kv.get("mc_last_tx_status", "0"))),
                **{key: int(kv[key]) if key in kv else None for key in (
                    "uno_loop_active_max_us", "uno_tx_active_max_gap_us", "uno_rx_active_max_gap_us",
                    "uno_tx_call_max_us", "uno_rpc_max_us", "uno_tx_short_writes", "uno_tx_count", "uno_rx_count",
                    "uno_log_dropped", "uno_log_pending")},
                "bp_mode": int(float(kv.get("bp_mode", "0"))),
                "bp_cmd_mode": int(float(kv.get("bp_cmd_mode", kv.get("bp_mode", "0")))),
                "bp_foc_backend": int(float(kv.get("bp_foc_backend", "0"))),
                "fw_build": int(float(kv.get("fw_build", "0"))),
                "mc_fw_build": int(float(kv.get("bp_fw_build", "0"))),
                "matrix_test": int(float(kv.get("matrix_test", "0"))),
                "bp_seq": int(float(kv.get("bp_seq", "0"))),
                "bp_good_cnt": int(float(kv.get("bp_good_cnt", kv.get("bp_good", "0")))),
                "bp_bad_cnt": int(float(kv.get("bp_bad_cnt", kv.get("bp_bad", "999999")))),
                "bp_ext": int(float(kv.get("bp_ext", "0"))),
                "bp_brake_duty": float(kv.get("bp_brake_duty", "0")),
                "bp_vbus_raw": int(float(kv.get("bp_vbus_raw", "0"))),
                "bp_vdc": float(kv.get("bp_vdc", kv.get("vdc", "0"))),
                "bp_vbus_age_ms": int(float(kv.get("bp_vbus_age_ms", "999999"))),
                "bp_mcsdk_telemetry": int(float(kv.get("bp_mcsdk_telemetry", "0"))),
                "bp_vbus_valid": int(float(kv.get("bp_vbus_valid", "0"))),
                "bp_softstart_ready": int(float(kv.get("bp_softstart_ready", "0"))),
                "bp_precharge_managed": 0,
                "rpc_schema_version": int(float(kv.get("rpc_schema", "1"))),
                "mc_capabilities": capabilities,
                "mc_supported_modes": supported_modes_from_caps(capabilities),
                "bp_temp_raw": int(float(kv.get("bp_temp_raw", "0"))),
                "bp_temp_v": float(kv.get("bp_temp_v", "0")),
                "bp_temp_c": float(kv.get("bp_temp_c", "0")),
                "bp_temp_flags": int(float(kv.get("bp_temp_flags", "0"))),
                "bp_temp_valid": int(float(kv.get("bp_temp_valid", "0"))),
                "bp_temp_fault": int(float(kv.get("bp_temp_fault", "0"))),
                "bp_temp_age_ms": int(float(kv.get("bp_temp_age_ms", "999999"))),
                "bp_phase_a_raw": int(float(kv.get("bp_phase_a_raw", "0"))),
                "bp_phase_b_raw": int(float(kv.get("bp_phase_b_raw", "0"))),
                "bp_phase_c_raw": int(float(kv.get("bp_phase_c_raw", "0"))),
                "bp_phase_a_v": float(kv.get("bp_phase_a_v", "0")),
                "bp_phase_b_v": float(kv.get("bp_phase_b_v", "0")),
                "bp_phase_c_v": float(kv.get("bp_phase_c_v", "0")),
                "bp_phase_flags": int(float(kv.get("bp_phase_flags", "0"))),
                "bp_phase_valid": int(float(kv.get("bp_phase_valid", "0"))),
                "bp_phase_c_virtual": int(float(kv.get("bp_phase_c_virtual", "0"))),
                "bp_phase_age_ms": int(float(kv.get("bp_phase_age_ms", "999999"))),
                "bp_rsp_age_ms": int(float(kv.get("bp_rsp_age_ms", "999999"))),
                "bp_ping_pairs": int(float(kv.get("bp_ping_pairs", "0"))),
                "bp_ping_age_ms": int(float(kv.get("bp_ping_age_ms", "999999"))),
                **{key: int(kv[key]) for key in ("manual_scalar_capable", "manual_run_mode",
                    "downmode_coast", "mc_frequency_reference_valid", "mc_decel_bus_hold") if key in kv},
                **{key: float(kv[key]) for key in ("accel_hz_per_s", "decel_hz_per_s",
                    "mc_frequency_reference_hz") if key in kv},
                "ts": int(_now_ts() * 1000.0),
            }))
        except Exception:
            return None


# Local bench UI: opening the control page creates an operator session.
# The persistent script/API control key is never sent to the browser.
class UiSessionStore:
    COOKIE='mic_ui_session'
    def __init__(self,clock=None,ttl=43200):
        self._clock=clock or time.monotonic
        self._ttl=ttl
        self._sessions={}
        self._lock=threading.RLock()

    def _read(self,header):
        from http.cookies import SimpleCookie
        try:
            if not isinstance(header,str) or len(header)>8192:return ''
            jar=SimpleCookie();jar.load(header)
            return jar[self.COOKIE].value if self.COOKIE in jar else ''
        except Exception:return ''

    def valid(self,header):
        value=self._read(header);now=self._clock()
        with self._lock:
            if not value or self._sessions.get(value,0)<=now:
                self._sessions.pop(value,None);return False
            self._sessions[value]=now+self._ttl
            return True

    def issue(self,header=''):
        from http.cookies import SimpleCookie
        value=self._read(header);now=self._clock()
        with self._lock:
            self._sessions={k:v for k,v in self._sessions.items() if v>now}
            if value not in self._sessions:
                if len(self._sessions)>=32:self._sessions.pop(min(self._sessions,key=self._sessions.get))
                value=secrets.token_urlsafe(32)
            self._sessions[value]=now+self._ttl
        jar=SimpleCookie();jar[self.COOKIE]=value
        for key,val in {'path':'/','httponly':True,'samesite':'Strict','max-age':str(self._ttl)}.items():jar[self.COOKIE][key]=val
        return jar[self.COOKIE].OutputString()


class AppState:
    def __init__(
        self,
        rpc: RpcBridge,
        logs: LogStore,
        status_log_interval: float,
        firmware_update: Optional[FirmwareUpdateConfig] = None,
        command_guard: Optional[CommandGuardConfig] = None,
        hv_arm: Optional[HvArmState] = None,
        start_runlimit_sec: float = DEFAULT_START_RUNLIMIT_SEC,
        arm_profiles: Optional[dict[str, HvArmConfig]] = None,
        profile_runlimits: Optional[dict[str, float]] = None,
        guard_max_vdc: float = DEFAULT_CMD_GUARD_MAX_VDC,
        control_access: Optional[ControlAccessConfig] = None,
        operator_heartbeat_timeout_sec: float = DEFAULT_OPERATOR_HEARTBEAT_TIMEOUT_SEC,
        vbus_calibration: Optional[VbusCalibrationStore] = None,
    ) -> None:
        self.rpc = rpc
        self.logs = logs
        self.firmware_update = firmware_update
        self.command_guard = command_guard or CommandGuardConfig(DEFAULT_CMD_GUARD_MAX_VDC)
        self.hv_arm = hv_arm or HvArmState(HvArmConfig())
        self.start_runlimit_sec = max(0.1, float(start_runlimit_sec))
        self.arm_profiles = dict(arm_profiles or {})
        self.profile_runlimits = {
            str(name).lower(): max(0.1, float(limit))
            for name, limit in (profile_runlimits or {}).items()
        }
        self.guard_max_vdc = float(guard_max_vdc)
        self.control_access = control_access or ControlAccessConfig()
        self.ui_sessions = UiSessionStore()
        self.vbus_calibration = vbus_calibration or VbusCalibrationStore()
        self.hv_arm.set_calibration_provider(self.vbus_calibration.is_valid)
        self.operator_heartbeat_timeout_sec = max(1.0, float(operator_heartbeat_timeout_sec))
        self._operator_heartbeat_ts = 0.0
        self._manual_start_requested = False
        self._manual_mcu_watchdog = False
        self.control_lock = threading.Lock()
        self._status_log_interval = status_log_interval
        self._last_status_log = 0.0
        self._last_fault_diag_key = None
        self._lock = threading.Lock()
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._runtime_bad_monitor = HvRuntimeBadFrameMonitor()
        self._fault_recorder = MotorFaultRecorder()
        self._last_diag_idle_poll = 0.0
        self._trial_original_cfg = None
        self._trial_original_runlimit = None
        self._powered_trial_spent = False

    def prepare_powered_trial(self, proof: object, confirm: str) -> tuple[bool, str]:
        if confirm not in ("PREPARE UARTV3 TRIAL 3S","PREPARE UARTV3 COAST30 50HZ") or not self.control_access.enabled:
            return False, "authenticated explicit trial preparation required"
        ok, reason = validate_powered_trial_qualification(proof)
        if not ok:
            return False, reason
        coast30 = proof.get("schema")=="mic_ai.powered_trial.coast30.v1"
        if confirm != ("PREPARE UARTV3 COAST30 50HZ" if coast30 else "PREPARE UARTV3 TRIAL 3S"):
            return False, "qualification/preparation phrase mismatch"
        if self._powered_trial_spent or self.hv_arm.cfg.trial_gate is not None:
            return False, "trial already prepared or consumed in this HMI session"
        cfg = self.hv_arm.cfg
        read_ok, data, _ = self.rpc.get()
        if (not read_ok or data is None or cfg.profile != ARM_PROFILE_HV or not cfg.enabled
                or self.hv_arm.snapshot()["hmi_hv_armed"] or not self.vbus_calibration.is_valid(data)):
            return False, "trial needs disarmed calibrated HV profile"
        if ((data.get("fw_build"), data.get("mc_fw_build")) != tuple(proof["pair"])
                or data.get("state") != "SAFE" or data.get("pwm") != 0 or data.get("estop") != 0
                or _as_int(data, "bp_status", 0x22) & 0x22
                or any(data.get(k) != 0 for k in ("precharge", "pfc", "brake", "bp_ext"))):
            return False, "trial preparation requires qualified peers with outputs off"
        prepare_max_vdc = 10 if tuple(proof["pair"]) == BOOT_TRIAL_PAIR else 2
        for key in ("vdc", "bp_vdc"):
            value = data.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= prepare_max_vdc:
                return False, "prepare only on a low-energy bus"
        if not 0 <= _as_int(data, "bp_vbus_raw", 999999) <= prepare_max_vdc*10 or not _status_link_live(data):
            return False, "preparation bus word/link invalid"
        for key in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence", "mc_uart_error_flags",
                    "mc_last_uart_error_flags", "uno_tx_short_writes", "bp_transport_fault"):
            if type(data.get(key)) is not int or data[key] != 0:
                return False, "preparation transport unhealthy: " + key
        for key in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
            value = data.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 300:
                return False, "preparation telemetry stale: " + key
        if (data.get("bp_fault") not in (0, 5) or data.get("mc_diag_valid") != 1
                or data.get("bp_vbus_valid") != 1 or data.get("bp_temp_valid") != 1
                or data.get("bp_temp_fault") != 0):
            return False, "preparation measurements or fault state invalid"
        if data.get("bp_fault") == 5 and (data.get("mc_fault_reason") != 8
                or data.get("mc_fault_current_mask") != 4 or data.get("mc_fault_occurred_mask") not in (4, 0x404)):
            return False, "preparation permits only specifically identified zero-bus undervoltage"
        # Preparation is not ACK/ARM. Retain a recorded DP occurrence; live
        # arming still requires fault-free powered telemetry for a full window.
        remaining = proof["expires_at"] - time.time()
        if not 0 < remaining <= 3600:
            return False, "qualification expired during trial preparation"
        self._trial_original_cfg = cfg
        gate = PoweredTrialGate(remaining, pair=tuple(proof["pair"]),profile=COAST30_PROFILE if coast30 else "short",
                                wait_without_deadline=tuple(proof["pair"]) == BOOT_TRIAL_PAIR)
        self._trial_original_runlimit = self.start_runlimit_sec
        if coast30:
            self.start_runlimit_sec = 33
        self.hv_arm.set_config(HvArmConfig(enabled=cfg.enabled, ttl_sec=45 if coast30 else min(cfg.ttl_sec, 10),
            min_vdc=max(cfg.min_vdc, 250), max_vdc=min(cfg.max_vdc, 360),
            min_temp_c=cfg.min_temp_c, max_temp_c=min(cfg.max_temp_c, 80),
            confirm="ARM UARTV3 COAST30 50HZ" if coast30 else "ARM UARTV3 TRIAL 3S", profile=ARM_PROFILE_HV,
            trial_gate=gate))
        self.logs.add("POWERED_TRIAL_PREPARED pair=" + "/".join(map(str, proof["pair"]))
                      + f" max_run={gate.max_run_s}s max_freq={gate.max_freq_hz}Hz no_START")
        return True, "prepared, not armed; awaiting 30 seconds of fault-free powered idle observations"

    def cancel_powered_trial(self) -> tuple[bool, str]:
        ok, reason, _ = self.stop_sequence()
        if self._trial_original_cfg is not None:
            self.hv_arm.set_config(self._trial_original_cfg)
            self._trial_original_cfg = None
            self.start_runlimit_sec = self._trial_original_runlimit
            self._trial_original_runlimit = None
        return ok, reason

    def trial_command_check(self, cmd: str) -> tuple[bool, str]:
        if self.hv_arm.cfg.trial_gate is None:
            return True, "ok"
        parts = [p.upper() for p in _cmd_tokens(cmd)]
        if parts in (["STOP"], ["ESTOP"], ["CLEAR"], ["MODE", "VF"]):
            return True, "ok"
        if len(parts) == 3 and parts[:2] in (["SET", "FREQ"], ["SET", "RUNLIMIT"]):
            try:
                value = float(parts[2])
                gate = self.hv_arm.cfg.trial_gate
                if gate.profile==COAST30_PROFILE:
                    if math.isfinite(value) and ((parts[1]=="FREQ" and value in (0,50))
                            or (parts[1]=="RUNLIMIT" and value==33 and not gate.consumed)):
                        return True,"ok"
                    return False,"coast profile fixes 50 Hz and 33 s backup; STOP allowed, active deceleration forbidden"
                ceiling = gate.max_freq_hz if parts[1] == "FREQ" else gate.max_run_s
                if math.isfinite(value) and (0 <= value <= ceiling if parts[1] == "FREQ" else .1 <= value <= ceiling):
                    return True, "ok"
            except ValueError:
                pass
        return False, "powered trial permits only V/f <=10 Hz, run limit <=3 s, CLEAR and stop commands"

    def _precharge_off(self) -> tuple[bool, str]:
        return True, "external-autonomous-no-control"

    def mark_operator_heartbeat(self) -> bool:
        if self._manual_mcu_watchdog:
            ok, error = self.rpc.cmd("CONTROL HEARTBEAT")
            if not ok:
                self.logs.add("MANUAL_OPERATOR_HEARTBEAT_FAIL " + str(error))
                return False
        with self._lock:
            self._operator_heartbeat_ts = time.monotonic()
        return True

    def operator_heartbeat_age(self) -> float:
        with self._lock:
            stamp = self._operator_heartbeat_ts
        if stamp <= 0.0:
            return math.inf
        return max(0.0, time.monotonic() - stamp)

    def operator_heartbeat_fresh(self) -> bool:
        return self.operator_heartbeat_age() <= self.operator_heartbeat_timeout_sec

    def stop_sequence(
        self,
        emergency: bool = False,
        confirm_timeout_sec: float = 0.75,
        poll_sec: float = 0.05,
    ) -> tuple[bool, str, Optional[dict]]:
        """Stop PWM and confirm that every motor-control output is off."""
        self._manual_mcu_watchdog = False
        primary_cmd = "ESTOP" if emergency else "STOP"
        primary_ok, primary_err = self.rpc.cmd(primary_cmd)
        relay_ok, relay_err = self._precharge_off()
        self.hv_arm.disarm()
        self._runtime_bad_monitor.reset()

        deadline = time.monotonic() + max(0.0, float(confirm_timeout_sec))
        status_ok = False
        status: Optional[dict] = None
        status_err = "status unavailable"
        off_confirmed = False
        while True:
            status_ok, candidate, status_err = self.rpc.get()
            if status_ok and candidate is not None:
                status = candidate
                off_confirmed = bool(
                    _status_link_live(candidate)
                    and _as_int(candidate, "bp_status", 0) & 0x01
                    and _as_int(candidate, "pwm", 1) == 0
                    and (_as_int(candidate, "bp_status", 0x20) & 0x20) == 0
                    and _as_int(candidate, "precharge", 1) == 0
                    and (_as_int(candidate, "bp_ext", 0x08) & 0x08) == 0
                )
                if off_confirmed:
                    break
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.0, float(poll_sec)))
        ok = bool(primary_ok and relay_ok and off_confirmed)
        detail = (
            f"{primary_cmd}={primary_err or primary_ok}; "
            f"PRECHARGE_OFF={relay_err or relay_ok}; "
            f"outputs_off={int(off_confirmed)}"
        )
        if not status_ok:
            detail += f"; status={status_err or 'unavailable'}"
        self.logs.add(f"WIFI_STOP_SEQUENCE emergency={int(emergency)} ok={int(ok)} {detail}")
        return ok, detail, status

    def start_sequence(
        self,
        relay_timeout_sec: float = DEFAULT_RELAY_CONFIRM_TIMEOUT_SEC,
        relay_settle_sec: float = DEFAULT_RELAY_SETTLE_SEC,
        run_timeout_sec: float = DEFAULT_RUN_CONFIRM_TIMEOUT_SEC,
        poll_sec: float = 0.05,
        runlimit_sec: Optional[float] = None,
        manual_run: bool = False,
    ) -> tuple[bool, str, Optional[dict]]:
        """Confirm safety, then wait for the autonomous AC soft-start and PWM."""
        if type(manual_run) is not bool or (manual_run and runlimit_sec is not None):
            return False, "manual mode cannot be combined with a timed run limit", None
        effective_limit = self.start_runlimit_sec
        if self.hv_arm.cfg.trial_gate is not None:
            gate=self.hv_arm.cfg.trial_gate
            effective_limit = min(effective_limit, gate.max_run_s)
            if gate.profile==COAST30_PROFILE and runlimit_sec is not None and runlimit_sec!=33:
                return False,"coast profile requires its exact 33-second MCU backup limit",None
            if not self.operator_heartbeat_fresh():
                return False, "powered trial requires a fresh operator heartbeat", None
        if runlimit_sec is not None:
            if (type(runlimit_sec) not in (int, float) or not math.isfinite(runlimit_sec)
                    or not 0.1 <= runlimit_sec <= effective_limit):
                return False, "requested run limit must be finite, positive and no greater than profile limit", None
            effective_limit = float(runlimit_sec)
        st_ok, status, st_err = self.rpc.get()
        if manual_run and not (manual_scalar_supported(status) and self.control_access.enabled and
                self.hv_arm.cfg.enabled and self.hv_arm.cfg.profile==ARM_PROFILE_HV and
                self.hv_arm.cfg.trial_gate is None and self.operator_heartbeat_fresh()):
            return False, "manual scalar requires matching firmware, authenticated live control and normal HV profile", status
        allowed, guard_err = command_guard_check(
            "START", status if st_ok else None, self.command_guard
        )
        if not allowed:
            detail = guard_err if st_ok else f"{guard_err}: {st_err or 'no status'}"
            self.logs.add(f"WIFI_START_REJECT guard {detail}")
            return False, detail, status

        if self.hv_arm.cfg.enabled:
            arm_ok, arm_err = self.hv_arm.command_allowed(status)
            if not arm_ok:
                self.logs.add(f"WIFI_START_REJECT arm {arm_err}")
                return False, arm_err, status

        if status is None:
            return False, "status unavailable", None
        if _as_int(status, "precharge", 0) != 0 or (_as_int(status, "bp_ext", 0) & 0x08) != 0:
            self.stop_sequence(emergency=False)
            return False, "reserved precharge bit was nonzero; outputs were forced off, retry START", status

        self._manual_start_requested = manual_run
        return self._start_without_precharge(status, run_timeout_sec, poll_sec, effective_limit)

    def _start_without_precharge(
        self,
        initial_status: dict,
        run_timeout_sec: float,
        poll_sec: float,
        effective_limit: Optional[float] = None,
    ) -> tuple[bool, str, Optional[dict]]:
        mcsdk_backend = _as_int(initial_status, "bp_mcsdk_telemetry", 0) == 1
        self.logs.add(
            "WIFI_START_STEP SOFTSTART owner=external-autonomous "
            f"ready={_as_int(initial_status, 'bp_softstart_ready', 0)} "
            f"mcsdk={int(mcsdk_backend)}"
        )
        arm_ok, arm_err = self.hv_arm.command_allowed(initial_status)
        if self.hv_arm.cfg.enabled and not arm_ok:
            self.stop_sequence(emergency=False)
            self.logs.add(f"WIFI_START_FAIL arm_recheck {arm_err}")
            return False, arm_err, initial_status

        if manual_scalar_supported(initial_status):
            mode = "MANUAL" if self._manual_start_requested else "BOUNDED"
            setup = ["SET RUNMODE " + mode]
            if self._manual_start_requested:
                setup.append("CONTROL HEARTBEAT")
                effective_limit = 0.0
            for command in setup:
                setup_ok, setup_error = self.rpc.cmd(command)
                if not setup_ok:
                    self.stop_sequence()
                    return False, "manual setup failed: " + str(setup_error), initial_status
            self._manual_mcu_watchdog = self._manual_start_requested
            self.hv_arm.set_manual_session(self._manual_start_requested)
        runlimit_cmd = f"SET RUNLIMIT {self.start_runlimit_sec if effective_limit is None else effective_limit:.3f}"
        limit_ok, limit_err = self.rpc.cmd(runlimit_cmd)
        if not limit_ok:
            self.stop_sequence(emergency=False)
            detail = f"run limit rejected: {limit_err or 'no acknowledgement'}"
            self.logs.add(f"WIFI_START_FAIL runlimit {detail}")
            return False, detail, initial_status

        gate = self.hv_arm.cfg.trial_gate
        if gate is not None:
            read_ok, current, read_err = self.rpc.get()
            allowed, reason = self.hv_arm.command_allowed(current if read_ok else None)
            if not read_ok or not allowed or not self.operator_heartbeat_fresh():
                self.stop_sequence()
                return False, "trial final pre-START check failed: " + (read_err or reason), current
            # Consume before attempting START, including a lost/rejected reply.
            gate.consume()
            self._powered_trial_spent = True
            self.logs.add(f"POWERED_TRIAL_CONSUMED max_run={gate.max_run_s}s stop_after={gate.stop_after_s}s")
        start_ok, start_err = self.rpc.cmd("START")
        if not start_ok:
            self.stop_sequence(emergency=True)
            detail = f"START rejected: {start_err or 'no acknowledgement'}"
            self.logs.add(f"WIFI_START_FAIL start_cmd {detail}")
            return False, detail, initial_status

        run_deadline = time.monotonic() + max(0.0, float(run_timeout_sec))
        run_status: Optional[dict] = None
        last_run_error = "PWM did not start"
        while True:
            read_ok, candidate, read_err = self.rpc.get()
            if read_ok and candidate is not None:
                self.maybe_log_fault_diagnostics(candidate)
                run_status = candidate
                run_ok, run_err = output_sequence_health_check(
                    candidate,
                    self.hv_arm.cfg,
                    self.command_guard,
                    vbus_calibrated=self.vbus_calibration.is_valid(candidate),
                )
                reserved_relay_bit = bool(
                    _as_int(candidate, "precharge", 0) != 0
                    or (_as_int(candidate, "bp_ext", 0) & 0x08) != 0
                )
                softstart_ready = (
                    _as_int(candidate, "bp_softstart_ready", 0) == 1
                    if mcsdk_backend
                    else True
                )
                nucleo_pwm_ok = (
                    (_as_int(candidate, "bp_status", 0) & 0x20) != 0
                    if mcsdk_backend
                    else True
                )
                running = (
                    _as_int(candidate, "pwm", 0) == 1
                    and str(candidate.get("state", "")).upper()
                    in ("VF_RUN", "FOC_ALIGN", "FOC_RUN")
                    and not reserved_relay_bit
                    and softstart_ready
                    and nucleo_pwm_ok
                )
                if (run_ok and not self._manual_start_requested and
                        bounded_run_complete(candidate, initial_status, effective_limit)):
                    self.hv_arm.disarm()
                    self.logs.add("WIFI_BOUNDED_COMPLETE MCU deadline; HTTP response may be late")
                    return True, "Timed run already completed by MCU; outputs off", candidate
                if run_ok and identification_point_complete(candidate,initial_status):
                    self.hv_arm.disarm()
                    return True,"Native identification completed before HTTP response",candidate
                if run_ok and running:
                    self.hv_arm.mark_started()
                    self.logs.add(
                        f"WIFI_START_OK state={candidate.get('state')} "
                        f"freq={_as_float(candidate, 'freq', 0.0):.2f} "
                        f"speed={_as_float(candidate, 'speed', 0.0):.1f} "
                        "softstart=external-ready"
                    )
                    return True, "PWM started; external soft-start bus is stable", candidate
                if not softstart_ready:
                    last_run_error = "external soft-start bus is not stable yet"
                else:
                    last_run_error = run_err if not run_ok else "PWM did not enter a running state"
            else:
                last_run_error = read_err or "status unavailable"
            if time.monotonic() >= run_deadline:
                self.stop_sequence(emergency=True)
                detail = f"START confirmation failed: {last_run_error}"
                self.logs.add(f"WIFI_START_FAIL run_feedback {detail}")
                return False, detail, run_status
            time.sleep(max(0.0, float(poll_sec)))

    def arm_snapshot(self, status: Optional[dict] = None) -> dict:
        snapshot = self.hv_arm.snapshot()
        available = [name for name in (ARM_PROFILE_HV, ARM_PROFILE_LV) if name in self.arm_profiles]
        snapshot["hmi_arm_profiles"] = available
        snapshot["hmi_start_runlimit_s"] = round(self.start_runlimit_sec, 1)
        snapshot["hmi_manual_scalar_supported"] = int(manual_scalar_supported(status))
        gate = self.hv_arm.cfg.trial_gate
        snapshot["hmi_local_stop_latched"] = local_stop_latched(status)
        snapshot["hmi_powered_trial_supported"] = 1
        snapshot["hmi_powered_trial_enabled"] = 0
        snapshot["hmi_powered_trial_ready"] = 0
        if gate is not None:
            ready, reason = gate.ready(status, self.vbus_calibration.is_valid(status))
            snapshot.update(gate.snapshot())
            snapshot["hmi_powered_trial_ready"] = int(ready)
            snapshot["hmi_powered_trial_reason"] = reason
            snapshot["hmi_start_runlimit_s"] = min(snapshot["hmi_start_runlimit_s"], gate.max_run_s)
        snapshot["hmi_bounded_start_request_supported"] = 1
        snapshot["hmi_precharge_relay_present"] = 0
        snapshot["hmi_external_softstart_ready"] = int(
            status is not None and _as_int(status, "bp_softstart_ready", 0) == 1
        )
        calibration = self.vbus_calibration.snapshot(status)
        snapshot["hmi_vbus_hv_calibrated"] = int(calibration["valid"])
        snapshot["hmi_vbus_calibration_reason"] = calibration["reason"]
        snapshot["hmi_vbus_zero_captured"] = int(calibration["zero_captured"])
        snapshot["hmi_vbus_high_captured"] = int(calibration["high_captured"])
        snapshot["hmi_vbus_zero_meter_vdc"] = calibration["zero_meter_vdc"]
        snapshot["hmi_vbus_zero_mc_vdc"] = calibration["zero_mc_vdc"]
        snapshot["hmi_vbus_high_meter_vdc"] = calibration["high_meter_vdc"]
        snapshot["hmi_vbus_high_mc_vdc"] = calibration["high_mc_vdc"]
        current_cfg = self.hv_arm.cfg
        switch_ok, _ = arm_profile_switch_precheck(status, current_cfg) if status is not None else (False, "")
        snapshot["hmi_arm_profile_switch_ready"] = int(switch_ok and not snapshot["hmi_hv_armed"])
        heartbeat_age = self.operator_heartbeat_age()
        snapshot["hmi_operator_heartbeat_age_s"] = round(heartbeat_age, 2) if math.isfinite(heartbeat_age) else None
        snapshot["hmi_operator_heartbeat_ok"] = int(
            not self.control_access.enabled or heartbeat_age <= self.operator_heartbeat_timeout_sec
        )
        snapshot["hmi_operator_heartbeat_timeout_s"] = self.operator_heartbeat_timeout_sec
        return snapshot

    def switch_arm_profile(self, profile: str, status: Optional[dict]) -> tuple[bool, str]:
        if self.hv_arm.cfg.trial_gate is not None:
            return False, "cancel powered trial before changing profile"
        target = str(profile).strip().lower()
        cfg = self.arm_profiles.get(target)
        if cfg is None:
            return False, f"unsupported arm profile: {profile}"
        ok, reason = arm_profile_switch_precheck(status, cfg)
        if not ok:
            return False, reason

        self.hv_arm.set_config(cfg)
        if target == ARM_PROFILE_LV:
            self.command_guard.max_vdc = min(self.guard_max_vdc, cfg.max_vdc)
            self.command_guard.allow_hv = False
        else:
            self.command_guard.max_vdc = self.guard_max_vdc
            self.command_guard.allow_hv = True
        self.start_runlimit_sec = self.profile_runlimits.get(target, DEFAULT_START_RUNLIMIT_SEC)
        self._runtime_bad_monitor.reset()
        return True, "profile selected"

    def start_safety_watchdog(self) -> None:
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(target=self._safety_watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop_safety_watchdog(self) -> None:
        self._watchdog_stop.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=1.0)

    def _safety_watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(0.2):
            reason = ""
            if self.hv_arm.take_expired_session_action():
                reason = "HV_ARM_EXPIRED"
            elif self.hv_arm.runtime_monitor_required():
                if self.control_access.enabled and not self.operator_heartbeat_fresh():
                    reason = f"OPERATOR_HEARTBEAT_LOST age={self.operator_heartbeat_age():.2f}s"
                    self.hv_arm.disarm()
                else:
                    status_ok, status, status_err = self.rpc.get()
                    if status_ok and status is not None:
                        self.maybe_log_fault_diagnostics(status)
                    live_ok, live_err = hv_runtime_check(
                        status if status_ok else None,
                        self.hv_arm.cfg,
                        allow_nonzero_bad=True,
                        vbus_calibrated=self.vbus_calibration.is_valid(status if status_ok else None),
                    )
                    if live_ok and status is not None:
                        live_ok, bad_err = self._runtime_bad_monitor.observe(status)
                        if live_ok and bad_err != "ok":
                            self.logs.add(f"HV_RUNTIME_UART_WARN {bad_err}")
                        elif not live_ok:
                            live_err = bad_err
                    if not live_ok:
                        gate=self.hv_arm.cfg.trial_gate
                        reason = ("POWERED_TRIAL_RUNLIMIT" if gate is not None and live_err == gate.deadline_reason
                                  else f"HV_RUNTIME_REJECT {status_err or live_err}")
                        self.hv_arm.disarm()
            else:
                self._runtime_bad_monitor.reset()
                # Keep a small idle prehistory even when no browser is open.
                # Armed operation already polls above; do not add a second poll.
                now = time.monotonic()
                if now - self._last_diag_idle_poll >= 1.0:
                    self._last_diag_idle_poll = now
                    status_ok, status, _ = self.rpc.get()
                    if status_ok and status is not None:
                        self.maybe_log_fault_diagnostics(status)
                    gate = self.hv_arm.cfg.trial_gate
                    if gate is not None:
                        idle = status if status_ok else None
                        gate.observe(idle, self.vbus_calibration.is_valid(idle))
            if not reason:
                continue
            stop_ok, stop_err = self.rpc.cmd("STOP")
            normal_trial_stop = False
            if reason == "POWERED_TRIAL_RUNLIMIT" and stop_ok:
                read_ok, stopped, _ = self.rpc.get()
                normal_trial_stop = bool(read_ok and stopped is not None and _status_link_live(stopped)
                    and _as_int(stopped, "pwm", 1) == 0 and not (_as_int(stopped, "bp_status", 0x20) & 0x20)
                    and _as_int(stopped, "bp_ext", 1) == 0)
            # A normal deadline is not an emergency; unconfirmed STOP still escalates.
            estop_ok, estop_err = ((True, "not-required-after-confirmed-trial-stop") if normal_trial_stop
                                  else self.rpc.cmd("ESTOP"))
            relay_ok, relay_err = self._precharge_off()
            self.logs.add(
                f"{reason} "
                f"stop_ok={int(stop_ok)} stop_err={stop_err or '-'} "
                f"estop_ok={int(estop_ok)} estop_err={estop_err or '-'} "
                f"relay_ok={int(relay_ok)} relay_err={relay_err or '-'}"
            )

    def maybe_log_fault_diagnostics(self, data: dict) -> None:
        data["hmi_local_stop_latched"] = local_stop_latched(data)
        data["mc_fault_detail"] = motor_fault_detail(data)
        data["mc_sd_live"] = sd_live_status(data)
        data["mc_fault_detail"] += "; " + data["mc_sd_live"]["summary_ru"]
        trace=uart_reject_status(data)
        if trace.get("available"):data["mc_fault_detail"]+="; "+trace["summary_ru"]
        for line in self._fault_recorder.observe(data):
            self.logs.add(line)
        data.update(self._fault_recorder.snapshot())
        reason = _as_int(data, "mc_fault_reason", 0)
        active = _as_int(data, "bp_fault", 0)
        key = None
        if reason or active or local_stop_latched(data):
            key = tuple(data.get(k) for k in ("mc_fw_build", "mc_diag_valid", "mc_fault_reason",
                                             "mc_uart_error_flags", "mc_fault_current_mask",
                                             "mc_fault_occurred_mask", "mc_fault_motor_state",
                                             "mc_fault_sequence", "mc_fault_tx_status", "mc_bad_cnt",
                                             "mc_last_bad_reason", "mc_last_uart_error_flags", "mc_last_tx_status"))
            key += (active, local_stop_latched(data))
        with self._lock:
            if key == self._last_fault_diag_key:
                return
            self._last_fault_diag_key = key
        if key is not None:
            self.logs.add(f"MC_FAULT_DIAG code={active} bad={_as_int(data, 'bp_bad_cnt', 0)} "
                          + motor_fault_detail(data))

    def maybe_log_status(self, data: dict) -> None:
        self.maybe_log_fault_diagnostics(data)
        for index, record in enumerate(data.get("mc_break_snapshots", [])):
            if not record.get("available") or not record.get("captured"):
                continue
            key = json.dumps(record["raw"], sort_keys=True)
            with self._lock:
                if not hasattr(self, "_last_break_snapshot_keys"):
                    self._last_break_snapshot_keys = {}
                changed = self._last_break_snapshot_keys.get(index) != key
                self._last_break_snapshot_keys[index] = key
            if changed:
                self.logs.add("IPM_BREAK_SNAPSHOT " + json.dumps(record, sort_keys=True))
        now = _now_ts()
        with self._lock:
            if (now - self._last_status_log) < self._status_log_interval:
                return
            self._last_status_log = now
        line = (
            f"STAT state={data.get('state')} mode={data.get('mode')} pwm={data.get('pwm')} "
            f"freq={data.get('freq'):.2f} speed={data.get('speed'):.1f} vdc={data.get('vdc'):.2f} "
            f"bp_temp_c={data.get('bp_temp_c', 0.0):.1f} bp_temp_fault={data.get('bp_temp_fault', 0)} "
            f"bp_phase_c_v={data.get('bp_phase_c_v', 0.0):.3f} bp_phase_c_virtual={data.get('bp_phase_c_virtual', 0)} "
            f"fan_duty={data.get('fan_duty', 0.0):.2f} bp_fan_rpm={data.get('bp_fan_rpm', 0.0):.0f} "
            f"bp_cmd_mode={data.get('bp_cmd_mode', 0)} bp_foc_backend={data.get('bp_foc_backend', 0)}"
            f" mc_diag_valid={data.get('mc_diag_valid', 0)} mc_fault_reason={data.get('mc_fault_reason', 0)}"
            f" hmi_local_stop_latched={local_stop_latched(data)}"
        )
        self.logs.add(line)


class Handler(BaseHTTPRequestHandler):
    server_version = "UNOQHMI/0.1"

    def _send_json(self, payload: dict, code: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_text(self, text: str, code: int = 200, filename: Optional[str] = None) -> None:
        data = text.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            if filename:
                self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_static(self, name: str, content_type: str) -> None:
        base = os.path.dirname(__file__)
        path = os.path.join(base, "static", name)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if name == "index.html" and self.server.app.control_access.enabled:
                cookie=self.server.app.ui_sessions.issue(self.headers.get("Cookie", ""))
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _require_control_access(self, mark_heartbeat: bool = True) -> bool:
        cfg = self.server.app.control_access  # type: ignore[attr-defined]
        if not cfg.enabled:
            return True
        expected = cfg.read_token()
        provided = self.headers.get("X-UNOQ-Control-Token", "")
        header_ok = bool(expected and provided and provided.isascii() and secrets.compare_digest(provided, expected))
        cookie_ok = self.server.app.ui_sessions.valid(self.headers.get("Cookie", ""))
        if header_ok or cookie_ok:
            if mark_heartbeat:
                if self.server.app.mark_operator_heartbeat() is False:  # type: ignore[attr-defined]
                    self._send_json({"ok":False,"error":"MCU operator heartbeat was not acknowledged"},503)
                    return False
            return True
        peer = self.client_address[0] if self.client_address else "unknown"
        self.server.app.logs.add(f"AUTH_REJECT peer={peer} path={urlparse(self.path).path}")  # type: ignore[attr-defined]
        self._send_json({"ok": False, "error": "control access key is missing or invalid"}, 401)
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_static("style.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/uart-reject":
            if not self._require_control_access(mark_heartbeat=False):return
            ok,data,err=self.server.app.rpc.get()
            if not ok or data is None:
                self._send_json({"ok":False,"error":err or "no response"},503);return
            self._send_json({"ok":True,"data":uart_reject_status(data)});return
        if parsed.path == "/api/bkin-trace":
            if not self._require_control_access(mark_heartbeat=False):
                return
            ok, data, err = self.server.app.rpc.get()
            if not ok or data is None:
                self._send_json({"ok": False, "error": err or "no response"}, 503)
                return
            self.server.app.maybe_log_status(data)
            self._send_json({"ok": True, "data": bkin_wave_status(data)})
            return
        if parsed.path == "/api/break-snapshot":
            if not self._require_control_access(mark_heartbeat=False):
                return
            ok, data, err = self.server.app.rpc.get()
            if not ok or data is None:
                self._send_json({"ok": False, "error": err or "no response"}, 503)
                return
            self.server.app.maybe_log_status(data)
            fields = {k: v for k, v in data.items() if k.startswith("mc_break_")}
            self._send_json({"ok": True, "data": fields})
            return
        if parsed.path == "/api/identification":
            if not self._require_control_access(mark_heartbeat=False):return
            try:page=int(parse_qs(parsed.query).get("page",["0"])[0])
            except (ValueError,TypeError):self._send_json({"ok":False,"error":"invalid page"},400);return
            if not 0<=page<13:self._send_json({"ok":False,"error":"invalid page"},400);return
            app=self.server.app
            with app.control_lock:
                ok,data,err=app.rpc.get()
                if not ok or not data or data.get("pwm")!=0 or data.get("state")!="SAFE" or data.get("id_complete")!=1:
                    self._send_json({"ok":False,"error":"No complete stopped capture"},409);return
                crc=data.get("id_result_crc")
                ok,err=app.rpc.cmd(f"IDENT PAGE {page}")
                if not ok:self._send_json({"ok":False,"error":err},409);return
                ok,data,err=app.rpc.get()
                if not ok or data.get("id_view_page")!=page or data.get("id_result_crc")!=crc or data.get("id_complete")!=1:
                    self._send_json({"ok":False,"error":"Capture page changed"},409);return
                self._send_json({"ok":True,"page":page,"crc32c":crc,"hex":data.get("id_page_hex"),"run_id":data.get("id_run_id")});return
        if parsed.path == "/api/status":
            self._handle_status()
            return
        if parsed.path == "/api/logs":
            if not self._require_control_access():
                return
            self._handle_logs(parsed)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        protected = {
            "/api/cmd",
            "/api/algorithm",
            "/api/start-sequence",
            "/api/hv-arm",
            "/api/arm-profile",
            "/api/calibration/vbus",
            "/api/operator-heartbeat",
            "/api/powered-trial",
        }
        if parsed.path in protected and not self._require_control_access():
            return
        if parsed.path == "/api/algorithm":
            request=self._read_json();algorithm=request.get("algorithm")
            if type(algorithm) is not int or algorithm not in (1,2,3,4):
                self._send_json({"ok":False,"error":"Неизвестный алгоритм"},400);return
            app=self.server.app
            with app.control_lock:
                ok,status,err=app.rpc.get()
                if not ok or not status or (status.get("fw_build"),status.get("mc_fw_build"))!=(2026103015,2026103016) or status.get("research_native_caps")!=15 or status.get("research_native_valid")!=1 or status.get("pwm")!=0 or status.get("state")!="SAFE" or not 0<=status.get("mc_age_ms",9999)<300:
                    self._send_json({"ok":False,"error":"Сначала остановите привод; нужна свежая связь"},409);return
                ok,err=app.rpc.cmd("SET ALGORITHM "+{1:"VF",2:"FOC",3:"ADAPTIVE_PWM",4:"IDENT"}[algorithm])
                app.logs.add(f"ALGORITHM_CONFIG {algorithm} accepted={int(ok)}")
            self._send_json({"ok":ok,"error":err or ""},200 if ok else 409);return
        if parsed.path == "/api/cmd":
            self._handle_cmd()
            return
        if parsed.path == "/api/start-sequence":
            self._handle_start_sequence()
            return
        if parsed.path == "/api/powered-trial":
            self._handle_powered_trial()
            return
        if parsed.path == "/api/stop-sequence":
            self._handle_stop_sequence()
            return
        if parsed.path == "/api/hv-arm":
            self._handle_hv_arm()
            return
        if parsed.path == "/api/arm-profile":
            self._handle_arm_profile()
            return
        if parsed.path == "/api/calibration/vbus":
            self._handle_vbus_capture()
            return
        if parsed.path == "/api/operator-heartbeat":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/firmware/update":
            self._handle_firmware_update(parsed)
            return
        self.send_error(404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_cmd(self) -> None:
        data = self._read_json()
        cmd = str(data.get("cmd", "")).strip()
        if not cmd:
            self._send_json({"ok": False, "error": "missing cmd"}, 400)
            return
        if _cmd_head(cmd) == "NTC":
            self._send_json({"ok": False, "error": "unsupported: STEVAL J2-21 is not connected"}, 400)
            return
        if _cmd_head(cmd) in ("PRECHARGE", "RELAY"):
            self._send_json({"ok": False, "error": "unsupported: external soft-start is autonomous"}, 400)
            return
        with self.server.app.control_lock:  # type: ignore[attr-defined]
            self._handle_cmd_locked(cmd)

    def _handle_start_sequence(self) -> None:
        app = self.server.app  # type: ignore[attr-defined]
        request = self._read_json()
        if not isinstance(request, dict) or ("runlimit_s" in request and request["runlimit_s"] is None):
            self._send_json({"ok": False, "error": "numeric runlimit_s required"}, 400)
            return
        with app.control_lock:
            if "manual" in request:
                ok, detail, status = app.start_sequence(manual_run=request["manual"],runlimit_sec=request.get("runlimit_s"))
            elif "runlimit_s" in request:
                ok, detail, status = app.start_sequence(runlimit_sec=request["runlimit_s"])
            else:
                ok, detail, status = app.start_sequence()
        self._send_json(
            {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
            200 if ok else 409,
        )

    def _handle_powered_trial(self) -> None:
        request = self._read_json()
        if not isinstance(request, dict):
            self._send_json({"ok": False, "error": "trial request must be an object"}, 400)
            return
        app = self.server.app
        with app.control_lock:
            if request.get("action") == "prepare":
                ok, reason = app.prepare_powered_trial(request.get("qualification"), str(request.get("confirm", "")))
            elif request.get("action") == "cancel":
                ok, reason = app.cancel_powered_trial()
            else:
                ok, reason = False, "trial action must be prepare or cancel; use the bounded START endpoint"
        app.logs.add(f"POWERED_TRIAL_ACTION {request.get('action')} ok={int(ok)} {reason}")
        self._send_json({"ok": ok, "message": reason if ok else "", "error": "" if ok else reason}, 200 if ok else 409)

    def _handle_stop_sequence(self) -> None:
        request = self._read_json()
        emergency = bool(request.get("emergency", False))
        app = self.server.app  # type: ignore[attr-defined]
        with app.control_lock:
            ok, detail, status = app.stop_sequence(emergency=emergency)
        self._send_json(
            {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
            200 if ok else 500,
        )

    def _handle_cmd_locked(self, cmd: str) -> None:
        app = self.server.app  # type: ignore[attr-defined]
        if command_requests_start(cmd):
            ok, detail, status = app.start_sequence()
            self._send_json(
                {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
                200 if ok else 409,
            )
            return
        normalized = " ".join(_cmd_tokens(cmd)).upper()
        if normalized.startswith("ENC BUS ") and app.hv_arm.snapshot()["hmi_hv_armed"]:
            self._send_json({"ok": False, "error": "Disarm before changing encoder bus mode"}, 409)
            return
        parts = _cmd_tokens(cmd)
        frequency_stop = False
        if len(parts) == 3 and parts[0].upper() == "SET" and parts[1].upper() == "FREQ":
            try:
                frequency_stop = float(parts[2]) == 0.0
            except ValueError:
                pass
        if normalized in ("STOP", "ESTOP") or frequency_stop:
            ok, detail, status = app.stop_sequence(emergency=normalized == "ESTOP")
            self._send_json(
                {"ok": ok, "message": detail if ok else "", "error": "" if ok else detail, "status": status},
                200 if ok else 500,
            )
            return
        allowed, reason = app.trial_command_check(cmd)
        if not allowed:
            app.logs.add(f"POWERED_TRIAL_CMD_REJECT {cmd} {reason}")
            self._send_json({"ok": False, "error": reason}, 409)
            return
        guard_cfg = self.server.app.command_guard  # type: ignore[attr-defined]
        armed_output_command = False
        if command_requests_start(cmd) or command_requests_service_output(cmd):
            st_ok, st_data, st_err = self.server.app.rpc.get()  # type: ignore[attr-defined]
            allowed, guard_err = command_guard_check(cmd, st_data if st_ok else None, guard_cfg)
            if not allowed:
                err = guard_err if st_ok else f"{guard_err}: {st_err or 'no status'}"
                self.server.app.logs.add(f"CMD_REJECT {cmd} {err}")  # type: ignore[attr-defined]
                self._send_json({"ok": False, "error": err, "status": st_data}, 409)
                return
            armed_output_command = bool(self.server.app.hv_arm.cfg.enabled)  # type: ignore[attr-defined]
            if armed_output_command:
                arm_ok, arm_err = self.server.app.hv_arm.command_allowed(st_data)  # type: ignore[attr-defined]
                if not arm_ok:
                    self.server.app.logs.add(f"CMD_REJECT {cmd} {arm_err}")  # type: ignore[attr-defined]
                    self._send_json({"ok": False, "error": arm_err, "status": st_data}, 409)
                    return
        if command_requests_start(cmd):
            runlimit_cmd = f"SET RUNLIMIT {self.server.app.start_runlimit_sec:.3f}"  # type: ignore[attr-defined]
            limit_ok, limit_err = self.server.app.rpc.cmd(runlimit_cmd)  # type: ignore[attr-defined]
            if not limit_ok:
                self.server.app.logs.add(f"CMD_FAIL {runlimit_cmd} {limit_err}")  # type: ignore[attr-defined]
                self._send_json({"ok": False, "error": f"run limit rejected: {limit_err}"}, 500)
                return
            self.server.app.logs.add(f"CMD {runlimit_cmd}")  # type: ignore[attr-defined]
        ok, err = self.server.app.rpc.cmd(cmd)  # type: ignore[attr-defined]
        if ok:
            if armed_output_command:
                self.server.app.hv_arm.mark_started()  # type: ignore[attr-defined]
            elif command_releases_service_output(cmd):
                status_ok, status, _ = self.server.app.rpc.get()  # type: ignore[attr-defined]
                if status_ok and not status_has_active_outputs(status):
                    self.server.app.hv_arm.mark_stopped()  # type: ignore[attr-defined]
            if _cmd_head(cmd) in ("STOP", "ESTOP"):
                self.server.app.hv_arm.disarm()  # type: ignore[attr-defined]
            self.server.app.logs.add(f"CMD {cmd}")  # type: ignore[attr-defined]
            self._send_json({"ok": True})
        else:
            self.server.app.logs.add(f"CMD_FAIL {cmd} {err}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": err}, 500)

    def _handle_status(self) -> None:
        ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
        if not ok or data is None:
            self._send_json({"ok": False, "error": err or "no response"}, 503)
            return
        data.update(self.server.app.arm_snapshot(data))  # type: ignore[attr-defined]
        data["hmi_ui_session_active"] = int(self.server.app.ui_sessions.valid(self.headers.get("Cookie", "")))
        data["hmi_control_auth_required"] = int(self.server.app.control_access.enabled)  # type: ignore[attr-defined]
        self.server.app.maybe_log_status(data)  # type: ignore[attr-defined]
        self._send_json({"ok": True, "data": data})

    def _handle_hv_arm(self) -> None:
        request = self._read_json()
        with self.server.app.control_lock:  # type: ignore[attr-defined]
            self._handle_hv_arm_locked(request)

    def _handle_hv_arm_locked(self, request: dict) -> None:
        action = str(request.get("action", "arm")).strip().lower()
        arm = self.server.app.hv_arm  # type: ignore[attr-defined]
        if action == "disarm":
            arm.disarm()
            stop_ok, stop_err = self.server.app.rpc.cmd("STOP")  # type: ignore[attr-defined]
            estop_ok, estop_err = self.server.app.rpc.cmd("ESTOP")  # type: ignore[attr-defined]
            relay_ok, relay_err = self.server.app._precharge_off()  # type: ignore[attr-defined]
            self.server.app.logs.add("HV_DISARM")  # type: ignore[attr-defined]
            ok = bool(stop_ok and estop_ok and relay_ok)
            self._send_json(
                {
                    "ok": ok,
                    "error": "" if ok else (
                        f"STOP={stop_err or stop_ok}; ESTOP={estop_err or estop_ok}; "
                        f"PRECHARGE={relay_err or relay_ok}"
                    ),
                    "arm": arm.snapshot(),
                },
                200 if ok else 500,
            )
            return
        if action != "arm":
            self._send_json({"ok": False, "error": "unsupported HV arm action"}, 400)
            return
        st_ok, st_data, st_err = self.server.app.rpc.get()  # type: ignore[attr-defined]
        if not st_ok or st_data is None:
            self._send_json({"ok": False, "error": st_err or "status unavailable"}, 503)
            return
        ok, reason = arm.arm(str(request.get("confirm", "")), st_data)
        if not ok:
            self.server.app.logs.add(f"HV_ARM_REJECT {reason}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": reason, "status": st_data, "arm": arm.snapshot()}, 409)
            return
        self.server.app.logs.add(  # type: ignore[attr-defined]
            f"ARM profile={arm.cfg.profile} ttl={arm.cfg.ttl_sec:.1f}s vdc={_status_vdc(st_data):.1f}"
        )
        self._send_json({"ok": True, "arm": self.server.app.arm_snapshot(st_data)})  # type: ignore[attr-defined]

    def _handle_arm_profile(self) -> None:
        request = self._read_json()
        profile = str(request.get("profile", "")).strip().lower()
        app = self.server.app  # type: ignore[attr-defined]
        with app.control_lock:
            stop_ok, stop_err = app.rpc.cmd("STOP")
            relay_ok, relay_err = app._precharge_off()
            app.hv_arm.disarm()
            if not stop_ok or not relay_ok:
                error = f"safe shutdown failed: STOP={stop_err or stop_ok}; PRECHARGE={relay_err or relay_ok}"
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {error}")
                self._send_json({"ok": False, "error": error}, 500)
                return
            time.sleep(0.05)
            st_ok, st_data, st_err = app.rpc.get()
            if not st_ok or st_data is None:
                error = st_err or "status unavailable"
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {error}")
                self._send_json({"ok": False, "error": error}, 503)
                return
            ok, reason = app.switch_arm_profile(profile, st_data)
            if not ok:
                app.logs.add(f"ARM_PROFILE_REJECT {profile or '-'} {reason}")
                self._send_json(
                    {"ok": False, "error": reason, "status": st_data, "arm": app.arm_snapshot(st_data)},
                    409,
                )
                return
            app.logs.add(f"ARM_PROFILE {profile} runlimit={app.start_runlimit_sec:.1f}s")
            self._send_json({"ok": True, "arm": app.arm_snapshot(st_data)})

    def _handle_vbus_capture(self) -> None:
        request = self._read_json()
        action = str(request.get("action", "capture")).strip().lower()
        app = self.server.app  # type: ignore[attr-defined]
        if action == "reset":
            with app.control_lock:
                stop_ok, stop_err, _ = app.stop_sequence(emergency=False)
                if not stop_ok:
                    self._send_json({"ok": False, "error": f"safe stop failed: {stop_err}"}, 500)
                    return
                calibration = app.vbus_calibration.reset()
                app.logs.add("VBUS_CALIBRATION_RESET")
            self._send_json({"ok": True, "calibration": calibration})
            return
        if action != "capture":
            self._send_json({"ok": False, "error": "unsupported Vbus calibration action"}, 400)
            return
        try:
            meter_vdc = float(request["meter_vdc"]) if request.get("meter_vdc") not in (None, "") else None
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "meter_vdc must be a number"}, 400)
            return
        if meter_vdc is not None and (not math.isfinite(meter_vdc) or meter_vdc < 0.0 or meter_vdc > 450.0):
            self._send_json({"ok": False, "error": "meter_vdc must be within 0..450 V"}, 400)
            return

        samples: list[dict] = []
        with app.control_lock:
            app.hv_arm.disarm()
            for _ in range(VBUS_CAL_CAPTURE_SAMPLES):
                ok, data, err = app.rpc.get()
                if not ok or data is None:
                    self._send_json({"ok": False, "error": err or "status unavailable"}, 503)
                    return
                safe, reason = vbus_capture_precheck(data, meter_vdc)
                if not safe:
                    app.logs.add(f"VBUS_CAPTURE_REJECT {reason}")
                    self._send_json({"ok": False, "error": reason, "status": data}, 409)
                    return
                samples.append(data)
                time.sleep(0.02)

            capture_identity = _vbus_calibration_identity(samples[0])
            if any(_vbus_calibration_identity(sample) != capture_identity for sample in samples[1:]):
                reason = "firmware or telemetry identity changed during capture"
                app.logs.add(f"VBUS_CAPTURE_REJECT {reason}")
                self._send_json({"ok": False, "error": reason}, 409)
                return

            capture = vbus_capture_summary(samples, meter_vdc)
            calibration = app.vbus_calibration.snapshot(samples[-1])
            calibration_ok = True
            calibration_reason = "measurement-only capture"
            if meter_vdc is not None:
                calibration_ok, calibration_reason, calibration = app.vbus_calibration.record_capture(
                    capture, samples[-1]
                )
        raw = capture["bp_vbus_raw"]
        scaled = capture["bp_vdc"]
        meter_text = "none" if meter_vdc is None else f"{meter_vdc:.3f}"
        app.logs.add(
            "VBUS_CAPTURE "
            f"meter_vdc={meter_text} raw_mean={raw['mean']:.3f} raw_std={raw['std']:.3f} "
            f"raw_min={raw['min']:.0f} raw_max={raw['max']:.0f} vdc_mean={scaled['mean']:.3f} "
            f"calibration_ok={int(calibration_ok)} calibration_reason={calibration_reason}"
        )
        if meter_vdc is not None and not calibration_ok:
            self._send_json(
                {
                    "ok": False,
                    "error": calibration_reason,
                    "capture": capture,
                    "calibration": calibration,
                },
                409,
            )
            return
        self._send_json(
            {
                "ok": True,
                "capture": capture,
                "calibration": calibration,
                "message": calibration_reason,
            }
        )

    def _handle_logs(self, parsed) -> None:
        query = parse_qs(parsed.query)
        try:
            hours = float(query.get("hours", ["24"])[0])
        except ValueError:
            hours = 24.0
        download = query.get("download", ["0"])[0] in ("1", "true", "yes")
        since = _now_ts() - (hours * 3600.0)
        lines = self.server.app.logs.dump_since(since)  # type: ignore[attr-defined]
        text = "\n".join(lines) + ("\n" if lines else "")
        if download:
            self._send_text(text, filename="unoq_logs.txt")
        else:
            self._send_text(text)

    def _firmware_update_authorized(self, cfg: FirmwareUpdateConfig) -> tuple[bool, str]:
        expected = cfg.read_token()
        if not expected:
            return False, "firmware update token file is missing or too short"
        provided = self.headers.get("X-UNOQ-Update-Token", "")
        if not provided or not secrets.compare_digest(provided, expected):
            return False, "bad firmware update token"
        return True, ""

    def _ensure_firmware_update_safe(self, cfg: FirmwareUpdateConfig) -> tuple[bool, Optional[dict], str]:
        ok, err = self.server.app.rpc.cmd("STOP")  # type: ignore[attr-defined]
        if not ok:
            return False, None, f"STOP failed: {err}"
        relay_ok, relay_err = self.server.app._precharge_off()  # type: ignore[attr-defined]
        if not relay_ok:
            return False, None, f"PRECHARGE OFF failed: {relay_err}"
        time.sleep(0.2)

        last_err = "no status"
        for _ in range(10):
            ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
            if ok and data is not None:
                state = str(data.get("state", "")).upper()
                state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))
                pwm = _as_int(data, "pwm", 1)
                estop = _as_int(data, "estop", 0)
                bp_fault = _as_int(data, "bp_fault", 0)
                vdc = _status_vdc(data)
                if state != "SAFE" and state_code != STATE_CODES["SAFE"]:
                    return False, data, f"not SAFE: state={data.get('state')}"
                if pwm != 0:
                    return False, data, f"PWM is not off: pwm={pwm}"
                if estop != 0:
                    return False, data, f"ESTOP is active: estop={estop}"
                if bp_fault != 0:
                    return False, data, f"motor-controller fault is active: mc_fault={bp_fault}"
                bad = _status_mc_bad(data)
                if bad != 0:
                    return False, data, f"motor-controller bad-frame counter is non-zero: mc_bad={bad}"
                if not _status_link_live(data):
                    return False, data, "motor-controller link is stale or down"
                if not math.isfinite(vdc):
                    return False, data, "DC bus telemetry is not readable for firmware update"
                if vdc > cfg.max_vdc:
                    return False, data, f"DC bus too high for firmware update: vdc={vdc:.1f} V"
                raw_ok, raw_reason = raw_vbus_window_check(data, 0.0, cfg.max_vdc)
                if not raw_ok:
                    return False, data, f"firmware update blocked: {raw_reason}"
                return True, data, ""
            last_err = err or "no response"
            time.sleep(0.1)
        return False, None, f"status failed: {last_err}"

    def _handle_firmware_update(self, parsed) -> None:
        cfg = self.server.app.firmware_update  # type: ignore[attr-defined]
        if cfg is None or not cfg.enabled:
            self._send_json({"ok": False, "error": "firmware update disabled"}, 403)
            return

        ok, err = self._firmware_update_authorized(cfg)
        if not ok:
            self._send_json({"ok": False, "error": err}, 403)
            return

        query = parse_qs(parsed.query)
        dry_run = query.get("dry_run", ["0"])[0].lower() in ("1", "true", "yes")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json({"ok": False, "error": "empty firmware body"}, 400)
            return
        if length > cfg.max_bytes:
            self._send_json({"ok": False, "error": f"firmware too large: {length} > {cfg.max_bytes}"}, 413)
            return

        safe, status, safe_err = self._ensure_firmware_update_safe(cfg)
        if not safe:
            self.server.app.logs.add(f"FW_UPDATE_REJECT {safe_err}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": safe_err, "status": status}, 409)
            return

        os.makedirs(cfg.upload_dir, exist_ok=True)
        filename = f"unoq_firmware_{int(time.time())}_{threading.get_ident()}.bin"
        path = os.path.join(cfg.upload_dir, filename)
        sha256 = hashlib.sha256()
        remaining = length
        try:
            with open(path, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        raise RuntimeError("short firmware body")
                    f.write(chunk)
                    sha256.update(chunk)
                    remaining -= len(chunk)
        except Exception as exc:
            try:
                os.remove(path)
            except OSError:
                pass
            self._send_json({"ok": False, "error": f"failed to save firmware: {exc}"}, 400)
            return

        digest = sha256.hexdigest()
        self.server.app.logs.add(  # type: ignore[attr-defined]
            f"FW_UPDATE_UPLOAD bytes={length} sha256={digest} dry_run={int(dry_run)}"
        )
        if dry_run:
            self._send_json({"ok": True, "dry_run": True, "bytes": length, "sha256": digest, "path": path})
            return

        if not os.path.exists(cfg.remoteocd_bin):
            self._send_json({"ok": False, "error": f"remoteocd not found: {cfg.remoteocd_bin}"}, 500)
            return
        if not os.path.exists(cfg.remoteocd_cfg):
            self._send_json({"ok": False, "error": f"remoteocd cfg not found: {cfg.remoteocd_cfg}"}, 500)
            return

        cmd = [cfg.remoteocd_bin, "upload", "--verbose", "-f", cfg.remoteocd_cfg, path]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=cfg.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            out = _tail_text(exc.stdout or "")
            self.server.app.logs.add(f"FW_UPDATE_TIMEOUT sha256={digest}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": "remoteocd timeout", "output": out}, 504)
            return
        output = _tail_text(result.stdout or "")
        if result.returncode != 0:
            self.server.app.logs.add(f"FW_UPDATE_FAIL rc={result.returncode} sha256={digest}")  # type: ignore[attr-defined]
            self._send_json(
                {"ok": False, "error": f"remoteocd failed: rc={result.returncode}", "output": output},
                500,
            )
            return
        self.server.app.logs.add(f"FW_UPDATE_WRITE_OK sha256={digest}")  # type: ignore[attr-defined]
        self._send_json(
            {
                "ok": True,
                "dry_run": False,
                "write_only": True,
                "bytes": length,
                "sha256": digest,
                "output": output,
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="UNOQ WiFi HMI server")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument(
        "--router",
        default="/run/arduino-router.sock",
        help="Router endpoint (unix:/path or host:port)",
    )
    parser.add_argument(
        "--serial-baud",
        type=int,
        default=115200,
        help="Baud rate for serial fallback endpoints such as serial:/dev/ttyX",
    )
    parser.add_argument("--log-bytes", type=int, default=2 * 1024 * 1024, help="Max in-memory log bytes")
    parser.add_argument(
        "--log-file",
        default=os.path.join(os.path.dirname(__file__), "logs", "unoq.log"),
        help="Log file path (empty to disable)",
    )
    parser.add_argument("--log-file-bytes", type=int, default=64 * 1024 * 1024, help="Max persistent log file bytes")
    parser.add_argument("--status-log-sec", type=float, default=5.0, help="Status log interval")
    parser.add_argument(
        "--operator-heartbeat-timeout-sec",
        type=float,
        default=float(os.environ.get("UNOQ_OPERATOR_HEARTBEAT_TIMEOUT_SEC", DEFAULT_OPERATOR_HEARTBEAT_TIMEOUT_SEC)),
        help="STOP/ESTOP an active autonomous run when the authenticated browser heartbeat is lost",
    )
    parser.add_argument(
        "--control-token-file",
        default=os.environ.get("UNOQ_HMI_CONTROL_TOKEN_FILE", ""),
        help="Protect control commands and log download with a token stored in this file",
    )
    parser.add_argument(
        "--vbus-calibration-file",
        default=os.environ.get("UNOQ_VBUS_CALIBRATION_FILE", DEFAULT_VBUS_CALIBRATION_FILE),
        help="Persistent two-point Vbus verification record used by the autonomous HV arm gate",
    )
    parser.add_argument(
        "--firmware-update-token-file",
        default=os.environ.get("UNOQ_FIRMWARE_UPDATE_TOKEN_FILE", ""),
        help="Enable firmware update API with a token stored in this file",
    )
    parser.add_argument(
        "--firmware-upload-dir",
        default="/tmp/unoq_firmware_updates",
        help="Directory for received firmware images",
    )
    parser.add_argument("--firmware-update-max-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--firmware-update-timeout-sec", type=float, default=90.0)
    parser.add_argument("--firmware-update-max-vdc", type=float, default=10.0)
    parser.add_argument("--cmd-guard-max-vdc", type=float, default=float(os.environ.get("UNOQ_CMD_GUARD_MAX_VDC", DEFAULT_CMD_GUARD_MAX_VDC)))
    parser.add_argument("--cmd-guard-allow-hv", action="store_true", default=_truthy_env("UNOQ_CMD_GUARD_ALLOW_HV"))
    standalone_group = parser.add_mutually_exclusive_group()
    standalone_group.add_argument(
        "--standalone-hv",
        action="store_true",
        default=_truthy_env("UNOQ_STANDALONE_HV"),
        help="Enable both Wi-Fi arm profiles and start fail-closed in HV mode.",
    )
    standalone_group.add_argument(
        "--standalone-lv",
        action="store_true",
        default=_truthy_env("UNOQ_STANDALONE_LV"),
        help="Enable both Wi-Fi arm profiles and start in HV-disconnected LV test mode.",
    )
    parser.add_argument(
        "--hv-arm-ttl-sec",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_TTL_SEC", DEFAULT_HV_ARM_TTL_SEC)),
    )
    parser.add_argument(
        "--hv-arm-min-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_MIN_VDC", DEFAULT_HV_ARM_MIN_VDC)),
    )
    parser.add_argument(
        "--hv-arm-max-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_HV_ARM_MAX_VDC", DEFAULT_HV_ARM_MAX_VDC)),
    )
    parser.add_argument(
        "--hv-arm-confirm",
        default=os.environ.get("UNOQ_HV_ARM_CONFIRM", DEFAULT_HV_ARM_CONFIRM),
    )
    parser.add_argument(
        "--lv-arm-ttl-sec",
        type=float,
        default=float(os.environ.get("UNOQ_LV_ARM_TTL_SEC", DEFAULT_LV_ARM_TTL_SEC)),
    )
    parser.add_argument(
        "--lv-arm-max-vdc",
        type=float,
        default=float(os.environ.get("UNOQ_LV_ARM_MAX_VDC", DEFAULT_LV_ARM_MAX_VDC)),
    )
    parser.add_argument(
        "--lv-arm-confirm",
        default=os.environ.get("UNOQ_LV_ARM_CONFIRM", DEFAULT_LV_ARM_CONFIRM),
    )
    parser.add_argument(
        "--start-runlimit-sec",
        type=float,
        default=float(os.environ.get("UNOQ_START_RUNLIMIT_SEC", DEFAULT_START_RUNLIMIT_SEC)),
        help="Bound every accepted START command with this automatic run limit.",
    )
    parser.add_argument(
        "--cmd-guard-disable",
        action="store_true",
        default=_truthy_env("UNOQ_CMD_GUARD_DISABLE"),
        help="Bypass only the DC bus voltage command guard; status, link, ESTOP, fault, PWM-active and bad-counter checks stay enforced.",
    )
    parser.add_argument(
        "--bench-gate-url",
        default=os.environ.get("UNOQ_BENCH_GATE_URL", ""),
        help="Live HMI URL used by bench_gate_report.py before accepting START. Defaults to this server on 127.0.0.1.",
    )
    parser.add_argument(
        "--bench-gate-attestation-url",
        default=os.environ.get("UNOQ_BENCH_GATE_ATTESTATION_URL", ""),
        help="Short-lived PC bench-gate attestation URL. START fails closed if it is unavailable, red, stale or expired.",
    )
    parser.add_argument("--remoteocd-bin", default=DEFAULT_REMOTEOCD)
    parser.add_argument("--remoteocd-cfg", default=DEFAULT_REMOTEOCD_CFG)
    args = parser.parse_args()
    if args.router == "/run/arduino-router.sock" and not os.path.exists(args.router):
        if os.path.exists("/var/run/arduino-router.sock"):
            args.router = "/var/run/arduino-router.sock"

    rpc = RpcBridge(args.router, serial_baud=int(args.serial_baud))
    log_path = args.log_file.strip() if isinstance(args.log_file, str) else args.log_file
    if log_path == "":
        log_path = None
    logs = LogStore(max_bytes=args.log_bytes, log_path=log_path, file_max_bytes=args.log_file_bytes)
    firmware_update = None
    token_file = args.firmware_update_token_file.strip()
    if token_file:
        firmware_update = FirmwareUpdateConfig(
            token_file=token_file,
            upload_dir=args.firmware_upload_dir,
            remoteocd_bin=args.remoteocd_bin,
            remoteocd_cfg=args.remoteocd_cfg,
            max_bytes=args.firmware_update_max_bytes,
            timeout_sec=args.firmware_update_timeout_sec,
            max_vdc=args.firmware_update_max_vdc,
        )
    attestation_url = args.bench_gate_attestation_url.strip()
    standalone_enabled = bool(args.standalone_hv or args.standalone_lv)
    control_token_file = args.control_token_file.strip()
    control_access = ControlAccessConfig(control_token_file or None)
    if standalone_enabled and not control_access.read_token():
        parser.error("standalone operation requires --control-token-file containing at least 16 characters")
    initial_profile = ARM_PROFILE_LV if args.standalone_lv else ARM_PROFILE_HV
    hv_cfg = HvArmConfig(
        enabled=standalone_enabled,
        ttl_sec=float(args.hv_arm_ttl_sec),
        min_vdc=float(args.hv_arm_min_vdc),
        max_vdc=float(args.hv_arm_max_vdc),
        confirm=str(args.hv_arm_confirm),
        profile=ARM_PROFILE_HV,
    )
    lv_cfg = HvArmConfig(
        enabled=standalone_enabled,
        ttl_sec=float(args.lv_arm_ttl_sec),
        min_vdc=DEFAULT_LV_ARM_MIN_VDC,
        max_vdc=float(args.lv_arm_max_vdc),
        confirm=str(args.lv_arm_confirm),
        profile=ARM_PROFILE_LV,
    )
    arm_profiles = (
        {ARM_PROFILE_HV: hv_cfg, ARM_PROFILE_LV: lv_cfg}
        if standalone_enabled
        else {}
    )
    hv_runlimit_sec = float(args.start_runlimit_sec)
    lv_runlimit_sec = min(hv_runlimit_sec, DEFAULT_LV_START_RUNLIMIT_SEC)
    profile_runlimits = {
        ARM_PROFILE_HV: hv_runlimit_sec,
        ARM_PROFILE_LV: lv_runlimit_sec,
    }
    selected_cfg = arm_profiles.get(initial_profile, hv_cfg)
    guard_max_vdc = (
        min(float(args.cmd_guard_max_vdc), selected_cfg.max_vdc)
        if initial_profile == ARM_PROFILE_LV
        else float(args.cmd_guard_max_vdc)
    )
    start_runlimit_sec = profile_runlimits[initial_profile]

    command_guard = CommandGuardConfig(
        max_vdc=guard_max_vdc,
        allow_hv=bool(args.cmd_guard_allow_hv or args.standalone_hv),
        disabled=bool(args.cmd_guard_disable),
        bench_gate_url=attestation_url or args.bench_gate_url.strip() or f"http://127.0.0.1:{int(args.port)}",
        bench_gate_runner=attested_bench_gate_runner if attestation_url else None,
        local_bench_gate=standalone_enabled,
    )
    hv_arm = HvArmState(selected_cfg)
    vbus_calibration_path = str(args.vbus_calibration_file).strip()
    vbus_calibration = VbusCalibrationStore(vbus_calibration_path or None)
    app = AppState(
        rpc,
        logs,
        args.status_log_sec,
        firmware_update=firmware_update,
        command_guard=command_guard,
        hv_arm=hv_arm,
        start_runlimit_sec=start_runlimit_sec,
        arm_profiles=arm_profiles,
        profile_runlimits=profile_runlimits,
        guard_max_vdc=float(args.cmd_guard_max_vdc),
        control_access=control_access,
        operator_heartbeat_timeout_sec=float(args.operator_heartbeat_timeout_sec),
        vbus_calibration=vbus_calibration,
    )

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.app = app  # type: ignore[attr-defined]
    server.daemon_threads = True

    print(
        f"UNOQ HMI on http://{args.bind}:{args.port} (router: {args.router}, "
         f"standalone_hv={int(args.standalone_hv)}, standalone_lv={int(args.standalone_lv)}, "
         f"control_auth={int(control_access.enabled)}, softstart=external-autonomous, "
         f"vbus_calibrated={int(vbus_calibration.is_valid())}, runlimit={start_runlimit_sec:.1f}s)"
    )
    app.start_safety_watchdog()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_safety_watchdog()


if __name__ == "__main__":
    main()
