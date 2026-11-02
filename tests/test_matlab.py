"""Chay main.m bang GNU Octave va doi chieu voi ban Python; bo qua neu khong co Octave."""
import csv
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from omr_grade import grade_batch, load_answer_key
from omr_layout import question_bubble
from omr_sheet import render_sheet
from synth import add_glare, fill_bubble, fill_sheet, photograph, shift_content

ROOT = Path(__file__).parent.parent
OCTAVE = os.environ.get("OCTAVE") or shutil.which("octave")
pytestmark = pytest.mark.skipif(not OCTAVE, reason="khong co Octave")

ANSWERS = {q: "ABCD"[q % 4] for q in range(1, 41)}


def run_main(tmp_path, args):
    code = f"addpath('{ROOT}'); main({args});"
    return subprocess.run([OCTAVE, "--no-gui", "--quiet", "--eval", code], cwd=tmp_path,
                          capture_output=True, text=True, timeout=600)


def read_scores(tmp_path):
    with open(tmp_path / "scores.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def key_file(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("cau,dap_an\n" + "".join(f"{q},{a}\n" for q, a in ANSWERS.items()))
    return p


def cases():
    good = fill_sheet(render_sheet(), "001234", ANSWERS)
    wrong = fill_sheet(render_sheet(), "567890", {q: "A" for q in range(1, 41)})
    faint = fill_sheet(render_sheet(), "111111", {})
    fill_bubble(faint, question_bubble(5, "B"), darkness=200)
    shadow = good.copy()
    x = question_bubble(1, "C")[0]
    shadow[:, x - 20:x + 20] = (shadow[:, x - 20:x + 20] * .5).astype(shadow.dtype)
    return {
        "thang": photograph(good),
        "nghieng": photograph(good, angle=7, perspective=.05, seed=1),
        "nguoc": photograph(good, angle=180),
        "ngang": photograph(wrong, angle=90),
        "toi": photograph(wrong, brightness=.45, gradient=.4),
        "nhat": photograph(faint),
        "bong": photograph(shadow),
        "mo": photograph(good, blur=31),
        "loa": photograph(add_glare(good)),
        "lech": photograph(shift_content(good, dx=25)),
        "trang": np.full((1000, 800, 3), 220, np.uint8),
    }


def test_matches_python_on_all_cases(tmp_path):
    key = key_file(tmp_path)
    paths = []
    for name, img in cases().items():
        p = tmp_path / f"{name}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths.append(p)
    bad = tmp_path / "hong.jpg"
    bad.write_bytes(b"not an image")
    paths.append(bad)

    cell = "{" + ",".join(f"'{p}'" for p in paths) + "}"
    run = run_main(tmp_path, f"'{key}', {cell}")
    assert run.returncode == 0, run.stdout + run.stderr

    expected = grade_batch([str(p) for p in paths], load_answer_key(str(key)))
    rows = read_scores(tmp_path)
    assert len(rows) == len(expected)
    for row, py in zip(rows, expected):
        assert row["ten_file"] == py.filename
        assert row["trang_thai"] == py.status, (py.filename, row, py.notes)
        if py.score is not None:
            assert row["ma_hoc_sinh"] == py.student_id, py.filename
            assert float(row["diem"]) == py.score, py.filename
        else:
            assert row["diem"] == "", py.filename


def test_default_runs_on_samples(tmp_path):
    run = run_main(tmp_path, "")
    assert run.returncode == 0, run.stdout + run.stderr
    row = read_scores(tmp_path)[0]
    assert (row["ma_hoc_sinh"], row["diem"], row["trang_thai"]) == ("001234", "9.5", "Đã chấm")
    assert "Câu bỏ trống: 7" in row["ghi_chu"]


def test_bad_key_is_reported(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("x,y\n1,A\n")
    run = run_main(tmp_path, f"'{p}', {{'a.jpg'}}")
    assert run.returncode != 0 and "cau,dap_an" in run.stdout + run.stderr


def test_key_from_excel_variants(tmp_path):
    p = tmp_path / "k.csv"
    p.write_bytes("﻿sep=;\r\ncau;dap_an;;\r\n1; a ;;\r\n;;;\r\n".encode())
    img = tmp_path / "a.png"
    cv2.imwrite(str(img), photograph(fill_sheet(render_sheet(), "001234", {1: "A"})))
    run = run_main(tmp_path, f"'{p}', {{'{img}'}}")
    assert run.returncode == 0, run.stdout + run.stderr
    assert read_scores(tmp_path)[0]["diem"] == "10"


def test_duplicate_ids_are_noted(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("cau,dap_an\n1,A\n")
    img = tmp_path / "a.png"
    cv2.imwrite(str(img), photograph(fill_sheet(render_sheet(), "001234", {1: "A"})))
    run = run_main(tmp_path, f"'{p}', {{'{img}','{img}'}}")
    assert run.returncode == 0, run.stdout + run.stderr
    assert all("Trùng mã" in r["ghi_chu"] for r in read_scores(tmp_path))
