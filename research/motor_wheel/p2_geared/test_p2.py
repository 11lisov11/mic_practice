"""Physical consistency and artifact checks; no hardware access."""
import json,math,unittest
from pathlib import Path
import numpy as np
from model import ROOT,belt
from optimise import road

class P2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=json.loads((ROOT/'P2_HUB/results.json').read_text());cls.a=json.loads((ROOT/'REVIEW/review_data.json').read_text())
    def test_electrical_energy_and_peak_not_battery_current(self):
        for v,points in self.r['points'].items():
            for name,limits in points.items():
                for limit,q in limits.items():
                    if q is None:continue
                    self.assertLess(abs(q['energy_error_W']),1e-8);self.assertLess(abs(q['slip_energy_error_W']),1e-8)
                    self.assertAlmostEqual(q['I_peak_A'],q['I_rms_A']*math.sqrt(2))
                    self.assertAlmostEqual(q['battery_A']*float(v),q['battery_W_with_10W_aux'])
                    if float(limit)<=10.5:self.assertLessEqual(q['I_peak_with_ripple_A'],15+1e-8)
                    self.assertGreaterEqual(q['voltage_margin_V'],0)
    def test_winding_balance_and_wire_fit(self):
        winding=self.r['winding'];self.assertLessEqual(winding['bare_slot_fill'],.4)
        # Net series phase EMF is balanced, including the return side.
        z=24;p=2;pitch=5;phasors={ph:0j for ph in 'ABC'}
        for j in range(z):
            ph,sign=belt(j);phasors[ph]+=sign*(np.exp(1j*2*math.pi*p*j/z)-np.exp(1j*2*math.pi*p*(j+pitch)/z))
        vals=list(phasors.values());self.assertLess(abs(sum(vals)),1e-10)
        self.assertLess(max(map(abs,vals))-min(map(abs,vals)),1e-10)
        self.assertEqual(winding['turns_series_per_phase'],56)
    def test_gear_phases_at_all_positions(self):
        for g in self.a['mesh']:
            self.assertTrue(g['gears_valid']);self.assertEqual(g['carrier_angles_checked'],91);self.assertLess(g['max_overlap_area_mm2'],1e-8)
        for s in self.a['gear_load_screens'].values():
            self.assertGreater(s['planet_neighbour_tip_clearance_mm'],.5)
            self.assertLess(s['planet_root_MPa_Lewis_screen'],10)
    def test_native_cad_kernel_and_interference(self):
        for name in ['P2_HUB','P2_HUB_SMALL']:
            c=json.loads((ROOT/name/'CAD/cad_verification.json').read_text());self.assertEqual(c['kernel_faults_total'],0);self.assertFalse(c['interferences']);self.assertEqual(c['component_count'],59)
    def test_field_convergence_and_hot_launch_derating(self):
        for q in self.a['mesh_refinement']:
            self.assertLess(q['L_complex_relative_change'],.005);self.assertLess(q['torque_relative_change'],.005)
        n=self.a['nonlinear_hot_launch'];self.assertLess(abs(n['torque_mst_Nm']/n['torque_from_cage_Nm']-1),.005)
        # The target0.4 acceleration must not be promoted after saturation.
        self.assertGreater(self.a['nonlinear_hot_launch_acceleration_m_s2'],.3)
        self.assertLess(self.a['nonlinear_hot_launch_acceleration_m_s2'],.4)
    def test_duty_limits_are_exposed(self):
        self.assertIsNotNone(self.r['points']['30']['flat20']['9'])
        self.assertIsNone(self.r['points']['30']['flat25']['10.5'])
        self.assertIsNone(self.r['points']['36']['hill5_10']['10.5'])
        t=self.r['thermal']['flat20_30V'];self.assertTrue(t['passes_winding120C_screen']);self.assertFalse(t['continuous_rating_measured'])
        self.assertGreater(t['steady_C']['stator'],55)
        self.assertGreater(self.a['gear_thermal']['Tgear_for_Rgear_ambient_C']['4'],65)
    def test_mass_boundaries_and_fit_unknown(self):
        for m in self.a['mass'].values():
            self.assertFalse(m['donor_fit_verified']);self.assertLess(m['comparable_no_tyre_kg'],5.5)
            self.assertAlmostEqual(m['comparable_no_tyre_kg'],m['insert_kg']+m['assumed_donor_metal_kg']+.07)
        self.assertFalse(self.a['drive_hardware_modified']);self.assertEqual(self.a['bench_peak_trip_A_unchanged'],1.35)

if __name__=='__main__':unittest.main(verbosity=2)
