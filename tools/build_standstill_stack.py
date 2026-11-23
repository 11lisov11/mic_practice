"""Build native stack-fix pair using the verified make graph, no Java."""
import build_standstill_timing as build
import prepare_standstill_stack as package
build.p=package
if __name__=='__main__':build.main()
