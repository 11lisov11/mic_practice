"""Stock RNR ECO MOTION 2.0 HID: identity-locked I/O, never axis motion.

Independent implementation from documented interoperability facts:
https://github.com/manuprendlair/GRBL2MACH/blob/e172263aa72f9ffa5520c919ca0c482e10a094c8/docs/PROTOCOL.md
Only digital I/O initialization, stop and opcode 03 (outputs) are implemented.
No position reset, STEP/DIR, spindle PWM or firmware command is available here.
A returned mask is controller feedback, NOT an electrical measurement.
Stock outputs must not be mistaken for a hardware watchdog.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import os
import struct
import time


VID, PID = 0xA720, 0xF803
DEFAULT_IDENTITY = dict(vid=VID, pid=PID, serial_number="816FAD79CE5",
                        product="RNR ECO MOTION 2.0", version=0x0300)


class RedBoardError(RuntimeError):
    pass


def output_frame(sequence, mask):
    if type(sequence) is not int or not 0 <= sequence <= 65535:
        raise ValueError("16-bit sequence required")
    if type(mask) is not int or not 0 <= mask <= 15:
        raise ValueError("Only OUT1..OUT4 exist")
    return struct.pack("<BBBHB", 2, 3, 0, sequence, mask) + bytes(21)


def control_frame(sequence,opcode):
    if opcode not in (1,2,7):raise ValueError("No motion opcode is permitted")
    frame=bytearray(output_frame(sequence,0));frame[1]=opcode
    return bytes(frame)


def io_configuration_frame(sequence):
    # No CNC inputs are used by this output-only backend. The T3D's independent
    # hardwired stop is separate. This does not configure a machine for motion.
    frame=bytearray(output_frame(sequence,0));frame[0]=3;frame[1]=15
    frame[16]=100;frame[17]=5
    return bytes(frame)


def parse_status(raw):
    if len(raw) != 49 or raw[0] != 1:
        raise RedBoardError("Wrong RNR input report length or ID")
    if raw[1] not in (0, 1, 2, 4, 5, 6, 7):
        raise RedBoardError("Unknown RNR controller state")
    return dict(state=raw[1], flags=raw[2], ack_sequence=struct.unpack_from("<H", raw, 3)[0],
        outputs=raw[41] & 15, outputs_raw=raw[41], inputs=struct.unpack_from("<H",raw,42)[0],
        tick=struct.unpack_from("<H",raw,44)[0],
        live_steps=[struct.unpack_from("<i",raw,9+8*i)[0] for i in range(4)],
        raw_hex=raw.hex(), electrical_output_measured=False)


def _api():
    if os.name != "nt":
        raise RedBoardError("The stock HID backend currently requires Windows")
    from types import SimpleNamespace
    a=SimpleNamespace()
    a.k=ctypes.WinDLL("kernel32",use_last_error=True)
    a.s=ctypes.WinDLL("setupapi",use_last_error=True)
    a.h=ctypes.WinDLL("hid",use_last_error=True)
    class Guid(ctypes.Structure):
        _fields_=[("a",w.DWORD),("b",w.WORD),("c",w.WORD),("d",ctypes.c_ubyte*8)]
    class Interface(ctypes.Structure):
        _fields_=[("cbSize",w.DWORD),("guid",Guid),("flags",w.DWORD),("reserved",ctypes.c_size_t)]
    class Attr(ctypes.Structure):
        _fields_=[("Size",w.ULONG),("vid",w.USHORT),("pid",w.USHORT),("version",w.USHORT)]
    class Caps(ctypes.Structure):
        _fields_=[("usage",w.USHORT),("page",w.USHORT),("input",w.USHORT),
                  ("output",w.USHORT),("feature",w.USHORT),("reserved",w.USHORT*17),
                  ("counts",w.USHORT*10)]
    class Overlapped(ctypes.Structure):
        _fields_=[("Internal",ctypes.c_size_t),("InternalHigh",ctypes.c_size_t),
                  ("Offset",w.DWORD),("OffsetHigh",w.DWORD),("hEvent",w.HANDLE)]
    a.Guid,a.Interface,a.Attr,a.Caps,a.Overlapped=Guid,Interface,Attr,Caps,Overlapped
    def fn(dll,name,restype,argtypes):
        f=getattr(dll,name);f.restype=restype;f.argtypes=argtypes
    P=ctypes.c_void_p
    fn(a.h,"HidD_GetHidGuid",None,[ctypes.POINTER(Guid)])
    fn(a.h,"HidD_GetAttributes",ctypes.c_ubyte,[w.HANDLE,ctypes.POINTER(Attr)])
    for name in ("HidD_GetProductString","HidD_GetManufacturerString","HidD_GetSerialNumberString"):
        fn(a.h,name,ctypes.c_ubyte,[w.HANDLE,P,w.ULONG])
    fn(a.h,"HidD_GetPreparsedData",ctypes.c_ubyte,[w.HANDLE,ctypes.POINTER(P)])
    fn(a.h,"HidD_FreePreparsedData",ctypes.c_ubyte,[P])
    fn(a.h,"HidP_GetCaps",w.LONG,[P,ctypes.POINTER(Caps)])
    fn(a.h,"HidD_FlushQueue",ctypes.c_ubyte,[w.HANDLE])
    fn(a.s,"SetupDiGetClassDevsW",w.HANDLE,[P,w.LPCWSTR,w.HWND,w.DWORD])
    fn(a.s,"SetupDiEnumDeviceInterfaces",w.BOOL,[w.HANDLE,P,P,w.DWORD,P])
    fn(a.s,"SetupDiGetDeviceInterfaceDetailW",w.BOOL,[w.HANDLE,P,P,w.DWORD,P,P])
    fn(a.s,"SetupDiDestroyDeviceInfoList",w.BOOL,[w.HANDLE])
    fn(a.k,"CreateFileW",w.HANDLE,[w.LPCWSTR,w.DWORD,w.DWORD,P,w.DWORD,w.DWORD,w.HANDLE])
    fn(a.k,"CloseHandle",w.BOOL,[w.HANDLE])
    fn(a.k,"CreateEventW",w.HANDLE,[P,w.BOOL,w.BOOL,w.LPCWSTR])
    fn(a.k,"WaitForSingleObject",w.DWORD,[w.HANDLE,w.DWORD])
    for name in ("ReadFile","WriteFile"):
        fn(a.k,name,w.BOOL,[w.HANDLE,P,w.DWORD,ctypes.POINTER(w.DWORD),P])
    fn(a.k,"GetOverlappedResult",w.BOOL,[w.HANDLE,P,ctypes.POINTER(w.DWORD),w.BOOL])
    fn(a.k,"CancelIoEx",w.BOOL,[w.HANDLE,P])
    a.invalid=ctypes.c_void_p(-1).value
    return a


def enumerate_boards():
    """Metadata query of matching HID interfaces only. No output report sent."""
    a=_api();guid=a.Guid();a.h.HidD_GetHidGuid(ctypes.byref(guid))
    device_set=a.s.SetupDiGetClassDevsW(ctypes.byref(guid),None,None,0x12)
    if device_set==a.invalid:raise ctypes.WinError(ctypes.get_last_error())
    boards=[]
    try:
        i=0
        while True:
            iface=a.Interface();iface.cbSize=ctypes.sizeof(iface)
            if not a.s.SetupDiEnumDeviceInterfaces(device_set,None,ctypes.byref(guid),i,ctypes.byref(iface)):
                error=ctypes.get_last_error()
                if error==259:break
                raise ctypes.WinError(error)
            i+=1;size=w.DWORD()
            a.s.SetupDiGetDeviceInterfaceDetailW(device_set,ctypes.byref(iface),None,0,ctypes.byref(size),None)
            if not 8 <= size.value <= 65536:raise RedBoardError("Unexpected HID path size")
            detail=ctypes.create_string_buffer(size.value)
            ctypes.cast(detail,ctypes.POINTER(w.DWORD))[0]=8 if ctypes.sizeof(ctypes.c_void_p)==8 else 6
            if not a.s.SetupDiGetDeviceInterfaceDetailW(device_set,ctypes.byref(iface),detail,size,ctypes.byref(size),None):
                raise ctypes.WinError(ctypes.get_last_error())
            path=ctypes.wstring_at(ctypes.addressof(detail)+4)
            if "vid_a720&pid_f803" not in path.casefold():continue
            handle=a.k.CreateFileW(path,0,3,None,3,0,None)
            if handle==a.invalid:continue
            try:
                attr=a.Attr();attr.Size=ctypes.sizeof(attr)
                if not a.h.HidD_GetAttributes(handle,ctypes.byref(attr)):continue
                item=dict(path=path,vid=attr.vid,pid=attr.pid,version=attr.version)
                for key,fn in (("product","HidD_GetProductString"),("manufacturer","HidD_GetManufacturerString"),
                               ("serial_number","HidD_GetSerialNumberString")):
                    value=ctypes.create_unicode_buffer(256)
                    item[key]=value.value if getattr(a.h,fn)(handle,value,ctypes.sizeof(value)) else None
                boards.append(item)
            finally:a.k.CloseHandle(handle)
    finally:a.s.SetupDiDestroyDeviceInfoList(device_set)
    return boards


def select_board(devices,identity):
    if identity.get("vid")!=VID or identity.get("pid")!=PID or not identity.get("serial_number"):
        raise RedBoardError("Explicit RNR VID/PID and USB serial are required")
    selected=[x for x in devices if all(x.get(k)==v for k,v in identity.items() if v is not None)]
    if len(selected)!=1:
        raise RedBoardError(f"Expected exactly one matching red board; found {len(selected)}")
    return selected[0]


class RedBoard:
    def __init__(self,identity=DEFAULT_IDENTITY,*,write_enabled=False):
        self.identity=select_board(enumerate_boards(),identity)
        self.a=_api();self.handle=None;self.trace=[];self.last_status=None
        self.write_enabled=write_enabled
        access=0x80000000 | (0x40000000 if write_enabled else 0)
        # Exclusive access: Drufel/Mach3 and our load program cannot drive it together.
        self.handle=self.a.k.CreateFileW(self.identity["path"],access,0,None,3,0x40000000,None)
        if self.handle==self.a.invalid:
            self.handle=None
            raise RedBoardError("Cannot claim red board exclusively; close DrufelCNC/Mach3 first: "+str(ctypes.WinError(ctypes.get_last_error())))
        try:
            pp=ctypes.c_void_p();caps=self.a.Caps()
            if not self.a.h.HidD_GetPreparsedData(self.handle,ctypes.byref(pp)):
                raise RedBoardError("Cannot read HID capabilities")
            try:
                if self.a.h.HidP_GetCaps(pp,ctypes.byref(caps))!=0x110000:
                    raise RedBoardError("Cannot decode HID capabilities")
            finally:self.a.h.HidD_FreePreparsedData(pp)
            if (caps.input,caps.output)!=(49,27):
                raise RedBoardError(f"Unqualified HID revision: reports {caps.input}/{caps.output}")
            self.capabilities=dict(input_bytes=caps.input,output_bytes=caps.output,
                                   usage=caps.usage,usage_page=caps.page)
        except BaseException:self.close();raise

    def close(self):
        if self.handle is not None:
            self.a.k.CloseHandle(self.handle);self.handle=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def _io(self,writing,data_or_size,timeout):
        if self.handle is None:raise RedBoardError("HID handle closed")
        a=self.a;event=a.k.CreateEventW(None,True,False,None)
        if not event:raise ctypes.WinError(ctypes.get_last_error())
        ol=a.Overlapped();ol.hEvent=event;count=w.DWORD()
        data=ctypes.create_string_buffer(data_or_size) if writing else ctypes.create_string_buffer(data_or_size)
        size=len(data_or_size) if writing else data_or_size
        start=time.monotonic()
        try:
            done=(a.k.WriteFile if writing else a.k.ReadFile)(self.handle,data,size,ctypes.byref(count),ctypes.byref(ol))
            if not done:
                error=ctypes.get_last_error()
                if error!=997:raise ctypes.WinError(error)
                wait=a.k.WaitForSingleObject(event,max(1,int(timeout*1000)))
                if wait!=0:
                    a.k.CancelIoEx(self.handle,ctypes.byref(ol))
                    # The kernel must release the buffer before Python frees it.
                    a.k.GetOverlappedResult(self.handle,ctypes.byref(ol),ctypes.byref(count),True)
                    raise TimeoutError("RNR HID write timeout" if writing else "RNR HID read timeout")
                if not a.k.GetOverlappedResult(self.handle,ctypes.byref(ol),ctypes.byref(count),False):
                    raise ctypes.WinError(ctypes.get_last_error())
            if count.value!=size:raise RedBoardError("Partial HID transfer")
            raw=data.raw[:size]
            self.trace.append(dict(direction="out" if writing else "in",start=start,end=time.monotonic(),raw_hex=raw.hex()))
            return raw
        finally:a.k.CloseHandle(event)

    def status(self,timeout=.2):
        result=parse_status(self._io(False,49,timeout))
        result["received_monotonic"]=time.monotonic();self.last_status=result
        return result

    def _command(self,builder,timeout=.22,mask=None,state=None,reset_sequence=False):
        if not self.write_enabled:raise RedBoardError("This session is read-only")
        if self.last_status is None:self.status()
        if self.last_status["state"] not in (0,1):
            raise RedBoardError("Controller has an active motion run; not touching outputs")
        if not self.a.h.HidD_FlushQueue(self.handle):raise RedBoardError("Cannot discard old HID status")
        seq=(self.last_status["ack_sequence"]+1)&65535
        deadline=time.monotonic()+timeout
        self._io(True,builder(seq),min(.1,timeout))
        while time.monotonic()<deadline:
            value=self.status(max(.001,deadline-time.monotonic()))
            if value["state"] not in (0,1):raise RedBoardError("Unexpected controller motion state")
            expected_ack=65535 if reset_sequence else seq
            if value["ack_sequence"]==expected_ack and (mask is None or value["outputs"]==mask) and (state is None or value["state"]==state):return value
        raise RedBoardError("Command not confirmed in a fresh status report")

    def outputs(self,mask,timeout=.22):
        return self._command(lambda seq:output_frame(seq,mask),timeout,mask=mask)

    def initialize_io(self):
        initial=self.status()
        if initial["state"] not in (0,1) or initial["outputs"]:
            raise RedBoardError("I/O initialization requires stopped board with all outputs off")
        self._command(io_configuration_frame)
        # This physical stock revision resets its sequence counter to FFFF on
        # PreReset, rather than acknowledging that frame's sequence number.
        self._command(lambda seq:control_frame(seq,7),state=0,mask=0,reset_sequence=True)
        self._command(lambda seq:control_frame(seq,2),state=1)
        self._command(io_configuration_frame,state=1)
        return self.outputs(0)

    def stop_io(self):
        self.outputs(0)
        return self._command(lambda seq:control_frame(seq,1),state=0,mask=0)


def passive_probe(identity=DEFAULT_IDENTITY,seconds=1.):
    with RedBoard(identity) as board:
        started=time.monotonic();samples=[]
        while time.monotonic()-started<seconds:samples.append(board.status())
        return dict(identity=board.identity,capabilities=board.capabilities,samples=samples,
                    raw_hid_trace=board.trace,write_reports_sent=0,firmware_changed=False,
                    electrical_output_measured=False)
