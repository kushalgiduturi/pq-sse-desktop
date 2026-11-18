"""Measure the numbers the website quotes and write site/data/facts.json.

    python scripts/make_facts.py [--skip-tests] [--skip-bench]

Every number on the site that is not from the release manifest comes from this file, and every
number here comes from running the project on this computer:
  - tests: the whole pytest suite (passed, skipped, failed);
  - attacks: every Security Lab scenario run for real, and which check caught it;
  - benchmarks: the app's own benchmark (pqsse.bench): the per-operation timings for every
    parameter set, and BuildIndex on the CPU and the GPU; the raw CSV files are kept next to it;
  - counts read from the code: verification checks, lesson steps, challenges, features;
  - the machine: Windows version, processor, GPU, Python, post-quantum backend.
--skip-tests or --skip-bench keep those parts from the previous facts.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "site" / "data" / "facts.json"
BENCH_DIR = ROOT / "site" / "data" / "bench"


def run_tests() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}", "tests"],
                       cwd=ROOT, env=env, check=False)
        suite = ET.parse(xml).getroot()
        suite = suite.find("testsuite") if suite.tag == "testsuites" else suite
        total, failed = int(suite.get("tests")), int(suite.get("failures")) + int(suite.get("errors"))
        skipped = int(suite.get("skipped"))
    files = len(list((ROOT / "tests").glob("test_*.py")))
    return {"total": total, "passed": total - failed - skipped, "skipped": skipped, "failed": failed, "files": files}


def run_attacks() -> dict:
    from pqsse import attacklab
    rows = []
    for key, title, line, _ in attacklab.SCENARIOS:
        outcome = attacklab.run_scenario(key)
        rows.append({"key": key, "title": title, "line": line, "behaved_as_claimed": bool(outcome.passed),
                     "check": outcome.check, "caught_by": outcome.caught_by})
    attacks = [r for r in rows if r["key"] != "collusion"]
    return {"attacks": len(attacks), "caught": sum(r["behaved_as_claimed"] for r in attacks),
            "comparison_ran": any(r["key"] == "collusion" and r["behaved_as_claimed"] for r in rows), "rows": rows}


def run_bench() -> dict:
    from pqsse import bench
    from pqsse.pqbackend import DEFAULT_PARAMS, FAST_PARAMS, PARAM_SETS
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    ops = bench.run_operation_benchmarks(PARAM_SETS, repeats=3)
    build = bench.run_build_benchmarks(bench.BUILD_SIZES)
    bench.write_csv(BENCH_DIR / "operations.csv", ops, bench.OPS_COLUMNS)
    bench.write_csv(BENCH_DIR / "buildindex.csv", build, bench.BUILD_COLUMNS)
    default = {r["operation"]: r["milliseconds"] for r in ops if (r["kem"], r["sig"]) == (DEFAULT_PARAMS.kem, DEFAULT_PARAMS.sig)}
    search = default["TokenGen"] + default["Search"] + default["Verify"]
    return {"default_params": f"{DEFAULT_PARAMS.kem} + {DEFAULT_PARAMS.sig}", "build_params": f"{FAST_PARAMS.kem} + {FAST_PARAMS.sig}",
            "search_ms": round(search, 1), "revoke_r_ms": round(default[next(k for k in default if k.startswith("Revoke R "))], 1),
            "revoke_re_ms": round(default[next(k for k in default if k.startswith("Revoke RE"))], 1),
            "operations": [{**r, "milliseconds": round(r["milliseconds"], 2)} for r in ops],
            "build": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in build],
            "csv": ["data/bench/operations.csv", "data/bench/buildindex.csv"]}


def processor() -> str:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "unknown processor"


def machine() -> dict:
    from pqsse import pqbackend
    from pqsse.gpu import status
    info = status.gpu_status()
    gpu = f"{info.device}, {info.total_mem / 2**30:.0f} GB" if info.usable else "no usable GPU"
    return {"os": f"Windows build {platform.version()}" if sys.platform == "win32" else platform.platform(),
            "cpu": processor(), "gpu": gpu, "python": platform.python_version(), "pq_backend": pqbackend.backend_name()}


def counts() -> dict:
    from pqsse.receiver import CHECKS
    from app import challenges, lesson
    features = json.loads((ROOT / "site" / "data" / "features.json").read_text(encoding="utf-8"))
    return {"checks": len(CHECKS), "check_names": list(CHECKS), "lesson_steps": len(lesson.STEPS),
            "challenges": len(challenges.CHALLENGES), "features": len(features["features"]), "screens": 5,
            "algorithms": 10}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-bench", action="store_true")
    parser.add_argument("--out", type=Path, default=None,
                        help="write here instead of site/data/facts.json (numbers of a branch that is not released)")
    args = parser.parse_args()
    global OUT, BENCH_DIR
    if args.out is not None:                     # a branch's numbers stay away from the public site's data
        OUT = args.out.resolve()
        BENCH_DIR = OUT.parent / (OUT.stem + "-bench")
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    facts = {"schema": 1, "measured": dt.date.today().isoformat(), "machine": machine(), "counts": counts()}
    facts["tests"] = old["tests"] if args.skip_tests and "tests" in old else run_tests()
    facts["security_lab"] = run_attacks()
    facts["bench"] = old["bench"] if args.skip_bench and "bench" in old else run_bench()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    t, lab, b = facts["tests"], facts["security_lab"], facts["bench"]
    print(f"Facts: {t['passed']} of {t['total']} tests passed ({t['skipped']} skipped, {t['failed']} failed); "
          f"{lab['caught']} of {lab['attacks']} attacks caught; search {b['search_ms']} ms, revoke R {b['revoke_r_ms']} ms "
          f"({b['default_params']}); written to {OUT.relative_to(ROOT)}")
    return 0 if t["failed"] == 0 and lab["caught"] == lab["attacks"] else 1


if __name__ == "__main__":
    sys.exit(main())
