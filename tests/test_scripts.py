import hashlib
import importlib.util
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_module(name: str, rel_path: str):
    path = (REPO_ROOT / rel_path).resolve()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load module %r from %s" % (name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class ScriptTests(unittest.TestCase):
    def test_seed_billing_pool_cli_creates_txt_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "profiles.csv"
            output_dir = Path(tmp_dir) / "pool"
            input_path.write_text(
                "\n".join(
                    [
                        "Jane,Doe,123 Main St,Austin,TX,78701,5551231234,jane@example.com",
                        "Only,Five,Fields,Will,Skip",
                        "John,Smith,45 Oak Rd,Dallas,TX,75001",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "seed_billing_pool.py"),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            txt_files = list(output_dir.glob("*.txt"))
            self.assertGreaterEqual(len(txt_files), 1)
            lines = txt_files[0].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(
                lines[0],
                "Jane|Doe|123 Main St|Austin|TX|78701|5551231234|jane@example.com",
            )
            self.assertEqual(lines[1], "John|Smith|45 Oak Rd|Dallas|TX|75001||")

    def test_download_maxmind_cli_without_license_key_exits_1(self):
        env = os.environ.copy()
        env.pop("MAXMIND_LICENSE_KEY", None)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "download_maxmind.py")],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("MAXMIND_LICENSE_KEY", proc.stderr)

    def test_download_maxmind_main_downloads_and_saves_mmdb(self):
        module = _load_module("download_maxmind", "scripts/download_maxmind.py")
        mmdb_payload = b"mmdb-test-bytes"

        archive_stream = io.BytesIO()
        with tarfile.open(fileobj=archive_stream, mode="w:gz") as archive:
            info = tarfile.TarInfo(name="GeoLite2-City_20260414/GeoLite2-City.mmdb")
            info.size = len(mmdb_payload)
            archive.addfile(info, io.BytesIO(mmdb_payload))
        archive_bytes = archive_stream.getvalue()
        checksum = hashlib.sha256(archive_bytes).hexdigest()
        checksum_bytes = ("%s  GeoLite2-City.tar.gz\n" % checksum).encode("utf-8")

        def _mock_urlopen(url, **kwargs):
            value = getattr(url, "full_url", url)
            if str(value).endswith("suffix=tar.gz.sha256"):
                return _FakeResponse(checksum_bytes)
            if str(value).endswith("suffix=tar.gz"):
                return _FakeResponse(archive_bytes)
            raise AssertionError("Unexpected URL: %s" % value)

        with tempfile.TemporaryDirectory() as tmp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)
                with patch.dict(os.environ, {"MAXMIND_LICENSE_KEY": "test_key"}, clear=False):
                    with patch.object(module.urllib.request, "urlopen", side_effect=_mock_urlopen):
                        exit_code = module.main()
                self.assertEqual(exit_code, 0)
                mmdb_path = Path(tmp_dir) / "data" / "GeoLite2-City.mmdb"
                self.assertTrue(mmdb_path.exists())
                self.assertEqual(mmdb_path.read_bytes(), mmdb_payload)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
