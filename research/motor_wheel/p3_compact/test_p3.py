"""Independent physical/artifact checks, no drive or printer communication."""
import collections,csv,json,math,struct,unittest,zipfile,xml.etree.ElementTree as ET
import numpy as np
from calculate import ROOT

class P3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=ROOT/'P3_L30_M145';cls.r=json.loads((cls.case/'results.json').read_text());cls.a=json.loads((ROOT/'REVIEW/review_data.json').read_text());cls.c=json.loads((cls.case/'CAD/cad_verification.json').read_text())
    def test_electrical_and_slip_power_balance(self):
        for points in self.r['points'].values():
            for q in points.values():
                if q is None:continue
                self.assertLess(abs(q['energy_error_W']),1e-8);self.assertLess(abs(q['slip_energy_error_W']),1e-8)
                self.assertAlmostEqual(q['I_peak_A'],q['I_rms_A']*math.sqrt(2));self.assertLessEqual(q['I_peak_with_ripple_A'],15)
                self.assertAlmostEqual(q['shaft_W']+q['motor_loss_W'],q['motor_input_W']);self.assertGreaterEqual(q['voltage_margin_V'],0)
    def test_winding_from_exported_coil_schedule(self):
        with (self.case/'winding_24_coils.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),24);sums=collections.Counter();phasors={p:0j for p in 'ABC'}
        for row in rows:
            j=int(row['slot_top'])-1;k=int(row['slot_return'])-1;sign=int(row['sign_top']);self.assertEqual((k-j)%24,5);self.assertEqual(int(row['turns']),8);sums[row['phase']]+=1
            phasors[row['phase']]+=sign*(np.exp(1j*j*math.pi/6)-np.exp(1j*k*math.pi/6))
        self.assertEqual(list(sums.values()),[8,8,8]);self.assertLess(abs(sum(phasors.values())),1e-10)
        self.assertLess(max(map(abs,phasors.values()))-min(map(abs,phasors.values())),1e-10);self.assertLess(self.r['winding']['bare_slot_fill'],.4)
    def test_hot_nonlinear_point_within_phase_peak_limit(self):
        n=self.a['adjusted_hot_nonlinear'];q=self.a['adjusted_hot_launch'];self.assertGreater(q['accel_m_s2'],.3);self.assertLess(n['Bg_fund_peak_t'],.8)
        self.assertLess(abs(n['torque_mst_Nm']/n['torque_from_cage_Nm']-1),.005)
        ripple30=q['I_phase_peak_plus_ripple_30V_A']-q['I_phase_peak_A'];self.assertLess(q['I_phase_peak_A']+ripple30*42/30,15)
        self.assertLess(self.a['initial_hot_accel_m_s2'],.3);self.assertFalse(self.a['initial_start_target03_confirmed'])
    def test_gear_clearances_and_torque_scope(self):
        self.assertEqual(self.a['mesh']['max_overlap_area_mm2'],0);self.assertEqual(self.a['mesh']['carrier_angles_checked'],91)
        g=self.r['gear'];self.assertGreater(9*g['module_mm']-(g['needle_outer_r_mm']+1),.5)
        self.assertGreater(self.r['gear_load_screen']['planet_neighbour_tip_clearance_mm'],.6)
        self.assertLess(self.r['gear_load_screen']['planet_root_MPa_Lewis_screen'],10);self.assertGreater(self.r['gear_12Nm_overload_screen']['planet_root_MPa_Lewis_screen'],10)
    def test_cad_kernel_key_position_and_reaction_detail(self):
        c=self.c;self.assertEqual(c['component_count'],60);self.assertEqual(c['solid_body_count'],114);self.assertEqual(c['kernel_faults_total'],0);self.assertFalse(c['interferences'])
        key=next(p for p in c['parts'] if '28_REACTION_KEY' in p['component']);self.assertTrue(np.allclose(key['transform'][9:12],[0,0,0],atol=1e-12));self.assertAlmostEqual(key['volume_mm3'],300,places=5)
        axle=next(p for p in c['parts'] if '11_MAIN_AXLE' in p['component']);self.assertLess(axle['volume_mm3'],30799)
    def test_thermal_and_donor_limitations_are_explicit(self):
        self.assertLess(self.r['thermal_sensitivity_Rsa']['1.5']['winding'],120);self.assertGreater(self.r['thermal_sensitivity_Rsa']['2.5']['winding'],120)
        self.assertGreater(self.a['gear_thermal_sensitivity_C']['4'],65);self.assertIsNone(self.r['points']['30']['flat25']);self.assertIsNone(self.r['points']['36']['hill5_10'])
        self.assertFalse(self.a['packaging']['fit_verified']);self.assertFalse(self.a['drive_hardware_modified']);self.assertEqual(self.a['bench_peak_trip_A_unchanged'],1.35)
    def test_print_meshes_and_generic3mf_plates(self):
        for x in self.a['print_kit']:
            self.assertEqual(x['nonmanifold_edges'],0);self.assertLessEqual(max(x['dimensions_mm']),256)
        ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
        for name in ['01_FIRST_COIL_AND_FIT','02_GEAR_COLD_TRIAL']:
            with zipfile.ZipFile(ROOT/'PRINT_KIT_COLD'/(name+'.3mf')) as z:
                self.assertIsNone(z.testzip());self.assertNotIn('GCODE',' '.join(z.namelist()).upper());model=ET.fromstring(z.read('3D/3dmodel.model'))
            self.assertEqual(model.attrib['unit'],'millimeter');objects={}
            for obj in model.findall('m:resources/m:object',ns):objects[obj.attrib['id']]=np.array([[float(v.attrib[k]) for k in ['x','y','z']] for v in obj.findall('m:mesh/m:vertices/m:vertex',ns)])
            for item in model.findall('m:build/m:item',ns):
                tr=list(map(float,item.attrib['transform'].split()));pts=objects[item.attrib['objectid']]+tr[9:12]
                self.assertGreaterEqual(float(pts[:,:2].min()),0);self.assertLessEqual(float(pts[:,:2].max()),256);self.assertAlmostEqual(float(pts[:,2].min()),0,places=4)
    def test_comparable_mass_and_width_reduction(self):
        m=self.a['mass'];self.assertAlmostEqual(m['comparable_no_tire_kg'],sum(m['scope_masses_kg'].values()));self.assertLess(m['comparable_no_tire_kg'],4.4)
        self.assertEqual(self.a['packaging']['main_width_mm'],94.5);self.assertGreater(self.a['packaging']['with_external_cooling_span_mm'],self.a['packaging']['main_width_mm'])

if __name__=='__main__':unittest.main(verbosity=2)
