import os, sys
# shim — moved to scripts/dream/
_new = os.path.join(os.path.dirname(__file__), "dream", "session_placeholder.py")
os.execv(sys.executable, [sys.executable, _new] + sys.argv[1:])
