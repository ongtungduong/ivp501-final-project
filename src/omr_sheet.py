"""Ve phieu tra loi va xuat PDF de in."""
import unicodedata
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from omr_layout import (BUBBLE_RADIUS, CHOICES, ID_DIGITS, MARKER_CENTERS, MARKER_SIZE,
                        NUM_QUESTIONS, ORIENTATION_BAR, PAGE_H, PAGE_W, id_bubble,
                        question_bubble)

_FONTS = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "Arial Unicode.ttf"]


@lru_cache(maxsize=None)
def _load_font(size):
    """Tra ve (font, co_dau): may khong co font tieng Viet thi in khong dau."""
    for name in _FONTS:
        try:
            return ImageFont.truetype(name, size), True
        except OSError:
            continue
    return ImageFont.load_default(size), False


def _ascii(text):
    text = text.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode()


def render_sheet():
    """Ve phieu trang, tra ve anh xam uint8 kich thuoc PAGE_H x PAGE_W."""
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    half = MARKER_SIZE // 2
    for x, y in MARKER_CENTERS:
        img[y - half:y + half, x - half:x + half] = 0
    bx, by, bw, bh = ORIENTATION_BAR
    img[by:by + bh, bx:bx + bw] = 0

    pts = [question_bubble(q, c) for q in range(1, NUM_QUESTIONS + 1) for c in CHOICES]
    pts += [id_bubble(p, d) for p in range(ID_DIGITS) for d in range(10)]
    for pt in pts:
        cv2.circle(img, pt, BUBBLE_RADIUS, 70, 2, cv2.LINE_AA)

    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)

    def text(xy, s, size=26, anchor="mm"):
        font, has_vn = _load_font(size)
        draw.text(xy, s if has_vn else _ascii(s), font=font, fill=0, anchor=anchor)

    text((180, 170), "PHIẾU TRẢ LỜI TRẮC NGHIỆM", 40, "lm")
    text((180, 300), "Họ và tên: ____________________________", 30, "lm")
    text((180, 400), "Lớp: ______________", 30, "lm")
    text((180, 520), "Tô kín một ô cho mỗi câu, dùng bút chì 2B", 26, "lm")
    text((180, 565), "hoặc bút mực tối màu.", 26, "lm")
    text((id_bubble(0, 0)[0] + 175, 195), "MÃ HỌC SINH", 30)
    for d in range(10):
        text((id_bubble(0, d)[0] - 50, id_bubble(0, d)[1]), str(d))
    for q in range(1, NUM_QUESTIONS + 1):
        x, y = question_bubble(q, "A")
        text((x - 55, y), str(q))
        if (q - 1) % 10 == 0:
            for c in CHOICES:
                cx, cy = question_bubble(q, c)
                text((cx, cy - 50), c)
    return np.array(pil)


def save_pdf(path):
    Image.fromarray(render_sheet()).save(path, "PDF", resolution=200)
