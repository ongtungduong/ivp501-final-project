"""Doc cac o da to tren phieu da nan va kiem tra chat luong anh."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from omr_layout import (BUBBLE_RADIUS, CHOICES, ID_DIGITS, MARKER_CENTERS, MARKER_SIZE,
                        NUM_QUESTIONS, id_bubble, question_bubble)
from omr_locate import (SheetUnreadable, find_markers, fix_orientation, load_image, preprocess,
                        warp)

BLANK_BELOW = 0.25  # ti le diem den trong o
FILLED_ABOVE = 0.75
DARK_PIXEL = 0.75  # do sang so voi nen giay; toi hon muc nay la diem den
SOLID_MEAN = 0.65  # o da to phai du dam; to nhat la "khong chac"
PAPER = 0.92  # sang hon muc nay moi coi la giay sach
MAX_INNER_MARKS = 0.05  # o "trong" phai sach ca phan ben trong vien in
MAX_DIRTY_OUTSIDE = 0.15  # giay quanh o phai sach, neu khong co the la bong do
MAX_DARKNESS_GAP = 0.15  # hai o cung to phai dam nhu nhau, khac nhieu la vet tay
MAX_MISSING_RINGS = 0.05
MIN_SHARPNESS = 0.12
RING_COVERAGE = 0.7
STEP_MAX_SIDE = 1000


@dataclass
class SheetReading:
    student_id: str | None = None
    id_problems: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)
    uncertain: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    steps: dict = field(default_factory=dict)
    warped: np.ndarray | None = None


def classify_ratio(ratio):
    if ratio < BLANK_BELOW:
        return "blank"
    return "filled" if ratio > FILLED_ABOVE else "uncertain"


def _normalize_light(warped):
    """Chia cho nen giay uoc luong duoc de khu anh sang khong deu; giay ~ 1, muc ~ 0."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
    background = cv2.morphologyEx(warped, cv2.MORPH_CLOSE, kernel)
    return warped.astype(np.float32) / np.maximum(background.astype(np.float32), 1)


_R = int(BUBBLE_RADIUS * 0.7)
_P = BUBBLE_RADIUS + 10
_YY, _XX = np.mgrid[-_P:_P + 1, -_P:_P + 1]
_DIST = np.hypot(_XX, _YY)
_CORE = _DIST <= _R
_INNER = _DIST <= BUBBLE_RADIUS - 4
_OUTSIDE = (_DIST >= BUBBLE_RADIUS + 4) & (_DIST <= _P)
_ANGLES = np.linspace(0, 2 * np.pi, 36, endpoint=False)


_SNAP = 8  # px: sai so nan cuc bo toi da duoc bu lai
_T = BUBBLE_RADIUS + 7
_RING_TEMPLATE = np.zeros((2 * _T + 1, 2 * _T + 1), np.float32)
# vong duong o vien in, vong am ngay ben ngoai: o da to cung chi khop dung o mot vi tri
cv2.circle(_RING_TEMPLATE, (_T, _T), BUBBLE_RADIUS + 5, -1.0, 3)
cv2.circle(_RING_TEMPLATE, (_T, _T), BUBBLE_RADIUS, 1.0, 2)


def _snap(binary, center):
    """Can lai tam o theo vien in gan nhat, bu sai so phoi canh va giay cong."""
    x, y = center
    half = _T + _SNAP
    window = binary[y - half:y + half + 1, x - half:x + half + 1].astype(np.float32)
    score = cv2.matchTemplate(window, _RING_TEMPLATE, cv2.TM_CCORR)
    _, best, _, (dx, dy) = cv2.minMaxLoc(score)
    return (x, y) if best <= 0 else (x + dx - _SNAP, y + dy - _SNAP)


def _patch(norm, center):
    x, y = center
    return norm[y - _P:y + _P + 1, x - _P:x + _P + 1]


def _bubble_state(norm, center):
    """Ty le diem den trong loi o -> filled / blank / uncertain.

    "Trong" can bang chung: ben trong vien in sach va giay xung quanh sach.
    """
    patch = _patch(norm, center)
    core = patch[_CORE]
    if (patch[_OUTSIDE] < PAPER).mean() > MAX_DIRTY_OUTSIDE:
        return "uncertain"
    state = classify_ratio(float((core < DARK_PIXEL).mean()))
    if state == "filled":
        return "filled" if core.mean() <= SOLID_MEAN else "uncertain"
    if (patch[_INNER] < PAPER).mean() > MAX_INNER_MARKS:
        return "uncertain"
    return state


