import os
import subprocess
import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).parent.parent
NOTEBOOK = ROOT / "main.ipynb"


def test_notebook_is_self_contained():
    nb = nbformat.read(NOTEBOOK, 4)
    src = "\n".join(c.source for c in nb.cells if c.cell_type == "code")
    assert "from omr_" not in src and "import omr_" not in src and "from synth" not in src
    assert "pip install -q gradio==6.31.0" in nb.cells[1].source


def test_notebook_executes_clean(tmp_path):
    env = dict(os.environ, OMR_SKIP_LAUNCH="1")
    subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute",
                    "--output-dir", str(tmp_path), str(NOTEBOOK)],
                   check=True, env=env, timeout=600)
    out = nbformat.read(next(tmp_path.glob("*.ipynb")), 4)
    text = str([c.get("outputs") for c in out.cells if c.cell_type == "code"])
    assert "Đã chấm" in text and "Traceback" not in text
