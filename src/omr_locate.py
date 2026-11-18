"""Tim phieu trong anh chup va nan ve khung chuan.

Luong chinh (buoc 1-4 cua slide): load_image -> preprocess (xam, Gauss, nguong thich nghi)
-> find_markers (tim 4 o dinh vi) -> warp (phoi canh) -> fix_orientation (sua nguoc dau).
Moi loi khong cuu duoc (khong thay 4 o, 2 phieu, khong ro chieu) deu ne SheetUnreadable de
omr_read.read_sheet doi thanh "Can xem lai" thay vi doan.
"""
from itertools import combinations

import cv2
import numpy as np
from PIL import Image, ImageOps

from omr_layout import MARKER_CENTERS, ORIENTATION_BAR, PAGE_H, PAGE_W

MAX_SIDE = 3000  # thu anh ve toi da 3000 px canh dai: du net cho o dinh vi, tranh anh 12MP lam cham
# Chi giu 12 ung vien lon nhat. find_markers thu MOI to hop 4 trong so nay: C(12,4)=495 to hop,
# con 20 ung vien la 4845. 12 du cho 4 o that + vai o gia (chu in, o tron to dam), ma van nhanh.
MAX_CANDIDATES = 12
MAX_INK_RATIO = 0.3  # (nguong "toi hon han": trung vi muc xam trong o < 0.3 x trung vi giay quanh) o dinh vi la muc den in tren giay trang: trong toi hon han vien quanh
BAR_SLACK = 40  # px: giay cong lam thanh dinh huong lech khoi vi tri chuan sau khi nan
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
    # Xam: vi muc chi can do "toi/sang", mau khong them thong tin, ma giam 3 lan du lieu.
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Gauss 5x5: lam min nhieu hat/JPEG de contour khong bi rang cua.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Nguong thich nghi: moi diem duoc so voi trung binh Gauss cua 101x101 diem quanh no (tru C=10).
    # Nguong toan cuc (Otsu) hong khi anh co ben toi ben sang; cach nay chi quan tam "toi hon
    # lan can", nen chiu duoc anh sang khong deu. Block 101 phai lon hon o dinh vi de trung binh
    # lan can chu yeu la giay (neu block nho hon o, giua o dac se "bang" nen khong con la toi hon
    # lan can). THRESH_BINARY_INV: net den -> 255
    # (trang) de findContours coi vat the la tien canh.
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 101, 10)
    return gray, blurred, binary


