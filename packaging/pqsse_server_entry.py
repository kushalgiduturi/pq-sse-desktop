"""Entry point of the frozen pqsse-server.exe (PyInstaller needs a script without relative imports)."""
import sys

from pqsse.server.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
