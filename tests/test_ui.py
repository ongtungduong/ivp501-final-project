from pathlib import Path

import cv2
import gradio as gr

from omr_sheet import render_sheet
from omr_ui import build_ui, run_grading, show_sheet
from synth import fill_sheet, photograph


def make_key_and_photo(tmp_path):
    key = tmp_path / "k.csv"
    key.write_text("cau,dap_an\n1,A\n2,B\n")
    img = tmp_path / "bai.png"
    cv2.imwrite(str(img), photograph(fill_sheet(render_sheet(), "001234", {1: "A", 2: "C"})))
    return str(key), str(img)


def test_missing_inputs_give_message():
    assert run_grading(None, ["a.jpg"])[3]
    assert run_grading("k.csv", [])[3]


def test_bad_key_gives_message_not_crash(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("x,y\n")
    rows, csv_path, results, msg = run_grading(str(p), ["a.jpg"])
    assert rows == [] and csv_path is None and msg


def test_grades_uploaded_files(tmp_path):
    key, img = make_key_and_photo(tmp_path)
    rows, csv_path, results, msg = run_grading(key, [img])
    assert rows[0][:4] == ["bai.png", "001234", 1, 5.0]
    assert Path(csv_path).exists() and "1" in msg


def test_show_sheet_returns_rgb_image_and_steps(tmp_path):
    key, img = make_key_and_photo(tmp_path)
    results = run_grading(key, [img])[2]
    annotated, gallery = show_sheet(0, results)
    assert annotated.shape[2] == 3
    assert "nan_phoi_canh" in {cap for _, cap in gallery}


def test_show_sheet_unknown_name_is_empty():
    assert show_sheet(5, []) == (None, [])


def test_build_ui_returns_blocks():
    assert isinstance(build_ui(), gr.Blocks)


def test_duplicate_filenames_show_the_selected_sheet(tmp_path):
    key, img = make_key_and_photo(tmp_path)
    results = run_grading(key, [img, img])[2]
    results[1].annotated = results[1].annotated * 0
    assert show_sheet(1, results)[0].max() == 0 and show_sheet(0, results)[0].max() > 0
