"""Independent plant, own old/new headers; diagnostics must not change control."""
import inspect,json
import prepare_observer_adc_delivery as p
import model_exact_profile_budget as previous
import test_foc_runtime_fix as common


def main():
    original=common.compile_run
    def compile_run(out,name,code):
        code='static void mic_current_request_observer_capture(){}\n'+code
        return original(out,name,code)
    common.compile_run=compile_run
    try:
        source=inspect.getsource(previous.main)
        scope=dict(previous.__dict__,p=p)
        exec(compile(source,__file__,'exec'),scope);scope['main']()
    finally:common.compile_run=original
    f=p.OUT/'model_verification/model_report.json';r=json.loads(p.read(f))
    r.update(observer_validity_problem_solved=False,
        observer_physical_root_cause_proven=False,
        capture_request_stubbed_only_for_independent_plant=True)
    p.write(f,json.dumps(r,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
