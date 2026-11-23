"""Independent unchanged FOC plant regression; diagnostic ADC request is stubbed."""
import prepare_clear_recovery as p
import model_exact_profile_budget as model
import test_foc_runtime_fix as common


def main():
    original=common.compile_run
    def compile_with_capture_stub(out,name,code):
        # The real observer can request an ADC record. This plant harness has
        # no ADC IRQ; the request has no motor-control side effect.
        return original(out,name,'static void mic_current_request_observer_capture(){}\n'+code)
    common.compile_run=compile_with_capture_stub;model.p=p
    try:model.main()
    finally:common.compile_run=original


if __name__=='__main__':main()
