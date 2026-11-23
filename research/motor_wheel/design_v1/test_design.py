"""Physical checks on the saved simulation and the offline design model."""
import json
import math
from pathlib import Path
import unittest
import numpy as np
import calculate as c

ROOT=Path(__file__).resolve().parent


class DesignChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=c.load_model()
        cls.sweep=json.loads((ROOT/'femm'/'sweep.json').read_text())

    def test_winding_balanced_and_all_layer_sides_used_once(self):
        w=c.make_winding()
        self.assertEqual(sorted(r['return_slot'] for r in w),list(range(1,49)))
        for phase in 'ABC':
            coils=[r for r in w if r['phase']==phase]
            self.assertEqual(len(coils),16)
            self.assertEqual(sum(r['top_direction'] for r in coils),0)
            # Direct discrete winding fundamental matches analytic kw1.
            phasor=sum(r['top_direction']*(np.exp(1j*4*2*np.pi*(r['top_slot']-1)/48)-
                np.exp(1j*4*2*np.pi*(r['return_slot']-1)/48)) for r in coils)
            self.assertAlmostEqual(abs(phasor)/32,c.KW,places=12)

    def test_fea_rotor_loss_and_independent_stress_torque_agree(self):
        self.assertGreaterEqual(len(self.sweep['rows']),6)
        for row in self.sweep['rows']:
            a,b=row['torque_mst_nm'],row['torque_from_rotor_loss_nm']
            self.assertLess(abs(a-b)/abs(b),.025)

    def test_fea_inverse_gamma_fit_is_positive_and_accurate(self):
        fit=self.sweep['fit']
        for k in ['M_effective_h','tau_rotor_s','Rr_effective_20_ohm','L_leak_total_2d_h']:
            self.assertGreater(fit[k],0)
        self.assertLess(fit['relative_complex_fit_rms'],.002)

    def test_complete_phase_power_balance_including_loss_current(self):
        for speed,torque in [(0,5),(10,20),(25,9),(25,2)]:
            pt=c.operating_point(self.model,torque,speed/3.6/.254)
            self.assertIsNotNone(pt)
            self.assertLess(abs(pt['power_balance_residual_W']),1e-8)
            self.assertLess(pt['torque_loss_identity_error_W'],1e-8)

    def test_thermal_links_conserve_energy(self):
        k=c.thermal_matrix(10)
        self.assertTrue(np.all(np.linalg.eigvalsh(k)>0))
        temp=np.array([90.,70.,60.,50.])
        self.assertAlmostEqual(sum(k@temp),k.sum()*temp[3],places=10)

    def test_standstill_consumes_power_without_useful_shaft_work(self):
        pt=c.operating_point(self.model,10,0)
        self.assertEqual(pt['shaft_W'],0)
        self.assertGreater(pt['battery_W_including_15W_aux'],100)
        self.assertEqual(pt['motor_efficiency'],0)

    def test_infeasible_torque_is_rejected(self):
        self.assertIsNone(c.operating_point(self.model,25,0))
        self.assertIsNone(c.operating_point(self.model,24,25/3.6/.254))

    def test_refined_mesh_inductance_and_torque(self):
        finer=json.loads((ROOT/'femm'/'sweep_refined.json').read_text())['rows']
        self.assertEqual(len(finer),2)
        for row in finer:
            original=next(r for r in self.sweep['rows'] if r['frequency_hz']==row['frequency_hz'])
            la=complex(original['L_real_h'],original['L_imag_h'])
            lb=complex(row['L_real_h'],row['L_imag_h'])
            self.assertLess(abs(lb-la)/abs(lb),.03)
            self.assertLess(abs(row['torque_mst_nm']-original['torque_mst_nm'])/abs(row['torque_mst_nm']),.05)


if __name__=='__main__':
    unittest.main()
