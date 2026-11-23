import copy
import json
from pathlib import Path
import struct
import pytest

from load_bench.control import Interlock,readiness
from load_bench.protocol import crc16
from load_bench.red_board import (DEFAULT_IDENTITY,RedBoardError,control_frame,io_configuration_frame,
                                  output_frame,parse_status,select_board)
from load_bench.runner import run_live
from load_bench.simulation import Clock,fixture_config
from load_bench.watchdog import Watchdog,wire_line
from load_bench.stock_permit import StockPermit

ROOT=Path(__file__).resolve().parents[1]
IMAGE='RNRWD_AT32F403RC_20261122'


def test_identity_does_not_fall_back_to_plotter_or_another_red_board():
    own=dict(DEFAULT_IDENTITY,path='verified')
    other=dict(own,serial_number='another-board')
    assert select_board([other,own],DEFAULT_IDENTITY)==own
    for devices in ([other],[],[own,dict(own,path='ambiguous')]):
        with pytest.raises(RedBoardError):select_board(devices,DEFAULT_IDENTITY)
    with pytest.raises(RedBoardError):select_board([own],dict(DEFAULT_IDENTITY,serial_number=None))


@pytest.mark.parametrize('value',[-1,16,True,1.0])
def test_only_four_real_digital_output_bits_are_accepted(value):
    with pytest.raises(ValueError):output_frame(1,value)


def test_exact_nonmotion_hid_frames_and_sequence_wrap():
    frame=output_frame(65535,8)
    assert len(frame)==27 and frame[:6]==bytes.fromhex('020300ffff08')
    assert frame[6:]==bytes(21)
    assert output_frame(0,0)[:6]==bytes.fromhex('020300000000')
    with pytest.raises(ValueError):control_frame(1,4)  # cannot send GcodeSlice
    conf=io_configuration_frame(1)
    assert conf[0:3]==bytes((3,15,0)) and conf[5:16]==bytes(11) and conf[16:18]==bytes((100,5))


def test_observed_stock_report_is_parsed_without_claiming_electrical_measurement():
    raw=bytearray(49);raw[0]=1;raw[1]=1;raw[2]=129
    struct.pack_into('<H',raw,3,65535);struct.pack_into('<i',raw,9,-123)
    raw[41]=9;struct.pack_into('<H',raw,42,5);struct.pack_into('<H',raw,44,65535)
    value=parse_status(bytes(raw))
    assert value['ack_sequence']==65535 and value['live_steps'][0]==-123
    assert value['outputs']==9 and value['inputs']==5 and value['tick']==65535
    assert value['electrical_output_measured'] is False
    for bad in (bytes(raw[:48]),bytes(49),bytes([1,3])+bytes(47)):
        with pytest.raises(RedBoardError):parse_status(bad)


class FirmwareStream:
    def __init__(self,clock,fault=None):self.clock,self.fault,self.queue,self.writes=clock,fault,[],[]
    def reset_input_buffer(self):pass
    def write(self,data):
        self.writes.append(data)
        if data==b'HELLO\n':
            body='ID '+('RNRWD_WRONG_IMAGE' if self.fault=='wrong_id' else IMAGE)
            reply=wire_line(body)
            if self.fault=='crc':reply=reply[:-3]+b'00\n'
            if self.fault=='timeout':reply=b''
            self.queue.append(reply)
        return len(data)
    def readline(self,n):
        self.clock.sleep(.01)
        return self.queue.pop(0) if self.queue else b''


@pytest.mark.parametrize('fault',[None,'wrong_id','crc','timeout'])
def test_red_firmware_identity_is_required_before_any_lease_reply(fault):
    clock=Clock();stream=FirmwareStream(clock,fault);watchdog=Watchdog(stream,clock.now)
    with pytest.raises(RuntimeError,match='identified'):watchdog.renew()
    assert stream.writes==[]
    if fault:
        with pytest.raises(RuntimeError):watchdog.identify(IMAGE)
        assert watchdog.firmware_id is None
        with pytest.raises(RuntimeError):watchdog.renew()
    else:assert watchdog.identify(IMAGE)==IMAGE
    assert stream.writes==[b'HELLO\n']


def test_unattended_stock_and_legacy_bluepill_config_cannot_open_load_ports(monkeypatch,tmp_path):
    cfg=json.loads((ROOT/'load_bench/config.template.json').read_text(encoding='utf-8'))
    good=fixture_config(cfg);good.pop('fixture_only')
    monkeypatch.setattr('load_bench.runner.open_identified_serial',lambda *a:pytest.fail('Must not open ports'))
    assert readiness(good)==[]
    stock=copy.deepcopy(good);stock['experiment_mode']='unattended'
    assert 'stock_requires_supervised_bench' in readiness(stock)
    with pytest.raises(Interlock,match='No ports opened'):run_live(stock,'step',tmp_path/'stock')
    legacy=copy.deepcopy(good);legacy.pop('red_board')
    with pytest.raises(Interlock,match='No ports opened'):run_live(legacy,'step',tmp_path/'legacy')


@pytest.mark.parametrize('fault',[None,'wrong_state','axis_changed','stop_unconfirmed'])
def test_stock_permit_uses_only_confirmed_io_and_never_claims_autonomous_timeout(fault):
    class Board:
        trace=[]
        def __init__(self):self.calls=[]
        def initialize_io(self):self.calls.append('init_io');return dict(live_steps=[0]*4)
        def outputs(self,mask):
            self.calls.append(('outputs',mask))
            return dict(state=2 if fault=='wrong_state' else 1,
                        live_steps=[1,0,0,0] if fault=='axis_changed' else [0]*4,ack_sequence=8)
        def stop_io(self):
            self.calls.append('stop_io');return dict(outputs=1 if fault=='stop_unconfirmed' else 0,state=0)
    b=Board();permit=StockPermit(b)
    assert permit.autonomous_host_loss_shutdown is False
    if fault in ('wrong_state','axis_changed'):
        with pytest.raises(RedBoardError):permit.renew()
        assert b.calls[-1]==('outputs',0)
    else:assert permit.renew()==8
    if fault=='stop_unconfirmed':
        with pytest.raises(RedBoardError):permit.disarm()
    else:assert permit.disarm()['outputs']==0


def test_stock_does_not_require_reflash_or_dump_but_requires_continuous_regen_rating():
    cfg=fixture_config(json.loads((ROOT/'load_bench/config.template.json').read_text()))
    assert cfg['red_board']['backend']=='stock_hid'
    assert readiness(cfg)==[]
    assert not any('mcu' in x or 'firmware' in x or 'dump' in x for x in readiness(cfg))
    cfg['qualification']['watchdog_measured_drop_s']=None
    cfg['qualification']['independent_czero_watchdog_tested']=False
    assert readiness(cfg)==[]
    cfg['qualification']['regen_power_rating_is_continuous']=False
    assert 'regen_power_rating_is_continuous' in readiness(cfg)
    cfg['qualification']['regen_power_rating_is_continuous']=True
    cfg['qualification']['validated_regen_power_w']=5.
    assert 'continuous_regen_power_envelope' in readiness(cfg)