def _ink_on_paper(gray, contour, area):
    """Trong contour toi hon han dai giay bao quanh; loai phim ban phim, vat toi tren nen toi.

    Chi xet khung bao cua contour noi rong them nua cua so gian no, khong tao mat na ca anh.
    """
    k = max(int(np.sqrt(area) * 0.25), 3) | 1  # be rong vanh giay = 1/4 canh o, ep le (| 1) cho kernel
    x, y, w, h = cv2.boundingRect(contour)
    x0, y0 = max(x - k // 2, 0), max(y - k // 2, 0)
    roi = gray[y0:y + h + k // 2, x0:x + w + k // 2]
    mask = np.zeros(roi.shape, np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1, offset=(-x0, -y0))
    # vanh = ban gian no tru ban goc -> dai giay ngay sat ngoai contour
    ring = cv2.dilate(mask, np.ones((k, k), np.uint8)) - mask
    # So trung vi (khong phai trung binh) de it bi anh huong boi vai diem sang/toi bat thuong.
    return np.median(roi[mask > 0]) < MAX_INK_RATIO * np.median(roi[ring > 0])


def _candidates(binary, gray):
    """Contour gan vuong, dac, lon, la muc tren giay: ung vien o dinh vi. Tra ve [(dien_tich, tam)]."""
    # RETR_LIST: lay moi contour, khong lap cay long nhau (o dinh vi la khoi dac, khong can phan cap)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    # Dien tich toi thieu = (canh dai anh / 200)^2, tuc canh ~0.5% anh: chi de loai hat nhieu li ti.
    # Muc nay rat thap so voi o that (~2.5% chieu cao phieu), nen khong bo sot o ke ca khi phieu
    # chiem it anh; cac bo loc ben duoi moi la thu loai o gia.
    min_area = (max(binary.shape) / 200) ** 2
    found = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > 0.02 * binary.size:  # qua nho = nhieu, qua lon (>2% anh) = khong phai o
            continue
        # Xap xi da giac, sai so 6% chu vi: o vuong that ra dung 4 dinh, chu cai/o tron thi khong.
        approx = cv2.approxPolyDP(c, 0.06 * cv2.arcLength(c, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        (cx, cy), (w, h), _ = cv2.minAreaRect(c)  # hop chu nhat nho nhat, chiu duoc xoay
        # phoi canh manh lam o vuong thanh hinh binh hanh, nen do dac tinh theo bao loi
        if min(w, h) == 0 or not 0.5 < w / h < 2.0 or area / cv2.contourArea(cv2.convexHull(c)) < 0.9:
            continue
        if not _ink_on_paper(gray, c, area):
            continue
        # vien trong va vien ngoai cua cung mot o cho hai contour trung tam: chi giu mot
        # (nguong 10 px: hai contour cua cung o co tam lech nhau chi vai px)
        if all(np.hypot(cx - fx, cy - fy) > 10 for _, (fx, fy) in found):
            found.append((area, (cx, cy)))
    return sorted(found, key=lambda f: -f[0])[:MAX_CANDIDATES]


def _order(pts):
    """Sap xep 4 goc theo vong, canh dai cua tu giac la chieu doc cua phieu."""
    # Sap theo goc quanh tam: 4 diem cua mot tu giac loi se di vong tron, bat ke phieu xoay the nao.
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    p = pts[np.argsort(angles)]
    # Phieu A4 dung (cao > rong): canh p0-p1 phai la canh NGAN (canh ngang tren). Neu no dai hon
    # canh ke p1-p2 thi ta dang bat dau o cung sai -> xoay vong 1 vi tri. Chua biet tren/duoi:
    # viec do (xoay 180 do) la cua fix_orientation.
    if np.linalg.norm(p[0] - p[1]) > np.linalg.norm(p[1] - p[2]):
        p = np.roll(p, -1, axis=0)
    return p


def _rect_error(p):
    """Do lech cua tu giac so voi hinh chu nhat ti le nhu phieu; None neu khong hop le."""
    if not cv2.isContourConvex(p.astype(np.float32)):
        return None
    top, right, bottom, left = (np.linalg.norm(p[(i + 1) % 4] - p[i]) for i in range(4))
    if min(top, bottom) < 100:  # qua nho: nhieu hoac cac o gia nam sat nhau
        return None
    # Phoi canh vua phai chi lam hai canh doi dien chenh nhau chut; chenh >1.5 lan la khong phai phieu.
    if max(top, bottom) / min(top, bottom) > 1.5 or max(left, right) / min(left, right) > 1.5:
        return None
    # Ti le (canh doc / canh ngang) cua phieu that la (2259-80)/(1574-80)=1.46. So voi ti le do duoc,
    # cho sai 35% de du dung cho phoi canh, nhung du chat de loai bo cac to hop vo nghia.
    ratio_err = abs((left + right) / (top + bottom) - _MARKER_RATIO) / _MARKER_RATIO
    return ratio_err if ratio_err < 0.35 else None


_BAR_X0 = ORIENTATION_BAR[0] + 20  # vung chua thanh dinh huong trong khung chuan, cho lech +-BAR_SLACK
_BAR_Y0 = ORIENTATION_BAR[1] - BAR_SLACK
_BAR_SIZE = (ORIENTATION_BAR[2] - 40, ORIENTATION_BAR[3] + 2 * BAR_SLACK)  # (rong, cao)
# toa do khung chuan cua vung o mep tren va (sau khi xoay 180 do) o mep duoi
_BAR_TOP = np.float64([[1, 0, _BAR_X0], [0, 1, _BAR_Y0], [0, 0, 1]])
_BAR_BOTTOM = np.float64([[-1, 0, PAGE_W - 1 - _BAR_X0], [0, -1, PAGE_H - 1 - _BAR_Y0], [0, 0, 1]])


def _bar_level(band, darkest):
    """Muc sang cua dai cao bang thanh dinh huong, toi nhat (hoac sang nhat) trong vung."""
    # Thanh cao 20 px. Lay trung binh theo hang (mean axis=1) -> 1 gia tri sang moi hang, roi truot
    # cua so cao 12 px (=20-8, chua 8 px du phong lech/mo): tim vi tri cua so toi (hoac sang) nhat.
    # Thanh that du dai de lap day cua so; chu in/nhieu thi khong du dai nen khong dat muc cuc tri.
    h = ORIENTATION_BAR[3] - 8
    bands = np.convolve(band.mean(axis=1), np.ones(h) / h, mode="valid")
    return bands.max() if darkest else bands.min()


def _bar_band(img):
    w, h = _BAR_SIZE
    return img[_BAR_Y0:_BAR_Y0 + h, _BAR_X0:_BAR_X0 + w]


def _bar_present(binary, corners):
    """Dung bo 4 o thi thanh dinh huong phai nam o mep tren hoac duoi.

    Chi nan vung quanh thanh dinh huong (khong nan ca phieu) vi buoc nay chay cho moi bo 4 o.
    """
    # m: khung chuan -> anh goc (chieu nguoc voi warp). Chi cat cua so quanh thanh (WARP_INVERSE_MAP
    # voi "place" dich/lat toi vung do) de khong phai nan ca phieu cho moi bo 4 o con lai sau cac bo loc.
    m = cv2.getPerspectiveTransform(np.float32(MARKER_CENTERS), np.float32(corners)).astype(np.float64)
    top, bottom = (_bar_level(cv2.warpPerspective(binary, m @ place, _BAR_SIZE,
                                                  flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP), True)
                   for place in (_BAR_TOP, _BAR_BOTTOM))
    # Dung la phieu: mot dau co thanh den (>0.7 trang trong anh nhi phan) va dau kia KHONG co (<0.3).
    # Hai dau deu co hoac deu khong -> khong phai phieu cua minh (vd 4 o tron to dam ben trong phieu).
    return max(top, bottom) > 0.7 * 255 and min(top, bottom) < 0.3 * 255


def _outside(sheet, other):
    """Bo 4 o nay nam han ngoai phieu da chon: trong anh co phieu thu hai."""
    return all(cv2.pointPolygonTest(sheet, (float(x), float(y)), False) < 0 for x, y in other)


def find_markers(binary, gray):
    """Tim 4 o dinh vi: to hop phai dung ti le phieu va khop thanh dinh huong."""
    ranked = []
    for combo in combinations(_candidates(binary, gray), 4):
        areas = [c[0] for c in combo]
        # 4 o in cung kich thuoc; phoi canh mac dinh chi doi dien tich < 2 lan.
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
    # Ma tran homography 3x3 tinh tu dung 4 cap diem (4 goc thay trong anh -> 4 tam chuan).
    # 4 cap la so toi thieu de giai 8 an cua homography; vi vay moi o dinh vi quan trong.
    m = cv2.getPerspectiveTransform(np.float32(corners), np.float32(MARKER_CENTERS))
    return cv2.warpPerspective(gray, m, (PAGE_W, PAGE_H), flags=cv2.INTER_LINEAR)


def fix_orientation(warped):
    """Dua vao thanh den chi co o mep tren de xac dinh chieu phieu, xoay 180 do neu nguoc."""
    # Sau warp, neu phieu xuoi thi thanh den o tren. Do muc sang vung tren (top) va vung tren cua
    # anh da lat 180 do (bottom = chinh la mep duoi that). Vung co thanh den toi hon -> la mep tren.
    top = _bar_level(_bar_band(warped), False)
    flipped = cv2.rotate(warped, cv2.ROTATE_180)
    bottom = _bar_level(_bar_band(flipped), False)
    if min(top, bottom) > 0.6 * max(top, bottom):  # hai dau gan nhu nhau: khong phan biet duoc, khong doan
        raise SheetUnreadable("Không xác định được chiều phiếu")
    return warped if top < bottom else flipped
