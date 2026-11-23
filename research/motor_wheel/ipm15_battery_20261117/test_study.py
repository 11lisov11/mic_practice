"""Physical consistency checks for this offline study; no hardware access."""
import json
import math
from pathlib import Path
import unittest
import numpy as np
import calculate as c

ROOT=Path(__file__).resolve().parent


class StudyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'results.json').read_text(encoding='utf-8'))
        cls.points=[p for r in cls.data['records'] for s in r['points'].values() for p in s.values() if p is not None]

    def test_all_points_respect_peak_rms_voltage_and_flux(self):
        for p in self.points:
            self.assertLessEqual(p['I_phase_rms_A'],p['current_limit_rms_A_assumed']+1e-9)
            self.assertAlmostEqual(p['I_phase_peak_A'],math.sqrt(2)*p['I_phase_rms_A'])
            self.assertGreaterEqual(p['voltage_margin_peak_V'],1-1e-9)
            self.assertLessEqual(p['Bg_peak_T'],.5+1e-9)
            self.assertGreater(p['power_factor_fundamental'],0)
            self.assertLessEqual(p['power_factor_fundamental'],1+1e-9)

    def test_fundamental_energy_and_rotor_slip_balance(self):
        for p in self.points:
            self.assertLess(abs(p['motor_power_balance_error_W']),1e-8)
            self.assertLess(abs(p['torque_rotor_loss_identity_error_W']),1e-8)
            self.assertGreater(p['battery_W_with_15W_aux_range'][0],p['motor_input_W'])

    def test_slot_layer_fill_and_discrete_winding(self):
        groups=[('A',1),('C',-1),('B',1),('A',-1),('C',1),('B',-1)]
        sums={ph:0j for ph in 'ABC'}
        count={ph:0 for ph in 'ABC'}
        for j in range(48):
            ph,sgn=groups[((j+1)//2)%6]
            count[ph]+=1
            sums[ph]+=sgn*(np.exp(1j*2*np.pi*4*j/48)-np.exp(1j*2*np.pi*4*(j+5)/48))
        for ph in 'ABC':
            self.assertEqual(count[ph],16)
            self.assertAlmostEqual(abs(sums[ph])/32,c.KW,places=12)
        self.assertLess(abs(sum(sums.values())),1e-10)
        split=c.G['slot_layer_split_radius_mm']-c.G['slot_bottom_radius_mm']
        low=2.5*split+(4.5-2.5)/(2*c.HEIGHT)*split**2
        for w in self.data['winding_candidates']:
            self.assertLessEqual(w['bare_slot_fill'],.42)
            self.assertLess(w['turns_per_coil']*w['conductor_copper_area_mm2']/min(low,c.SLOT-low),.45)

    def test_fea_mesh_and_torque_crosscheck(self):
        base=json.loads((ROOT/'femm'/'linear.json').read_text())
        refine=json.loads((ROOT/'femm'/'refined.json').read_text())
        self.assertLess(base['fit']['relative_complex_fit_rms'],.002)
        for row in base['rows']:
            self.assertLess(abs(row['torque_mst_nm']/row['torque_from_rotor_loss_nm']-1),.02)
        for r in refine['rows']:
            a=next(x for x in base['rows'] if x['frequency_hz']==r['frequency_hz'])
            self.assertLess(abs(complex(r['L_real_h'],r['L_imag_h'])/complex(a['L_real_h'],a['L_imag_h'])-1),.02)

    def test_selected_60v_winding_covers_15kmh_and_drop_sensitivity(self):
        r=next(x for x in self.data['selected_by_bus_and_current'] if x['bus']['name']=='60V_16S' and x['current_limit_rms_A_assumed']==6)
        point=self.data['roads']['flat15']
        for drop in [1.0,1.5,2.1]:
            p=c.operating(self.data['model'],r['winding'],point['torque_Nm'],point['omega_rad_s'],48.,6.,drop)
            self.assertIsNotNone(p)
            self.assertLess(p['phase_current_peak_including_ripple_estimate_A'],9.)

    def test_high_torque_is_rejected_instead_of_clipped(self):
        road=self.data['roads']['hill5_10']
        for r in self.data['selected_by_bus_and_current']:
            self.assertIsNone(c.operating(self.data['model'],r['winding'],road['torque_Nm'],road['omega_rad_s'],r['bus']['full'],r['current_limit_rms_A_assumed']))

    def test_shunt_080_cannot_be_treated_like_040(self):
        a,b=self.data['shunt_cases']
        self.assertAlmostEqual(a['OCP_peak_A_typical_circuit_estimate'],2*b['OCP_peak_A_typical_circuit_estimate'])
        self.assertGreater(9*math.sqrt(2),b['ADC_bipolar_peak_A_ideal'])

    def test_faraday_scale_independent_crosscheck(self):
        r=next(x for x in self.data['selected_by_bus_and_current'] if x['bus']['name']=='60V_16S' and x['current_limit_rms_A_assumed']==6)
        p=r['points']['nominal']['flat15']
        flux=p['Bg_peak_T']*.13*.03/4
        emf_faraday=4.44*p['frequency_hz']*c.KW*r['winding']['turns_series_per_phase']*flux
        ratio=r['winding']['turns_per_coil']/10
        emf_gamma=2*math.pi*p['frequency_hz']*self.data['model']['M_effective_h']*ratio**2*p['Id_peak_A']/math.sqrt(2)
        self.assertLess(abs(emf_faraday/emf_gamma-1),.10)


if __name__=='__main__':unittest.main(verbosity=2)
