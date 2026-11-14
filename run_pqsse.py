"""Entry script for the packaged executable (and a shortcut for `python run_pqsse.py`).

With the argument --cloud the same executable runs the cloud server process.
"""
import multiprocessing
import sys

from app.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
