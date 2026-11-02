"""Doc dap an, cham diem, ve anh danh dau va xuat CSV."""
import csv
import os
from collections import Counter
from dataclasses import dataclass, field

import cv2
import numpy as np

from omr_layout import BUBBLE_RADIUS, CHOICES, NUM_QUESTIONS, question_bubble
from omr_read import read_sheet

DONE = "Đã chấm"
REVIEW = "Cần xem lại"
_GREEN, _RED = (0, 170, 0), (0, 0, 230)


class AnswerKeyError(Exception):
    pass


@dataclass
class SheetResult:
    filename: str
    status: str
    student_id: str | None = None
    correct: int | None = None
    score: float | None = None
    notes: list = field(default_factory=list)
    annotated: np.ndarray | None = None
    steps: dict = field(default_factory=dict)


def _trim_row(row):
    """Bo khoang trang va cac cot rong o cuoi dong."""
    cells = [c.strip() for c in row]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def load_answer_key(path):
    """Doc CSV hai cot cau,dap_an; chap nhan file luu tu Excel (BOM, dau ;, chu thuong)."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except (OSError, UnicodeDecodeError) as e:
        raise AnswerKeyError("Không đọc được file đáp án") from e
    if lines and lines[0].lower().startswith("sep="):
        lines = lines[1:]
    if not lines:
        raise AnswerKeyError("File đáp án trống")
    delim = ";" if ";" in lines[0] else ","
    rows = [_trim_row(row) for row in csv.reader(lines, delimiter=delim)]
    rows = [row for row in rows if row]  # Excel hay de lai dong toan dau phan cach
    if not rows or [c.lower() for c in rows[0]] != ["cau", "dap_an"]:
        raise AnswerKeyError("Dòng đầu của file đáp án phải là: cau,dap_an")
    key = {}
    for num, row in enumerate(rows[1:], start=2):
        if len(row) != 2 or not row[0].isdigit():
            raise AnswerKeyError(f"Dòng {num} sai định dạng")
        q, answer = int(row[0]), row[1].upper()
        if len(answer) != 1 or answer not in CHOICES:
            raise AnswerKeyError(f"Dòng {num}: đáp án phải là một trong A, B, C, D")
        if q != len(key) + 1:
            raise AnswerKeyError(f"Dòng {num}: số câu phải liên tục từ 1")
        key[q] = answer
    if not 1 <= len(key) <= NUM_QUESTIONS:
        raise AnswerKeyError(f"Đáp án phải có từ 1 đến {NUM_QUESTIONS} câu")
    return key


def _annotate(warped, marks, key):
    """Vong xanh o dap an dung, vong do o hoc sinh to sai."""
    out = cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR)
    for q, answer in key.items():
        cv2.circle(out, question_bubble(q, answer), BUBBLE_RADIUS + 6, _GREEN, 4)
        for c in marks.get(q, []):
            if c != answer:
                cv2.circle(out, question_bubble(q, c), BUBBLE_RADIUS + 6, _RED, 4)
    return out


def grade_reading(filename, reading, key):
    """Bai doc khong chac chan thi "Can xem lai", khong bao gio cho diem."""
    result = SheetResult(filename, DONE, reading.student_id, steps=reading.steps)
    uncertain = [q for q in reading.uncertain if q in key]
    notes = list(reading.problems) + list(reading.id_problems)
    if uncertain:
        notes.append("Câu không đọc chắc chắn: " + ", ".join(map(str, uncertain)))
    if reading.warped is not None:
        result.annotated = _annotate(reading.warped, reading.marks, key)
    if notes:
        result.status, result.notes = REVIEW, notes
        return result
    blank = [q for q in key if not reading.marks.get(q)]
    multi = [q for q in key if len(reading.marks.get(q, [])) > 1]
    if blank:
        notes.append("Câu bỏ trống: " + ", ".join(map(str, blank)))
    if multi:
        notes.append("Câu tô nhiều ô: " + ", ".join(map(str, multi)))
    result.correct = sum(reading.marks.get(q) == [a] for q, a in key.items())
    result.score = round(result.correct / len(key) * 10, 2)
    result.notes = notes
    return result


def grade_batch(paths, key):
    results = []
    for p in paths:
        name = os.path.basename(p)
        try:
            results.append(grade_reading(name, read_sheet(p), key))
        except Exception as e:  # mot file loi khong duoc lam mat ket qua cua ca lop
            results.append(SheetResult(name, REVIEW, notes=[f"Lỗi khi xử lý ảnh: {e}"]))
    counts = Counter(r.student_id for r in results if r.student_id)
    for r in results:
        if counts.get(r.student_id, 0) > 1:
            r.notes.append(f"Trùng mã học sinh {r.student_id}")
    return results


def write_csv(results, path):
    """utf-8-sig de Excel hien dung tieng Viet."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ten_file", "ma_hoc_sinh", "so_cau_dung", "diem", "trang_thai", "ghi_chu"])
        for r in results:
            w.writerow([r.filename, r.student_id or "",
                        "" if r.correct is None else r.correct,
                        "" if r.score is None else r.score,
                        r.status, "; ".join(r.notes)])
