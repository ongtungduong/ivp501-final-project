"""Sinh anh mo phong anh chup phieu, da biet truoc dap an."""
import math

import cv2
import numpy as np

from omr_layout import BUBBLE_RADIUS, PAGE_H, PAGE_W, id_bubble, question_bubble


def fill_bubble(img, center, darkness=40, coverage=1.0):
    """To mot o; coverage < 1 chi to phan tren cua o, mo phong net to thieu."""
    x, y = center
    r = int(BUBBLE_RADIUS * 0.9)
    mask = np.zeros(img.shape, np.uint8)
    cv2.circle(mask, (x, y), r, 255, -1)
    mask[y - r + int(2 * r * coverage):] = 0
    img[mask > 0] = darkness


def fill_sheet(img, student_id, answers):
    """Tra ve ban sao cua phieu da to ma hoc sinh va cac cau tra loi."""
    out = img.copy()
    for pos, ch in enumerate(student_id):
        fill_bubble(out, id_bubble(pos, int(ch)))
    for q, choice in answers.items():
        fill_bubble(out, question_bubble(q, choice))
    return out


def photograph(img, angle=0.0, perspective=0.0, brightness=1.0, gradient=0.0, blur=0,
               background=200, seed=0):
    """Mo phong anh chup: dat phieu len nen, xoay, nghieng, doi sang, lam mo, them nhieu."""
    rng = np.random.default_rng(seed)
    side = int(math.hypot(PAGE_W, PAGE_H)) + 200
    cx, cy = side / 2, side / 2
    a = math.radians(angle)
    corners = []
    for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        dx = sx * PAGE_W / 2 + rng.uniform(-perspective, perspective) * PAGE_W
        dy = sy * PAGE_H / 2 + rng.uniform(-perspective, perspective) * PAGE_W
        corners.append((cx + dx * math.cos(a) - dy * math.sin(a),
                        cy + dx * math.sin(a) + dy * math.cos(a)))
    src = np.float32([[0, 0], [PAGE_W, 0], [PAGE_W, PAGE_H], [0, PAGE_H]])
    m = cv2.getPerspectiveTransform(src, np.float32(corners))
    out = cv2.warpPerspective(img, m, (side, side), flags=cv2.INTER_LINEAR,
                              borderValue=int(background)).astype(np.float32)
    out *= brightness
    if gradient:
        out *= np.linspace(1.0, 1.0 - gradient, side, dtype=np.float32)[None, :]
    if blur:
        k = blur | 1
        out = cv2.GaussianBlur(out, (k, k), 0)
    out += rng.normal(0, 2.5, out.shape).astype(np.float32)
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def add_glare(img):
    """Phu mot vung trang loa len khu vuc o tra loi cua phieu xam."""
    out = img.copy()
    x, y = question_bubble(11, "A")
    cv2.circle(out, (x + 100, y + 300), 320, 255, -1)
    return out


def shift_content(img, dx=25):
    """Dich noi dung so voi o dinh vi, mo phong luoi o bi lech."""
    out = img.copy()
    box = out[170:2200, 160:1500].copy()
    out[170:2200, 160:1500] = 255
    out[170:2200, 160 + dx:1500 + dx] = box
    return out
