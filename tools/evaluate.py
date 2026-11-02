"""Do do chinh xac tren anh mo phong: moi loai 100 bai, seed co dinh."""
import os
import random
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

import cv2

ROOT = Path(__file__).parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from omr_grade import DONE, grade_reading  # noqa: E402
from omr_layout import CHOICES, question_bubble  # noqa: E402
from omr_read import read_sheet  # noqa: E402
from omr_sheet import render_sheet  # noqa: E402
from synth import fill_bubble, fill_sheet, photograph  # noqa: E402

N = 100
BLANK = render_sheet()
CASES = {
    "Sạch": lambda r: {},
    "Xoay ±15°": lambda r: dict(angle=r.uniform(-15, 15)),
    "Xoay 90/180/270°": lambda r: dict(angle=r.choice([90, 180, 270]) + r.uniform(-3, 3)),
    "Phối cảnh": lambda r: dict(perspective=r.uniform(.02, .07)),
    "Tối": lambda r: dict(brightness=r.uniform(.35, .6)),
    "Ánh sáng không đều": lambda r: dict(gradient=r.uniform(.3, .6)),
    "Nét tô nhạt": lambda r: {},
    "Vết tẩy sạch": lambda r: {},
    "Vết tẩy dở": lambda r: {},
}


MUST_REVIEW = ("Nét tô nhạt", "Vết tẩy dở")  # co diem la vi pham quy tac


def run_one(args):
    name, seed = args
    r = random.Random(f"{name}{seed}")
    student = "".join(r.choice("0123456789") for _ in range(6))
    key = {q: r.choice(CHOICES) for q in range(1, 41)}
    answers = {q: (key[q] if r.random() < .7 else r.choice(CHOICES))
               for q in key if r.random() > .05}
    faint_q = r.randint(1, 40)
    if name == "Nét tô nhạt":
        answers.pop(faint_q, None)  # net nhat nam o cau chua to, dung tinh huong can xem lai
    img = fill_sheet(BLANK, student, answers)
    if name == "Nét tô nhạt":
        fill_bubble(img, question_bubble(faint_q, r.choice(CHOICES)),
                    darkness=r.randint(170, 225), coverage=r.uniform(.3, 1))
    if name in ("Vết tẩy sạch", "Vết tẩy dở"):
        for q in r.sample(list(key), 5):
            others = [c for c in CHOICES if c != answers.get(q)]
            fill_bubble(img, question_bubble(q, r.choice(others)),
                        darkness=246 if name == "Vết tẩy sạch" else r.randint(170, 228))
    photo = photograph(img, seed=seed, **CASES[name](r))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jpg")
        cv2.imwrite(p, photo, [cv2.IMWRITE_JPEG_QUALITY, 88])
        res = grade_reading("a.jpg", read_sheet(p), key)
    if res.status != DONE:
        return name, "review"
    if name in MUST_REVIEW:
        return name, "wrong"
    correct = sum(answers.get(q) == a for q, a in key.items())
    ok = res.student_id == student and res.correct == correct
    return name, "ok" if ok else "wrong"


if __name__ == "__main__":
    names = sys.argv[1:] or list(CASES)
    jobs = [(name, s) for name in names for s in range(N)]
    with Pool() as pool:
        out = pool.map(run_one, jobs, chunksize=5)
    print(f"{'Loại':<22}{'Số bài':>7}{'Đúng':>7}{'Sai':>6}{'Xem lại':>9}")
    for name in names:
        vals = [v for n, v in out if n == name]
        print(f"{name:<22}{len(vals):>7}{vals.count('ok'):>7}{vals.count('wrong'):>6}{vals.count('review'):>9}")
