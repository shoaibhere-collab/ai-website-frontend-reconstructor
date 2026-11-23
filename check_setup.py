# check_setup.py
# A tiny "hello" program that proves your environment is ready.
# It does not touch any website yet - it only reports versions.

import sys
from importlib.metadata import version

print("Python version :", sys.version.split()[0])
print("Playwright     :", version("playwright"))

if sys.version_info < (3, 9):
    print("\n[!] Python is too old. Please install Python 3.9 or newer.")
else:
    print("\nSetup looks good. You are ready for Step 2.")
