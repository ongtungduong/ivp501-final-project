"""Doc cac o da to tren phieu da nan va kiem tra chat luong anh."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from omr_layout import (BUBBLE_RADIUS, CHOICES, ID_DIGITS, MARKER_CENTERS, MARKER_SIZE,
                        NUM_QUESTIONS, PAGE_H, PAGE_W, id_bubble, question_bubble)
from omr_locate import (SheetUnreadable, find_markers, fix_orientation, load_image, preprocess,
                        warp)

BLANK_BELOW = 0.25  # ti le diem den trong o
FILLED_ABOVE = 0.75
DARK_PIXEL = 0.75  # do sang so voi nen giay; toi hon muc nay la diem den
SOLID_MEAN = 0.65  # o da to phai du dam; to nhat la "khong chac"
# "O trong" duoc so voi o trong dien hinh cua chinh phieu (trung vi cua moi o): do mo, vien in day,
# nhieu hat giay cua anh chup co san trong mau nen tu triet tieu. Gia tri la muc toi hon mau.
INNER_DEV = 0.08  # trung binh phan trong vien: vet tay do, net to nhat
OUTSIDE_DEV = 0.07  # giay quanh o: bong do, vat den
INK_DEV = 0.25  # diem muc dam
MAX_INNER_INK = 0.02  # net to nho, vien o to bi loa
FAINT_DEV = 0.07  # diem hoi toi (sau khi lam min de bo nhieu hat): net chi nhat
MAX_INNER_FAINT = 0.08  # o trong that toi da ~0.06, net nhat rat mo tren anh mo ~0.10
MAX_DARKNESS_GAP = 0.15  # hai o cung to phai dam nhu nhau, khac nhieu la vet tay
MAX_MISSING_RINGS = 0.05
MIN_SHARPNESS = 0.07  # mo hon muc nay thi net to nhat co the bi nhoe mat; mo nhe van doc dung
RING_COVERAGE = 0.7
RING_CONTRAST = 0.5  # vien thay duoc khi con it nhat ngan nay do tuong phan cua vien o mau
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
    """Loc Gauss roi chia cho nen giay uoc luong duoc de khu anh sang khong deu; giay ~ 1, muc ~ 0."""
    blurred = cv2.GaussianBlur(warped, (5, 5), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))
    background = cv2.morphologyEx(blurred, cv2.MORPH_CLOSE, kernel)
    return blurred.astype(np.float32) / np.maximum(background.astype(np.float32), 1)


_R = int(BUBBLE_RADIUS * 0.7)
_P = BUBBLE_RADIUS + 10
_YY, _XX = np.mgrid[-_P:_P + 1, -_P:_P + 1]
_DIST = np.hypot(_XX, _YY)
_CORE = _DIST <= _R
_INNER = _DIST <= BUBBLE_RADIUS - 5  # chua 1 px cho cho giay cong lam vien o nho lai
_FAINT_ZONE = _DIST <= BUBBLE_RADIUS - 7  # net nhat chi xet xa vien, vien lech nhe khong lam nham
_OUTSIDE = (_DIST >= BUBBLE_RADIUS + 4) & (_DIST <= _P)
_ANGLES = np.arange(36) * 2 * np.pi / 36


def _rays(radii):
    """Toa do lay mau trong patch theo 36 huong. Nhieu diem roi dung vao x.5: lam tron len co
    chu dong (+1e-9) de sai so bit cuoi khong doi diem lay mau, giong het ban MATLAB."""
    pts = [[(_P + r * np.sin(a), _P + r * np.cos(a)) for r in radii] for a in _ANGLES]
    return np.floor(np.array(pts) + 0.5 + 1e-9).astype(int)


# vung vien (R-4..R+4) va giay ngay ben ngoai (ben trong co the da to kin)
_RAYS_RING = _rays(range(BUBBLE_RADIUS - 4, BUBBLE_RADIUS + 5))
_RAYS_PAPER = _rays((BUBBLE_RADIUS + 8, BUBBLE_RADIUS + 9))


_SNAP = 12  # px: sai so nan cuc bo toi da duoc bu lai; nho hon nhieu so voi khoang cach hai o
_T = BUBBLE_RADIUS + 9


def _ring_template():
    """Vong duong o vien in, vong am ngay ben ngoai: o da to cung chi khop dung o mot vi tri.

    Hai vong deu chuan hoa tong = 1, nen diem khop = do toi cua vien tru do toi cua giay quanh.
    """
    yy, xx = np.mgrid[-_T:_T + 1, -_T:_T + 1]
    dist = np.hypot(xx, yy)
    pos = (np.abs(dist - BUBBLE_RADIUS) <= 2.5).astype(np.float32)  # vong day 5 px
    neg = (np.abs(dist - BUBBLE_RADIUS - 6) <= 2.5).astype(np.float32)
    return pos / pos.sum() - neg / neg.sum()


_RING_TEMPLATE = _ring_template()


def ring_score(light):
    """Ban do diem khop vien o tren anh da khu sang (khong qua nhi phan nen chiu duoc anh mo).

    score[y - _T, x - _T] la diem cua o co tam (x, y).
    """
    return cv2.matchTemplate(1 - light, _RING_TEMPLATE, cv2.TM_CCORR)


def _snap(score, center):
    """Can lai tam o theo vien in gan nhat, bu sai so phoi canh va giay cong."""
    x, y = center
    window = score[y - _T - _SNAP:y - _T + _SNAP + 1, x - _T - _SNAP:x - _T + _SNAP + 1]
    _, best, _, (dx, dy) = cv2.minMaxLoc(window)
    return (x, y) if best <= 0 else (x + dx - _SNAP, y + dy - _SNAP)


_PEAK_COUNT = 2  # giu so dinh manh nhat gap doi so o; dinh thua (chu, vet ban) bi loai khi ghep
_POLY_STEPS = ((1, 45), (2, 25), (3, 15))  # (bac da thuc, ban kinh ghep o) tu tho den min
_LOCAL_STEPS = (30, 20, 12, 8)  # ban kinh ghep o khi bu cong cuc bo (vung gan tay cam)
_LOCAL_SIGMA = 60  # px: tam anh huong cua mot o len do lech cua vung quanh no
_MIN_MATCHED = 0.5
_MAX_BEND = 80  # px: lech lon hon muc nay thi khong tin la giay cong
_ANCHOR_WEIGHT = 5


def _ring_peaks(score):
    """Tam cac vien o tim thay tren toan phieu da nan, manh nhat truoc."""
    peaks = (score >= cv2.dilate(score, np.ones((21, 21), np.uint8))) & (score > 0)
    ys, xs = np.nonzero(peaks)
    keep = np.argsort(-score[ys, xs])[:_PEAK_COUNT * len(_all_bubbles())]
    return np.column_stack([xs[keep] + _T, ys[keep] + _T]).astype(np.float32)


def _poly(pts, deg):
    u, v = pts[:, 0] / PAGE_W, pts[:, 1] / PAGE_H
    return np.column_stack([u ** i * v ** j for i in range(deg + 1) for j in range(deg + 1 - i)])


def _smooth(src, values, pts):
    """Noi suy Gauss cac gia tri tai src ve pts; xa moi o thi tat dan ve 0."""
    d2 = ((pts[:, None] - src[None]) ** 2).sum(axis=2)
    w = np.exp(-d2 / (2 * _LOCAL_SIGMA ** 2))
    return (w @ values) / (w.sum(axis=1) + 0.05)[:, None]


def _bend_field(score):
    """Uoc luong do lech giua vi tri o chuan va vi tri o that; None neu khong tin cay.

    Tra ve ham tinh do lech tai cac diem bat ky. Ghep o chuan voi vien o gan nhat, tu ban kinh
    lon va da thuc bac thap toi bac cao, roi bu phan du cuc bo cho cho giay cong gat.
    O dinh vi da duoc nan dung nen co do lech 0.
    """
    template = np.float32(_all_bubbles())
    peaks = _ring_peaks(score)
    if len(peaks) < 2:
        return None

    def match(pred, radius):
        dist = np.linalg.norm(pred[:, None] - peaks[None], axis=2)
        order = np.argsort(dist, axis=1)[:, :2]
        d1, d2 = np.take_along_axis(dist, order, axis=1).T
        ok = (d1 < radius) & (d2 > 1.5 * d1)
        return ok, peaks[order[:, 0]] - template

    anchors = np.repeat(np.float32(MARKER_CENTERS), _ANCHOR_WEIGHT, axis=0)
    disp = np.zeros_like(template)
    for deg, radius in _POLY_STEPS:
        ok, target = match(template + disp, radius)
        if ok.mean() < _MIN_MATCHED:
            return None
        src = np.vstack([template[ok], anchors])
        dst = np.vstack([target[ok], np.zeros_like(anchors)])
        coef = np.linalg.lstsq(_poly(src, deg), dst, rcond=None)[0]
        disp = _poly(template, deg) @ coef

    def base(pts):
        return _poly(pts, deg) @ coef

    for radius in _LOCAL_STEPS:
        ok, target = match(template + disp, radius)
        if ok.mean() < _MIN_MATCHED:
            return None
        src, residual = template[ok], target[ok] - base(template[ok])
        disp = base(template) + _smooth(src, residual, template)
    return lambda pts: base(pts) + _smooth(src, residual, pts)


_GRID_STEP = 16  # px: tinh do lech tren luoi thua roi noi suy tuyen tinh ra tung diem anh


def _lerp_matrix(n, count):
    """Ma tran noi suy tuyen tinh tu luoi 0, step, 2*step, ... (count diem) ra cac toa do 0..n-1."""
    pos = np.arange(n) / _GRID_STEP
    i = np.minimum(pos.astype(int), count - 2)
    t = pos - i
    m = np.zeros((n, count), np.float32)
    m[np.arange(n), i] = 1 - t
    m[np.arange(n), i + 1] = t
    return m


def unbend(warped):
    """Bu giay cong: nan lai anh de cac o that trung voi vi tri chuan; khong tin cay thi giu nguyen."""
    field = _bend_field(ring_score(_normalize_light(warped)))
    if field is None:
        return warped
    gy, gx = np.mgrid[0:PAGE_H + _GRID_STEP:_GRID_STEP, 0:PAGE_W + _GRID_STEP:_GRID_STEP]
    disp = field(np.column_stack([gx.ravel(), gy.ravel()]).astype(np.float32))
    if np.abs(disp).max() > _MAX_BEND:
        return warped
    my, mx = _lerp_matrix(PAGE_H, gx.shape[0]), _lerp_matrix(PAGE_W, gx.shape[1])
    dx = my @ disp[:, 0].reshape(gx.shape).astype(np.float32) @ mx.T
    dy = my @ disp[:, 1].reshape(gx.shape).astype(np.float32) @ mx.T
    xs, ys = np.meshgrid(np.arange(PAGE_W, dtype=np.float32), np.arange(PAGE_H, dtype=np.float32))
    return cv2.remap(warped, xs + dx, ys + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _patch(norm, center):
    x, y = center
    return norm[y - _P:y + _P + 1, x - _P:x + _P + 1]


def _bubble_state(norm, center, blank_ref):
    """Ty le diem den trong loi o -> filled / blank / uncertain.

    "Trong" can bang chung: ben trong vien in va giay xung quanh giong o trong dien hinh cua phieu.
    """
    patch = _patch(norm, center)
    core = patch[_CORE]
    dev = blank_ref - patch
    if dev[_OUTSIDE].mean() > OUTSIDE_DEV:
        return "uncertain"
    state = classify_ratio(float((core < DARK_PIXEL).mean()))
    if state == "filled":
        return "filled" if core.mean() <= SOLID_MEAN else "uncertain"
    inner = dev[_INNER]
    faint = cv2.blur(dev.astype(np.float32), (7, 7))[_FAINT_ZONE]
    if (inner.mean() > INNER_DEV or (inner > INK_DEV).mean() > MAX_INNER_INK
            or (faint > FAINT_DEV).mean() > MAX_INNER_FAINT):
        return "uncertain"
    return state


def _blank_reference(norm, score):
    """O trong dien hinh cua phieu: trung vi patch cua moi o (da so o la o trong).

    Chia ca anh va mau cho muc giay cua mau de giay ~ 1 bat ke giay xam hay anh toi.
    """
    ref = np.median([_patch(norm, _snap(score, p)) for p in _all_bubbles()], axis=0)
    level = max(float(ref[_OUTSIDE].mean()), 0.5)
    return norm / level, ref / level


def _ring_contrast(patch):
    """Do tuong phan vien in theo 36 huong: giay ben ngoai tru diem toi nhat trong vung vien."""
    ring = patch[_RAYS_RING[..., 0], _RAYS_RING[..., 1]].min(axis=1)
    paper = patch[_RAYS_PAPER[..., 0], _RAYS_PAPER[..., 1]].mean(axis=1)
    return paper - ring


def _ring_visible(norm, center, blank_ref):
    """Vien in cua o co ro nhu o trong dien hinh khong? Bi loa che thi mat vien o nhieu huong."""
    seen = _ring_contrast(_patch(norm, center)) >= RING_CONTRAST * _ring_contrast(blank_ref)
    return seen.mean() >= RING_COVERAGE


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


def check_quality(warped, norm, score, blank_ref):
    """Bao anh mo qua do net cua canh; bao loa/lech khi khong thay vien cua nhieu o."""
    problems = []
    if _edge_sharpness(warped) < MIN_SHARPNESS:
        problems.append("Ảnh bị mờ")
    pts = _all_bubbles()
    missing = sum(not _ring_visible(norm, _snap(score, p), blank_ref) for p in pts)
    if missing / len(pts) > MAX_MISSING_RINGS:
        problems.append("Ảnh bị lóa hoặc lưới ô bị lệch")
    return problems


def _read_id(norm, score, blank_ref):
    digits, problems = [], []
    for pos in range(ID_DIGITS):
        states = [_state(norm, score, id_bubble(pos, d), blank_ref) for d in range(10)]
        filled = [d for d, s in enumerate(states) if s == "filled"]
        if "uncertain" in states or len(filled) != 1:
            problems.append(f"Mã học sinh: chữ số thứ {pos + 1} không đọc được")
        else:
            digits.append(str(filled[0]))
    return ("".join(digits) if not problems else None), problems


def _state(norm, score, center, blank_ref):
    """O trong ma khong thay vien (bi loa che) thi khong the coi la chac chan trong."""
    center = _snap(score, center)
    state = _bubble_state(norm, center, blank_ref)
    if state == "blank" and not _ring_visible(norm, center, blank_ref):
        return "uncertain"
    return state


def _uneven_marks(norm, score, q, filled):
    """Hai o to dam khac han nhau: o nhat hon co the la vet tay chua sach."""
    if len(filled) < 2:
        return False
    means = [_patch(norm, _snap(score, question_bubble(q, c)))[_CORE].mean() for c in filled]
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
        corners = find_markers(binary, gray)
        marked = bgr.copy()
        for x, y in corners:
            cv2.circle(marked, (int(x), int(y)), 40, (0, 0, 255), 8)
        r.steps["dinh_vi"] = _small(marked)
        warped = fix_orientation(warp(gray, corners))
    except SheetUnreadable as e:
        r.problems.append(e.reason)
        return r
    r.steps["nan_phoi_canh"] = _small(warped)
    warped = unbend(warped)
    r.warped = warped
    r.steps["nan_giay_cong"] = _small(warped)
    light = _normalize_light(warped)
    score = ring_score(light)
    norm, blank_ref = _blank_reference(light, score)
    r.steps["khu_anh_sang"] = _small((np.clip(norm, 0, 1) * 255).astype(np.uint8))
    r.problems += check_quality(warped, norm, score, blank_ref)
    r.student_id, r.id_problems = _read_id(norm, score, blank_ref)
    for q in range(1, NUM_QUESTIONS + 1):
        states = {c: _state(norm, score, question_bubble(q, c), blank_ref) for c in CHOICES}
        r.marks[q] = [c for c, s in states.items() if s == "filled"]
        if "uncertain" in states.values() or _uneven_marks(norm, score, q, r.marks[q]):
            r.uncertain.append(q)
    return r
