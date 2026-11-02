import csv

import cv2
import pytest

from omr_grade import AnswerKeyError, grade_batch, grade_reading, load_answer_key, write_csv
from omr_read import SheetReading
from omr_sheet import render_sheet
from synth import fill_sheet, photograph


def reading(student_id, marks, uncertain=(), problems=(), id_problems=()):
    return SheetReading(student_id=student_id, marks=marks, uncertain=list(uncertain),
                        problems=list(problems), id_problems=list(id_problems))


def make_batch_files(tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"bai{i}.png"
        cv2.imwrite(str(p), photograph(fill_sheet(render_sheet(), "001234", {1: "A"}), seed=i))
        paths.append(str(p))
    bad = tmp_path / "hong.jpg"
    bad.write_bytes(b"not an image")
    return paths + [str(bad)]


def test_key_from_excel_variants(tmp_path):
    p = tmp_path / "k.csv"
    p.write_bytes("﻿cau;dap_an\r\n1; a \r\n2;B\r\n".encode())
    assert load_answer_key(str(p)) == {1: "A", 2: "B"}


@pytest.mark.parametrize("body", ["cau;dap_an;;\n1;A;;\n;;;\n2;B;;\n",
                                  "sep=;\ncau;dap_an\n1;A\n2;B\n",
                                  "cau,dap_an,\n1,A,\n2,B,\n,,\n"])
def test_key_with_excel_empties(tmp_path, body):
    p = tmp_path / "k.csv"
    p.write_text(body)
    assert load_answer_key(str(p)) == {1: "A", 2: "B"}


def test_batch_survives_unexpected_error(tmp_path, monkeypatch):
    import omr_grade
    monkeypatch.setattr(omr_grade, "read_sheet", lambda p: 1 / 0)
    r = grade_batch(["a.jpg"], {1: "A"})[0]
    assert r.status == "Cần xem lại" and r.score is None and r.notes


@pytest.mark.parametrize("body", ["cau,dap_an\n", "cau,dap_an\n1,E\n", "cau,dap_an\n1,A\n3,B\n",
                                  "x,y\n1,A\n", "cau,dap_an\n1,A\n1,B\n", "cau,dap_an\nabc,A\n"])
def test_bad_key_rejected(tmp_path, body):
    p = tmp_path / "k.csv"
    p.write_text(body)
    with pytest.raises(AnswerKeyError):
        load_answer_key(str(p))


def test_41_questions_rejected(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("cau,dap_an\n" + "".join(f"{i},A\n" for i in range(1, 42)))
    with pytest.raises(AnswerKeyError):
        load_answer_key(str(p))


def test_score_notes_and_leading_zero():
    key = {q: "A" for q in range(1, 41)}
    marks = {q: ["A"] for q in range(1, 38)} | {38: [], 39: ["A", "B"], 40: ["B"]}
    r = grade_reading("a.jpg", reading("001234", marks), key)
    assert (r.status, r.student_id, r.correct, r.score) == ("Đã chấm", "001234", 37, 9.25)
    assert any("38" in n for n in r.notes) and any("39" in n for n in r.notes)


def test_marks_after_N_ignored_even_if_uncertain():
    r = grade_reading("a.jpg", reading("123456", {1: ["A"], 2: ["B"]}, uncertain=[2]), {1: "A"})
    assert (r.status, r.score) == ("Đã chấm", 10.0)


@pytest.mark.parametrize("kw", [dict(uncertain=[1]), dict(problems=["Ảnh bị mờ"]),
                                dict(student_id=None, id_problems=["Thiếu mã"])])
def test_needs_review_has_no_score(kw):
    args = dict(student_id="123456", marks={1: ["A"]}) | kw
    r = grade_reading("a.jpg", reading(**args), {1: "A"})
    assert (r.status, r.score, r.correct) == ("Cần xem lại", None, None)
    assert r.notes


def test_batch_duplicates_and_csv(tmp_path):
    results = grade_batch(make_batch_files(tmp_path), {1: "A"})
    assert [r.status for r in results] == ["Đã chấm", "Đã chấm", "Cần xem lại"]
    assert all(any("Trùng mã" in n for n in r.notes) for r in results[:2])
    assert results[0].annotated is not None
    out = tmp_path / "scores.csv"
    write_csv(results, str(out))
    with open(out, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["ma_hoc_sinh"] == "001234" and rows[0]["diem"] == "10.0"
    assert rows[2]["diem"] == "" and rows[2]["trang_thai"] == "Cần xem lại"
