"""Independent physical checks on generated calculation, DXF and CAD results."""
import json,math,unittest
import numpy as np
from geometry import ROOT,belt,geometry,parameters
from drawings import outline
from engine import polygon_area

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def enclosed_area(vertices):
    a=polygon_area([(x,y) for x,y,b in vertices])
    for u,v in zip(vertices,vertices[1:]+vertices[:1]):
        bulge=u[2]
        if bulge:
            angle=4*math.atan(bulge);chord=math.hypot(v[0]-u[0],v[1]-u[1]);radius=chord/(2*math.sin(angle/2))
            a+=radius*radius/2*(angle-math.sin(angle))
    return a

class GeneratedChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=[read(ROOT/name/'results.json') for name in ['D110_L30','D130_L30','D150_L40']]
        cls.points=[p for d in cls.cases for w in d['winding_candidates'] for group in w['points'].values() for p in group.values() if p]
    def test_power_and_slip_energy_balance(self):
        for q in self.points:
            self.assertLess(abs(q['power_balance_error_W']),1e-8)
            self.assertLess(abs(q['rotor_slip_balance_error_W']),1e-8)
            self.assertGreater(q['battery_W_bounds_assumed'][0],q['motor_input_W'])
            self.assertTrue(0<q['power_factor_fundamental']<=1)
    def test_peak_rms_voltage_flux_limits(self):
        for q in self.points:
            self.assertAlmostEqual(q['I_phase_peak_A'],q['I_phase_rms_A']*math.sqrt(2))
            self.assertLessEqual(q['I_phase_rms_A'],9+1e-9)
            self.assertLessEqual(q['current_peak_with_ripple_A_estimate'],15+1e-9)
            self.assertGreaterEqual(q['voltage_margin_peak_V'],1-1e-9)
            self.assertLessEqual(q['Bg_peak_T'],.5+1e-9)
    def test_discrete_three_phase_winding(self):
        z={p:0j for p in 'ABC'};count={p:0 for p in 'ABC'}
        for j in range(48):
            p,sgn=belt(j);count[p]+=1;z[p]+=sgn*(np.exp(1j*2*np.pi*4*j/48)-np.exp(1j*2*np.pi*4*(j+5)/48))
        self.assertLess(abs(sum(z.values())),1e-10)
        for p in z:self.assertEqual(count[p],16);self.assertAlmostEqual(abs(z[p])/32,.9330127018922193)
        for d in self.cases:
            for r in d['winding_candidates']:
                w=r['winding'];g=d['geometry'];x=g['slot_layer_split_radius_mm']-g['slot_bottom_radius_mm'];h=g['slot_shoulder_radius_mm']-g['slot_bottom_radius_mm']
                lower=g['slot_bottom_width_mm']*x+(g['slot_shoulder_width_mm']-g['slot_bottom_width_mm'])/(2*h)*x*x
                self.assertLessEqual(w['bare_slot_fill'],.42)
                self.assertLess(w['turns_per_coil']*w['copper_area_mm2']/min(lower,g['slot_copper_gross_mm2']-lower),.45)
    def test_cad_kernel_placement_and_no_nominal_overlap_all_diameters(self):
        for name in ['D110_L30','D130_L30','D150_L40']:
            a=read(ROOT/name/'CAD/cad_verification.json')
            self.assertEqual(a['component_count'],16);self.assertEqual(a['solid_body_count'],110)
            self.assertEqual(a['kernel_faults_total'],0);self.assertEqual(a['interferences'],[])
            for part in a['parts']:
                self.assertLess(np.max(abs(np.asarray(part['transform'][:9])-np.eye(3).flatten())),1e-10)
                self.assertLess(np.max(abs(np.asarray(part['transform'][9:12]))),1e-10)
    def test_exact_arc_dxf_area_matches_native_cad_volume(self):
        for d in self.cases:
            tag=f'D{d["parameters"]["stator_diameter_mm"]:g}_L{d["geometry"]["active_length_mm"]:g}'
            v=read(ROOT/tag/'CAD/cad_verification.json');g=d['geometry'];L=g['active_length_mm']
            stat=(enclosed_area(outline(g,'stator'))-math.pi*g['stator_bore_radius_mm']**2)*L
            rot=(math.pi*g['rotor_outer_radius_mm']**2-enclosed_area(outline(g,'rotor')))*L
            for label,expected in [('01_STATOR_LAMINATED',stat),('02_ROTOR_LAMINATED',rot)]:
                actual=next(x['volume_mm3'] for x in v['parts'] if label in x['component'])
                self.assertLess(abs(actual/expected-1),1e-6)
    def test_airgap_stays_independent_of_diameter_and_bearings_stay_standard(self):
        for diameter in [110,120,130,150,170]:
            p=parameters(diameter=diameter);g=geometry(p)
            self.assertEqual(g['air_gap_radial_mm'],.4)
            self.assertAlmostEqual(g['stator_outer_radius_mm']*2,diameter)
            self.assertEqual(p['mechanical']['bearing_OD_mm'],47)
    def test_fe_fit_mesh_and_maxwell_energy_torque(self):
        f=read(ROOT/'D150_L40/femm/linear.json');ref=read(ROOT/'D150_L40/femm/refined.json')
        self.assertLess(f['fit']['relative_complex_fit_rms'],.001)
        for q in f['rows']:self.assertLess(abs(q['torque_mst_nm']/q['torque_from_rotor_loss_nm']-1),.02)
        for q in ref['rows']:
            b=next(x for x in f['rows'] if x['frequency_hz']==q['frequency_hz'])
            self.assertLess(abs(complex(q['L_real_h'],q['L_imag_h'])/complex(b['L_real_h'],b['L_imag_h'])-1),.003)
        nl=read(ROOT/'D150_L40/femm/nonlinear.json')['rows'][0]
        self.assertLess(abs(nl['torque_mst_nm']/nl['torque_from_rotor_loss_nm']-1),.02)
        self.assertLess(nl['steel_sample_max_t'],2.0)
    def test_faraday_emf_independent_crosscheck(self):
        d=self.cases[-1];q=d['selected']['points']['flat15']['36.0'];w=d['selected']['winding'];g=d['geometry']
        phi=2*q['Bg_peak_T']*g['stator_outer_radius_mm']/1000*g['active_length_mm']/1000/4
        emf=math.sqrt(2)*math.pi*q['frequency_hz']*w['turns_series_per_phase']*w['winding_factor']*phi
        dq=2*math.pi*q['frequency_hz']*q['Lm_effective_h']*q['Id_peak_A']/math.sqrt(2)
        self.assertLess(abs(emf/dq-1),.1)
    def test_failures_are_not_promoted_to_traction_rating(self):
        self.assertIsNone(self.cases[0]['selected'])
        for d in self.cases[1:]:
            self.assertIsNone(d['selected']['points']['hill5_10']['30.0'])
            self.assertGreater(d['thermal_flat15_36V']['steady_state_C_if_stable']['winding'],90)
            self.assertFalse(d['thermal_flat15_36V']['continuous_rating_established'])

if __name__=='__main__':unittest.main(verbosity=2)
