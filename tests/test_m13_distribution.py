"""Distribution: NVIDIA redistributable allowlist, manifest, licenses."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_helpers  # noqa: E402


def make_cuda_folder(root: Path, extra: dict[str, str] | None = None) -> Path:
    (root / "bin").mkdir(parents=True)
    (root / "include").mkdir()
    for name in ("cudart64_12.dll", "nvrtc64_120_0.dll", "nvrtc-builtins64_120.dll"):
        (root / "bin" / name).write_bytes(b"x")
    for name in build_helpers.CUDA_REDISTRIBUTABLE_HEADERS:
        (root / "include" / name).write_text("// header", encoding="ascii")
    (root / "include" / build_helpers.CUDA_MARKER_HEADER).write_text(build_helpers.CUDA_MARKER_TEXT, encoding="ascii")
    for rel, text in (extra or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="ascii")
    return root


def test_attachment_a_files_pass(tmp_path):
    assert build_helpers.check_cuda_folder(make_cuda_folder(tmp_path / "cuda")) == []


def test_other_nvidia_headers_and_libraries_are_refused(tmp_path):
    folder = make_cuda_folder(tmp_path / "cuda", {"include/vector_types.h": "x", "include/cooperative_groups/details/async.h": "x",
                                                  "bin/cublas64_12.dll": "x"})
    assert sorted(build_helpers.check_cuda_folder(folder)) == ["bin/cublas64_12.dll", "include/cooperative_groups/details/async.h",
                                                               "include/vector_types.h"]


def test_a_real_cuda_runtime_header_is_refused(tmp_path):
    folder = make_cuda_folder(tmp_path / "cuda")
    (folder / "include" / "cuda_runtime.h").write_text("#include <host_config.h>\n", encoding="ascii")
    assert build_helpers.check_cuda_folder(folder) == ["include/cuda_runtime.h"]


def test_allowlist_matches_the_eula_list():
    # CUDA 12.0 EULA, Attachment A: runtime and NVRTC DLLs (versioned variants) and these headers only.
    assert set(build_helpers.CUDA_REDISTRIBUTABLE_HEADERS) <= {"nvrtc.h", "cuda_fp16.h", "cuda_fp16.hpp", "cuda_occupancy.h", "cufile.h"}
    for name in ("cudart64_12.dll", "nvrtc64_120_0.dll", "nvrtc-builtins64_120.dll"):
        assert build_helpers.CUDA_REDISTRIBUTABLE_DLLS.match(name)
    for name in ("cublas64_12.dll", "nvJitLink_120_0.dll", "cudnn64_9.dll", "nvcuda.dll"):
        assert not build_helpers.CUDA_REDISTRIBUTABLE_DLLS.match(name)


# ---------------------------------------------------------------- manifest and signatures
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

import make_manifest  # noqa: E402
from app import issig  # noqa: E402

REAL_RELEASE = Path(os.environ.get("PQSSE_RELEASE_DIR", r"C:\Users\Kushal\PQ-SSE-Desktop-release\restyle\0.1.0"))


def fake_release(folder: Path, gpu: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    names = ["PQ-SSE-Desktop-Setup-9.9.9.exe", "PQ-SSE-Desktop-9.9.9-portable-standard.zip", "PQ-SSE-Web-Setup.exe"]
    if gpu:
        names += ["PQ-SSE-Desktop-Setup-9.9.9-GPU.exe", "PQ-SSE-Desktop-9.9.9-portable-gpu.zip"]
    for index, name in enumerate(names):
        (folder / name).write_bytes(os.urandom(1000 + index))
    return folder


def check_entry(folder: Path, item: dict) -> None:
    path = folder / item["file"]
    assert item["size"] == path.stat().st_size
    assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert item["url"].startswith("https://github.com/kushalgiduturi/pq-sse-desktop/releases/download/v") and item["url"].endswith(item["file"])


def test_manifest_matches_the_files_and_gpu_is_unavailable_without_its_file(tmp_path):
    folder = fake_release(tmp_path / "rel")
    m = make_manifest.build_manifest(folder, "9.9.9", "2026-11-20")
    assert m["schema"] == 1 and m["version"] == "9.9.9" and m["min_os"] == "10.0.17763"
    for item in (m["channels"]["standard"], m["portable"]["standard"], m["web_setup"]):
        check_entry(folder, item)
    assert m["channels"]["gpu"] == {"available": False, "min_driver": "528.33"}
    assert m["portable"]["gpu"] == {"available": False}
    assert "url" not in json.dumps(m["channels"]["gpu"])


def test_manifest_lists_gpu_when_present(tmp_path):
    folder = fake_release(tmp_path / "rel", gpu=True)
    m = make_manifest.build_manifest(folder, "9.9.9", "2026-11-20")
    check_entry(folder, m["channels"]["gpu"])
    check_entry(folder, m["portable"]["gpu"])


@pytest.mark.skipif(not REAL_RELEASE.is_dir(), reason="no local release build")
def test_manifest_from_the_real_release_build(tmp_path):
    m = make_manifest.build_manifest(REAL_RELEASE, "0.1.0", "2026-11-17")
    for item in (m["channels"]["standard"], m["portable"]["standard"]):
        check_entry(REAL_RELEASE, item)
    sums = {line.split()[1]: line.split()[0] for line in (REAL_RELEASE / "SHA256SUMS.txt").read_text().splitlines() if line.strip()}
    assert sums[m["channels"]["standard"]["file"]] == m["channels"]["standard"]["sha256"]


ISSIGTOOL = make_manifest.find_issigtool()


@pytest.fixture()
def signing_key(tmp_path, monkeypatch):
    if not ISSIGTOOL:
        pytest.skip("ISSigTool (Inno Setup 6.5+) is not installed")
    key = tmp_path / "throwaway.key"
    subprocess.run([ISSIGTOOL, f"--key-file={key}", "generate-private-key"], check=True, capture_output=True)
    pub = tmp_path / "pub.txt"
    subprocess.run([ISSIGTOOL, f"--key-file={key}", "export-public-key", str(pub)], check=True, capture_output=True)
    monkeypatch.setenv("ISSIGTOOL_KEY_FILE", str(key))
    return issig.parse_public_key(pub.read_text())


def test_signed_manifest_verifies_and_tampering_is_refused(tmp_path, signing_key):
    folder = fake_release(tmp_path / "rel")
    assert make_manifest.main([str(folder), "--version", "9.9.9", "--date", "2026-11-20", "--sign"]) == 0
    manifest = (folder / "latest.json").read_bytes()
    sig = (folder / "latest.json.issig").read_text()
    assert issig.verify(sig, manifest, [signing_key], expected_name="latest.json") == signing_key.key_id
    setup = folder / "PQ-SSE-Desktop-Setup-9.9.9.exe"
    issig.verify((folder / (setup.name + ".issig")).read_text(), setup.read_bytes(), [signing_key], expected_name=setup.name)
    with pytest.raises(issig.SignatureError, match="mismatch"):
        issig.verify(sig, manifest.replace(b"9.9.9", b"9.9.8"), [signing_key])
    with pytest.raises(issig.SignatureError, match="not 'other.json'"):
        issig.verify(sig, manifest, [signing_key], expected_name="other.json")
    forged = sig.replace("file-size ", "file-size 1") if "file-size 0" not in sig else sig
    with pytest.raises(issig.SignatureError):
        issig.verify(forged, manifest, [signing_key])
    other = issig.PublicKey("0" * 64, "1" * 64, "2" * 64)
    with pytest.raises(issig.SignatureError, match="does not trust"):
        issig.verify(sig, manifest, [other])
    sums = (folder / "SHA256SUMS.txt").read_text()
    assert hashlib.sha256(manifest).hexdigest() + "  latest.json" in sums


def test_add_gpu_to_a_published_manifest(tmp_path):
    folder = fake_release(tmp_path / "rel", gpu=True)
    manifest = make_manifest.build_manifest(fake_release(tmp_path / "published"), "9.9.9", "2026-11-20")
    assert manifest["channels"]["gpu"]["available"] is False
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    updated = make_manifest.add_gpu(path, folder)
    check_entry(folder, updated["channels"]["gpu"])
    check_entry(folder, updated["portable"]["gpu"])
    assert updated["channels"]["gpu"]["min_driver"] == "528.33"
    assert updated["channels"]["standard"] == manifest["channels"]["standard"]   # the released files are untouched
    assert json.loads(path.read_text()) == updated


def _winget_fields(path: Path) -> dict[str, str]:
    """The top-level and installer "key: value" lines of a winget manifest (enough for these checks)."""
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " in line and not line.lstrip().startswith("#"):
            key, value = line.strip().lstrip("- ").split(": ", 1)
            fields[key] = value.strip("'")
    return fields


def test_winget_manifests_come_from_latest_json(tmp_path):
    import make_winget
    sha = "ab" * 32
    url = "https://github.com/o/r/releases/download/v9.8.7/PQ-SSE-Desktop-Setup-9.8.7.exe"
    folder = make_winget.write(tmp_path, {"version": "9.8.7", "min_os": "10.0.17763",
                                          "channels": {"standard": {"url": url, "sha256": sha}}})
    assert folder == tmp_path / "manifests" / "p" / "PQSSE" / "PQSSEDesktop" / "9.8.7"
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["PQSSE.PQSSEDesktop.installer.yaml", "PQSSE.PQSSEDesktop.locale.en-US.yaml", "PQSSE.PQSSEDesktop.yaml"]
    installer = _winget_fields(folder / "PQSSE.PQSSEDesktop.installer.yaml")
    assert installer["InstallerUrl"] == url and installer["InstallerSha256"] == sha.upper()
    assert installer["PackageVersion"] == "9.8.7" and installer["Scope"] == "user" and installer["InstallerType"] == "inno"
    assert installer["ElevationRequirement"] == "elevationProhibited"
    locale = _winget_fields(folder / "PQSSE.PQSSEDesktop.locale.en-US.yaml")
    assert locale["ReleaseNotesUrl"].endswith("/releases/tag/v9.8.7")
    assert "not audited" in locale["ShortDescription"]
    for name in names:
        text = (folder / name).read_text(encoding="utf-8")
        assert f"ManifestVersion: {make_winget.SCHEMA}" in text and f"winget-manifest." in text
        assert "—" not in text


def test_winget_product_code_is_the_real_apps_appid_not_the_test_twins():
    import make_winget
    iss = (ROOT / "installer" / "pqsse.iss").read_text(encoding="utf-8")
    code = make_winget.product_code()
    assert code.endswith("_is1") and code[:-4] in iss
    twin = iss.split("#ifdef TestInstall", 1)[1].split("#else", 1)[0]
    assert code[:-4] not in twin
