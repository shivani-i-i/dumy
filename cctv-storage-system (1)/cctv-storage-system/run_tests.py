"""Fallback runner when pytest is not installed:  python run_tests.py"""
import importlib, pkgutil, sys, traceback
import backend.tests as tests
fails = n = 0
for m in pkgutil.iter_modules(tests.__path__):
    mod = importlib.import_module(f"backend.tests.{m.name}")
    for name in dir(mod):
        if name.startswith("test_"):
            n += 1
            try:
                getattr(mod, name)()
            except Exception:
                fails += 1
                print(f"FAIL {m.name}.{name}"); traceback.print_exc()
print(f"{n - fails}/{n} passed")
sys.exit(1 if fails else 0)
