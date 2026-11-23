"""Offline 2-D AC identification of the proposed hub ACIM; no hardware access.

FEMM 4.2 + pyFEMM 0.1.3. FEMM phasor currents are PEAK amplitudes.
Open rotor slots avoid falsely linearizing a saturated closed-slot bridge.
Copper effective conductivity includes the fundamental end-ring correction.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
PRIVATE = Path(os.environ['LOCALAPPDATA']) / 'mic_motor_wheel_tools' / 'python'
sys.path.insert(0, str(PRIVATE))
import femm as f
import numpy as np
from scipy.optimize import least_squares

P = 4
Z = 48
ZR = 50
TURNS = 6
PITCH = 5
L_MM = 40
BAR_W = 4.8
BAR_D = 10
RING_A_MM2 = 120
RING_R_MM = 95
RHO_20 = 0.01724  # ohm mm2/m
SIGMA_CU = 1 / RHO_20
BAR_R_OHM = RHO_20 * .04 / (BAR_W * BAR_D)
RING_SEG_OHM = RHO_20 * (2 * math.pi * RING_R_MM / 1000 / ZR) / RING_A_MM2
END_FACTOR = 1 + RING_SEG_OHM / (2 * BAR_R_OHM * math.sin(math.pi * P / ZR)**2)


def xy(r, theta):
    return (r * math.cos(theta), r * math.sin(theta))


def slot_points(theta, levels):
    def point(r, t, on_circle=False):
        radial = math.sqrt(r*r-t*t) if on_circle else r
        return (radial*math.cos(theta)-t*math.sin(theta),
                radial*math.sin(theta)+t*math.cos(theta))
    a = [point(r, -w/2, i == 0) for i, (r, w) in enumerate(levels)]
    b = [point(r, w/2, i == 0) for i, (r, w) in reversed(list(enumerate(levels)))]
    return a + b


def poly(points):
    for x, y in points:
        f.mi_addnode(x, y)
    # Mouth is closed by the circular material boundary; no chord/sliver.
    for a, b in zip(points, points[1:]):
        f.mi_addsegment(*a, *b)


def circle(r, angles=None, group=0, boundary=''):
    if angles is None:
        angles = [0, math.pi/2, math.pi, 3*math.pi/2]
    angles = sorted(a % (2*math.pi) for a in angles)
    for a in angles:
        f.mi_addnode(*xy(r, a))
    for a, b in zip(angles, angles[1:] + [angles[0] + 2*math.pi]):
        f.mi_addarc(*xy(r, a), *xy(r, b), math.degrees(b-a), 1)
        f.mi_selectarcsegment(*xy(r, (a+b)/2))
        f.mi_setarcsegmentprop(1, boundary, 0, group)
        f.mi_clearselected()


def label(r, theta, material, mesh, group=0, circuit='<None>', turns=0):
    x, y = xy(r, theta)
    f.mi_addblocklabel(x, y)
    f.mi_selectlabel(x, y)
    f.mi_setblockprop(material, 0, mesh, circuit, 0, group, turns)
    f.mi_clearselected()


def belt(j):
    # Sector centered at A+, B-, C+, A-, B+, C-.
    # Exact winding factor is computed from this discrete winding, not assumed.
    # Integer arithmetic resolves slots on 30-degree belt boundaries uniformly.
    sector = ((j+1)//2) % 6
    return [('A', 1), ('C', -1), ('B', 1), ('A', -1), ('C', 1), ('B', -1)][sector]


def winding():
    rows = []
    for j in range(Z):
        phase, sign = belt(j)
        rows.append({'coil': j+1, 'phase': phase, 'sign_top': sign,
                     'slot_top': j+1, 'slot_return': (j+PITCH) % Z+1,
                     'turns': TURNS})
    return rows


def build(path, mesh_scale=1.0, mu=2000, nonlinear=False):
    f.newdocument(0)
    f.mi_probdef(1, 'millimeters', 'planar', 1e-6, L_MM, 20, 0)
    f.mi_addmaterial('Air', 1, 1, 0, 0, 0, 0, 0, 1)
    # Real unidentified steel: linear screening, not a verified B-H curve.
    f.mi_addmaterial('Steel_linear_assumed', mu, mu, 0, 0, 0, .5, 0, .95)
    steel = 'Steel_linear_assumed'
    if nonlinear:
        steel = 'M-19 Steel'
        f.mi_getmaterial(steel)
        f.mi_modifymaterial(steel, 5, 0)  # exclude unidentified core eddy loss
        f.mi_modifymaterial(steel, 6, .5)
        f.mi_modifymaterial(steel, 8, .95)
    f.mi_addmaterial('Winding', 1, 1, 0, 0, 0)
    f.mi_addmaterial('Cage_effective_Cu', 1, 1, 0, 0, SIGMA_CU / END_FACTOR)
    f.mi_addboundprop('A0', 0, 0, 0, 0, 0, 0, 0, 0, 0)
    for phase, angle in [('A', 0), ('B', -2*math.pi/3), ('C', 2*math.pi/3)]:
        f.mi_addcircprop(phase, complex(math.cos(angle), math.sin(angle)), 1)
    circle(45)
    circle(105)
    circle(120, boundary='A0')
    stat_angles, rot_angles = [], []
    levels = [(85, 2.5), (83, 2.5), (82, 6.8), (71, 5.15), (60, 3.5)]
    for j in range(Z):
        theta = 2*math.pi*j/Z
        points = slot_points(theta, levels)
        poly(points)
        # Divide the two winding layers at r=71 mm.
        f.mi_addsegment(*points[3], *points[-4])
        phase, sign = belt(j)
        label(77, theta, 'Winding', 1*mesh_scale, 1, phase, sign*TURNS)
        phase_b, sign_b = belt((j-PITCH) % Z)
        label(65, theta, 'Winding', 1*mesh_scale, 1, phase_b, -sign_b*TURNS)
        d = math.asin(2.5/170)
        stat_angles.extend([theta-d, theta+d])
    circle(85, stat_angles)
    # Radial gap 0.4 mm; bar starts at 86.2, open 1-mm-wide neck to gap.
    for j in range(ZR):
        theta = 2*math.pi*(j+.31)/ZR
        points = slot_points(theta, [(85.4, 1), (86.2, 1), (86.2, BAR_W), (96.2, BAR_W)])
        poly(points)
        # Boundary between insulating slot neck and copper bar.
        f.mi_addsegment(*points[2], *points[-3])
        label(90, theta, 'Cage_effective_Cu', .8*mesh_scale, 2)
        label(85.8, theta, 'Air', .25*mesh_scale, 3)
        d = math.asin(1/(2*85.4))
        rot_angles.extend([theta-d, theta+d])
    circle(85.4, rot_angles)
    label(30, .1, 'Air', 5)
    label(52, .1, steel, 1.8*mesh_scale, 4)
    label(85.2, .1, 'Air', .16*mesh_scale, 3)
    label(102, .1, steel, 1.5*mesh_scale, 2)
    label(114, .1, 'Air', 4)
    f.mi_saveas(str(path))


def evaluate(freq, amp_peak=1, ac_solver=0):
    f.mi_probdef(freq, 'millimeters', 'planar', 1e-6, L_MM, 20, ac_solver)
    for phase, angle in [('A', 0), ('B', -2*math.pi/3), ('C', 2*math.pi/3)]:
        f.mi_modifycircprop(phase, 1, amp_peak * complex(math.cos(angle), math.sin(angle)))
    started = time.time()
    f.mi_analyze(1)
    f.mi_loadsolution()
    c = f.mo_getcircuitproperties('A')
    f.mo_groupselectblock(2)
    loss = f.mo_blockintegral(4).real
    torque = f.mo_blockintegral(22).real
    f.mo_clearblock()
    sample = []
    for theta in np.linspace(0, 2*math.pi, 720, endpoint=False):
        b = f.mo_getb(*xy(85.2, float(theta)))
        br = b[0]*math.cos(theta)+b[1]*math.sin(theta)
        sample.append(complex(br))
    vals = np.asarray(sample)
    # Complex amplitude of positive/negative spatial fundamental.
    th = np.arange(720)*2*math.pi/720
    bg = max(abs(np.mean(vals*np.exp(1j*P*th))), abs(np.mean(vals*np.exp(-1j*P*th))))
    steel_b = []
    for radius, n in [(58, 240), (102, 240), (78, 48)]:
        for j in range(n):
            angle = 2*math.pi*(j+.5)/n
            b = f.mo_getb(*xy(radius, angle))
            steel_b.append(math.sqrt(abs(b[0])**2+abs(b[1])**2))
    result = {'frequency_hz': freq, 'current_peak_a': amp_peak,
              'L_real_h': (c[2]/c[0]).real, 'L_imag_h': (c[2]/c[0]).imag,
              'effective_cage_loss_w': loss, 'torque_mst_nm': torque,
              'torque_from_rotor_loss_nm': loss*P/(2*math.pi*freq),
              'Bg_fund_peak_t': bg, 'steel_sample_max_t': max(steel_b),
              'nodes': f.mo_numnodes(), 'elements': f.mo_numelements(),
              'elapsed_s': time.time()-started}
    f.mo_close()
    return result


def fit(rows):
    ws = 2*np.pi*np.array([r['frequency_hz'] for r in rows])
    target = np.array([complex(r['L_real_h'], r['L_imag_h']) for r in rows])
    def residual(x):
        ll, lm, tau = np.exp(x)
        err = ll + lm/(1+1j*ws*tau) - target
        return np.r_[err.real, err.imag] / max(abs(target))
    sol = least_squares(residual, np.log([.0003, .01, .1]), max_nfev=3000)
    ll, lm, tau = np.exp(sol.x)
    return {'L_leak_total_2d_h': ll, 'M_effective_h': lm,
            'tau_rotor_s': tau, 'Rr_effective_20_ohm': lm/tau,
            'relative_complex_fit_rms': float(np.sqrt(np.mean(residual(sol.x)**2))),
            'fit_success': bool(sol.success)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refine', action='store_true')
    parser.add_argument('--nonlinear', action='store_true')
    args = parser.parse_args()
    out = ROOT / 'femm'
    out.mkdir(exist_ok=True)
    f.openfemm(1)
    try:
        model_file = out/('hub_nonlinear.fem' if args.nonlinear else ('hub_refined.fem' if args.refine else 'hub_48s_8p.fem'))
        build(model_file, .72 if args.refine else 1, nonlinear=args.nonlinear)
        rows = []
        for freq in ([3] if args.nonlinear else ([1, 4] if args.refine else [.5, 1, 2, 4, 8, 16])):
            row = evaluate(freq, 35 if args.nonlinear else 1, 1 if args.nonlinear else 0)
            rows.append(row)
            print(json.dumps(row), flush=True)
            (out/('nonlinear.json' if args.nonlinear else ('sweep_refined.json' if args.refine else 'sweep.json'))).write_text(
                json.dumps({'end_factor': END_FACTOR, 'rows': rows, 'fit': fit(rows) if len(rows)>=4 else None}, indent=2), encoding='utf-8')
        f.mi_saveas(str(model_file))
    finally:
        f.closefemm()


if __name__ == '__main__':
    main()
