import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_main_serves_ui_and_creates_sheet(tmp_path):
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "--port", "7871"], cwd=tmp_path)
    try:
        for _ in range(120):
            try:
                html = urllib.request.urlopen("http://127.0.0.1:7871", timeout=2).read().decode()
                break
            except OSError:
                assert proc.poll() is None, "main.py da thoat som"
                time.sleep(1)
        else:
            raise AssertionError("server khong khoi dong")
        assert "Chấm bài trắc nghiệm" in html
        assert (ROOT / "templates" / "answer_sheet.pdf").read_bytes()[:4] == b"%PDF"
        assert not (tmp_path / "answer_sheet.pdf").exists()
    finally:
        proc.terminate()
        proc.wait(timeout=20)
