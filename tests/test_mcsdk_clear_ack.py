"""Exercise the checked-in MCSDK functions without connecting a board."""

import shutil
import subprocess
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / 'firmware/nucleo/Src'


def read_function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def test_off_preserves_pending_fault_ack(tmp_path):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('g++ is required for the MCSDK host regression')
    interface = (SOURCE / 'mc_interface.c').read_text(encoding='utf-8')
    tasks = (SOURCE / 'mc_tasks.c').read_text(encoding='utf-8')
    start = tasks.index('case FAULT_OVER:')
    scheduler = tasks[start:tasks.index('case FAULT_NOW:', start)]
    program = r'''
#include <cassert>
#include <initializer_list>
#define __weak
using MCI_State_t = int;
enum { IDLE, ICLWAIT, RUN, FAULT_NOW, FAULT_OVER, MCI_NO_COMMAND,
       MCI_STOP, MCI_ACK_FAULTS, MC_NO_FAULTS=0 };
struct MCI_Handle_t { int State, CurrentFaults, PastFaults, DirectCommand; };
MCI_Handle_t Mci[1];
constexpr int M1 = 0;
int MCI_GetSTMState(MCI_Handle_t *p) { return p->State; }
int MCI_GetCurrentFaults(MCI_Handle_t *p) { return p->CurrentFaults; }
int MCI_GetOccurredFaults(MCI_Handle_t *p) { return p->PastFaults; }
'''
    program += read_function(interface, '__weak bool MCI_StopMotor(')
    program += read_function(interface, '__weak bool MCI_FaultAcknowledged(')
    program += '\nvoid run_scheduler() { switch (Mci[M1].State) {\n' + scheduler
    program += r'''default: break; } }
int main() {
    auto &motor = Mci[M1];
    for (int off_frames : {0, 1, 8, 64}) {
        for (int mask : {4, 1024, 1028}) {
            motor = {FAULT_OVER, 0, mask, MCI_NO_COMMAND};
            assert(MCI_FaultAcknowledged(&motor));
            assert(motor.PastFaults == 0);
            for (int i = 0; i < off_frames; ++i) {
                assert(!MCI_StopMotor(&motor));
                assert(motor.DirectCommand == MCI_ACK_FAULTS);
            }
            run_scheduler();
            assert(motor.State == IDLE && motor.DirectCommand == MCI_NO_COMMAND);
        }
    }
    motor = {FAULT_OVER, 1024, 1024, MCI_NO_COMMAND};
    assert(!MCI_FaultAcknowledged(&motor));
    assert(!MCI_StopMotor(&motor) && motor.CurrentFaults == 1024);
    motor = {FAULT_NOW, 0, 0, MCI_NO_COMMAND};
    assert(!MCI_StopMotor(&motor));
    motor = {RUN, 0, 0, MCI_NO_COMMAND};
    assert(MCI_StopMotor(&motor) && motor.DirectCommand == MCI_STOP);
}
'''
    unit = tmp_path / 'test.cpp'
    executable = tmp_path / 'test.exe'
    unit.write_text(program, encoding='utf-8')
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    str(unit), '-o', str(executable)], check=True, timeout=30)
    subprocess.run([str(executable)], check=True, timeout=10)