def _ring_visible(binary, center):
    """Vien in cua o co nam dung cho khong? Xet 36 huong quanh tam, cho phep lech 4 px."""
    x, y = center
    seen = 0
    for a in _ANGLES:
        for r in range(BUBBLE_RADIUS - 4, BUBBLE_RADIUS + 5):
            if binary[int(y + r * np.sin(a)), int(x + r * np.cos(a))]:
                seen += 1
                break
    return seen / len(_ANGLES) >= RING_COVERAGE


def _all_bubbles():
    pts = [question_bubble(q, c) for q in range(1, NUM_QUESTIONS + 1) for c in CHOICES]
    return pts + [id_bubble(p, d) for p in range(ID_DIGITS) for d in range(10)]


def _edge_sharpness(warped):
    """Do doc lon nhat tai canh trai cua cac o dinh vi, chia cho do tuong phan; canh net ~ 0.5."""
    half = MARKER_SIZE // 2
    values = []
    for x, y in MARKER_CENTERS:
        profile = warped[y - 15:y + 15, x - half - 25:x - half + 25].mean(axis=0)
        contrast = float(profile.max() - profile.min())
        values.append(float(np.abs(np.diff(profile)).max()) / max(contrast, 1.0))
    return min(values)


def check_quality(warped, binary):
    """Bao anh mo qua do net cua canh; bao loa/lech khi khong thay vien cua nhieu o."""
    problems = []
    if _edge_sharpness(warped) < MIN_SHARPNESS:
        problems.append("Ảnh bị mờ")
    pts = _all_bubbles()
    missing = sum(not _ring_visible(binary, _snap(binary, p)) for p in pts)
    if missing / len(pts) > MAX_MISSING_RINGS:
        problems.append("Ảnh bị lóa hoặc lưới ô bị lệch")
    return problems


def _read_id(norm, binary):
    digits, problems = [], []
    for pos in range(ID_DIGITS):
        states = [_state(norm, binary, id_bubble(pos, d)) for d in range(10)]
        filled = [d for d, s in enumerate(states) if s == "filled"]
        if "uncertain" in states or len(filled) != 1:
            problems.append(f"Mã học sinh: chữ số thứ {pos + 1} không đọc được")
        else:
            digits.append(str(filled[0]))
    return ("".join(digits) if not problems else None), problems


def _state(norm, binary, center):
    """O trong ma khong thay vien (bi loa che) thi khong the coi la chac chan trong."""
    center = _snap(binary, center)
    state = _bubble_state(norm, center)
    if state == "blank" and not _ring_visible(binary, center):
        return "uncertain"
    return state


def _uneven_marks(norm, binary, q, filled):
    """Hai o to dam khac han nhau: o nhat hon co the la vet tay chua sach."""
    if len(filled) < 2:
        return False
    means = [_patch(norm, _snap(binary, question_bubble(q, c)))[_CORE].mean() for c in filled]
    return max(means) - min(means) > MAX_DARKNESS_GAP


def _small(img):
    scale = STEP_MAX_SIDE / max(img.shape[:2])
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img


def read_sheet(path):
    """Doc mot anh bai lam; anh khong doc duoc thi ghi ly do vao problems, khong raise."""
    r = SheetReading()
    try:
        bgr = load_image(path)
        r.steps["goc"] = _small(bgr)
        gray, _, binary = preprocess(bgr)
        r.steps["xam"] = _small(gray)
        r.steps["nhi_phan"] = _small(binary)
        corners = find_markers(binary)
        marked = bgr.copy()
        for x, y in corners:
            cv2.circle(marked, (int(x), int(y)), 40, (0, 0, 255), 8)
        r.steps["dinh_vi"] = _small(marked)
        warped = fix_orientation(warp(gray, corners))
    except SheetUnreadable as e:
        r.problems.append(e.reason)
        return r
    r.warped = warped
    r.steps["nan_phoi_canh"] = _small(warped)
    wbinary = preprocess(cv2.cvtColor(warped, cv2.COLOR_GRAY2BGR))[2]
    norm = _normalize_light(cv2.GaussianBlur(warped, (5, 5), 0))
    r.steps["khu_anh_sang"] = _small((np.clip(norm, 0, 1) * 255).astype(np.uint8))
    r.problems += check_quality(warped, wbinary)
    r.student_id, r.id_problems = _read_id(norm, wbinary)
    for q in range(1, NUM_QUESTIONS + 1):
        states = {c: _state(norm, wbinary, question_bubble(q, c)) for c in CHOICES}
        r.marks[q] = [c for c, s in states.items() if s == "filled"]
        if "uncertain" in states.values() or _uneven_marks(norm, wbinary, q, r.marks[q]):
            r.uncertain.append(q)
    return r
