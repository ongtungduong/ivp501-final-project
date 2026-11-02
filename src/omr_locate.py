"""Tim phieu trong anh chup va nan ve khung chuan."""
from itertools import combinations

import cv2
import numpy as np
from PIL import Image, ImageOps

from omr_layout import MARKER_CENTERS, ORIENTATION_BAR, PAGE_H, PAGE_W

MAX_SIDE = 3000
MAX_CANDIDATES = 12
_MARKER_RATIO = (MARKER_CENTERS[2][1] - MARKER_CENTERS[1][1]) / (MARKER_CENTERS[1][0] - MARKER_CENTERS[0][0])


class SheetUnreadable(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def load_image(path):
    """Doc anh, ap dung huong EXIF cua dien thoai, gioi han kich thuoc; tra ve BGR."""
    try:
        with Image.open(path) as im:
            rgb = np.array(ImageOps.exif_transpose(im).convert("RGB"))
        scale = MAX_SIDE / max(rgb.shape[:2])
        if scale < 1:
            rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    except Exception as e:
        raise SheetUnreadable("Không đọc được file ảnh") from e
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def preprocess(bgr):
    """Anh xam -> loc nhieu -> phan nguong thich nghi (block lon hon duong kinh o tron)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 101, 10)
    return gray, blurred, binary


def _candidates(binary):
    """Contour gan vuong, dac, lon: ung vien o dinh vi. Tra ve [(dien_tich, tam)]."""
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_area = (max(binary.shape) / 200) ** 2
    found = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > 0.02 * binary.size:
            continue
        approx = cv2.approxPolyDP(c, 0.06 * cv2.arcLength(c, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        (cx, cy), (w, h), _ = cv2.minAreaRect(c)
        # phoi canh manh lam o vuong thanh hinh binh hanh, nen do dac tinh theo bao loi
        if min(w, h) == 0 or not 0.5 < w / h < 2.0 or area / cv2.contourArea(cv2.convexHull(c)) < 0.9:
            continue
        # vien trong va vien ngoai cua cung mot o cho hai contour trung tam: chi giu mot
        if all(np.hypot(cx - fx, cy - fy) > 10 for _, (fx, fy) in found):
            found.append((area, (cx, cy)))
    return sorted(found, key=lambda f: -f[0])[:MAX_CANDIDATES]


def _order(pts):
    """Sap xep 4 goc theo vong, canh dai cua tu giac la chieu doc cua phieu."""
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    p = pts[np.argsort(angles)]
    if np.linalg.norm(p[0] - p[1]) > np.linalg.norm(p[1] - p[2]):
        p = np.roll(p, -1, axis=0)
    return p


def _rect_error(p):
    """Do lech cua tu giac so voi hinh chu nhat ti le nhu phieu; None neu khong hop le."""
    if not cv2.isContourConvex(p.astype(np.float32)):
        return None
    top, right, bottom, left = (np.linalg.norm(p[(i + 1) % 4] - p[i]) for i in range(4))
    if min(top, bottom) < 100:
        return None
    if max(top, bottom) / min(top, bottom) > 1.5 or max(left, right) / min(left, right) > 1.5:
        return None
    ratio_err = abs((left + right) / (top + bottom) - _MARKER_RATIO) / _MARKER_RATIO
    return ratio_err if ratio_err < 0.35 else None


def _bar_present(binary, corners):
    """Nan thu anh nhi phan: dung bo 4 o thi thanh dinh huong phai nam o mep tren hoac duoi."""
    w = warp(binary, corners)
    x, y, bw, bh = ORIENTATION_BAR
    top = w[y + 4:y + bh - 4, x + 20:x + bw - 20].mean()
    bottom = cv2.rotate(w, cv2.ROTATE_180)[y + 4:y + bh - 4, x + 20:x + bw - 20].mean()
    return max(top, bottom) > 0.7 * 255 and min(top, bottom) < 0.3 * 255


def _outside(sheet, other):
    """Bo 4 o nay nam han ngoai phieu da chon: trong anh co phieu thu hai."""
    return all(cv2.pointPolygonTest(sheet, (float(x), float(y)), False) < 0 for x, y in other)


def find_markers(binary):
    """Tim 4 o dinh vi: to hop phai dung ti le phieu va khop thanh dinh huong."""
    ranked = []
    for combo in combinations(_candidates(binary), 4):
        areas = [c[0] for c in combo]
        if max(areas) / min(areas) > 2.0:
            continue
        p = _order(np.float32([c[1] for c in combo]))
        err = _rect_error(p)
        if err is not None:
            ranked.append((err, p))
    valid = [p for _, p in ranked if _bar_present(binary, p)]
    if not valid:
        raise SheetUnreadable("Không tìm thấy 4 ô định vị")
    # bo lon nhat la phieu that; cac o da to ben trong phieu cung co the xep thanh bo gia
    valid.sort(key=lambda p: -np.linalg.norm(p[0] - p[2]))
    if any(_outside(valid[0], other) for other in valid[1:]):
        raise SheetUnreadable("Ảnh có nhiều hơn một phiếu")
    return valid[0]


def warp(gray, corners):
    """Bien doi phoi canh ve khung chuan PAGE_W x PAGE_H."""
    m = cv2.getPerspectiveTransform(np.float32(corners), np.float32(MARKER_CENTERS))
    return cv2.warpPerspective(gray, m, (PAGE_W, PAGE_H), flags=cv2.INTER_LINEAR)


def fix_orientation(warped):
    """Dua vao thanh den chi co o mep tren de xac dinh chieu phieu, xoay 180 do neu nguoc."""
    x, y, w, h = ORIENTATION_BAR
    top = warped[y:y + h, x:x + w].mean()
    flipped = cv2.rotate(warped, cv2.ROTATE_180)
    bottom = flipped[y:y + h, x:x + w].mean()
    if min(top, bottom) > 0.6 * max(top, bottom):
        raise SheetUnreadable("Không xác định được chiều phiếu")
    return warped if top < bottom else flipped
