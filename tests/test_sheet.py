from itertools import combinations
from math import hypot

from omr_layout import (BUBBLE_RADIUS, MARKER_CENTERS, PAGE_H, PAGE_W,
                        id_bubble, question_bubble)
from omr_sheet import render_sheet, save_pdf


def test_bubbles_do_not_overlap_and_stay_on_page():
    pts = [question_bubble(q, c) for q in range(1, 41) for c in "ABCD"]
    pts += [id_bubble(p, d) for p in range(6) for d in range(10)]
    assert len(set(pts)) == 220
    r = BUBBLE_RADIUS
    assert all(2 * r < hypot(a[0] - b[0], a[1] - b[1]) for a, b in combinations(pts, 2))
    assert all(100 < x < PAGE_W - 100 and 100 < y < PAGE_H - 100 for x, y in pts)


def test_render_sheet_shape_and_black_markers():
    img = render_sheet()
    assert img.shape == (PAGE_H, PAGE_W)
    assert all(img[y, x] < 30 for x, y in MARKER_CENTERS)


def test_save_pdf_writes_pdf(tmp_path):
    p = tmp_path / "phieu.pdf"
    save_pdf(str(p))
    assert p.read_bytes()[:4] == b"%PDF"
