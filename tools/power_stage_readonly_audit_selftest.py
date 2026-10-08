import unittest
import tempfile
from pathlib import Path
from power_stage_readonly_audit import GPIOA, NVIC_ISER0, TIM1, break_register_checks, source_checks


def registers():
    return {TIM1 + 0x44: 0x3000, TIM1 + 0x60: 0x201, TIM1 + 0x0C: 0x80,
            NVIC_ISER0: 1 << 24, GPIOA: 2 << 12, GPIOA + 4: 1 << 6,
            GPIOA + 0x0C: 1 << 12, GPIOA + 0x20: 6 << 24, GPIOA + 0x10: 1 << 6}


class AuditTests(unittest.TestCase):
    def test_correct_break(self):
        self.assertTrue(break_register_checks(registers())["pass"])

    def test_missing_fails_closed(self):
        for address in registers():
            with self.subTest(address=address):
                w = registers()
                del w[address]
                self.assertFalse(break_register_checks(w)["pass"])

    def test_source_rejects_OVP_for_SD(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV'
            (project / 'Src').mkdir(parents=True)
            (project / 'Inc').mkdir()
            header = project / 'Inc/power_stage_parameters.h'
            header.write_text('#define RSHUNT 0.04\n#define AMPLIFICATION_GAIN 2.1\n'
                              '#define V0_V 0.408\n#define T0_C 25\n#define dV_dT 0.025\n')
            irq = project / 'Src/stm32g4xx_mc_it.c'
            irq.write_text('void TIMx_BRK_M1_IRQHandler(void) {\n'
                           ' PWMC_OVP_Handler(&PWM_Handle_M1._Super, TIM1);\n}\n')
            self.assertFalse(source_checks(root)['pass'])
            irq.write_text('void TIMx_BRK_M1_IRQHandler(void) {\n'
                           ' PWMC_DP_Handler(&PWM_Handle_M1._Super);\n}\n')
            self.assertTrue(source_checks(root)['pass'])

    def test_rejects_disabled_inverted_auto_or_active(self):
        for address, value in ((TIM1 + 0x44, 0), (TIM1 + 0x44, 0xF000),
                               (TIM1 + 0x60, 1), (TIM1 + 0x0C, 0),
                               (NVIC_ISER0, 0), (GPIOA, 0), (GPIOA + 4, 0),
                               (GPIOA + 0x0C, 0), (GPIOA + 0x20, 0), (GPIOA + 0x10, 0)):
            with self.subTest(address=address, value=value):
                w = registers()
                w[address] = value
                self.assertFalse(break_register_checks(w)["pass"])


if __name__ == "__main__":
    unittest.main()
