import cv2
import numpy as np
import pytest
from PIL import Image

from omr_layout import MARKER_CENTERS, ORIENTATION_BAR
from omr_locate import (SheetUnreadable, find_markers, fix_orientation, load_image,
                        preprocess, warp)
from omr_sheet import render_sheet
from synth import photograph


def locate(bgr):
    gray, _, binary = preprocess(bgr)
    return fix_orientation(warp(gray, find_markers(binary)))


def markers_dark(w):
    return all(w[y, x] < 90 for x, y in MARKER_CENTERS)


def save_jpeg_with_exif_orientation(tmp_path, img, orientation):
    exif = Image.Exif()
    exif[0x0112] = orientation
    p = tmp_path / "exif.jpg"
    Image.fromarray(img).rotate(90, expand=True).save(p, exif=exif)
    return str(p)


def add_black_square(bgr, size):
    out = bgr.copy()
    out[40:40 + size, 40:40 + size] = 0
    return out


@pytest.mark.parametrize("kw", [dict(angle=8), dict(perspective=.08), dict(brightness=.5),
                                dict(gradient=.5)])
def test_locates_markers_after_distortion(kw):
    assert markers_dark(locate(photograph(render_sheet(), **kw)))


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_upside_down_or_sideways_is_corrected(angle):
    w = locate(photograph(render_sheet(), angle=angle))
    x, y, bw, bh = ORIENTATION_BAR
    assert w[y + bh // 2, x + bw // 2] < 90


def test_exif_rotation_applied(tmp_path):
    p = save_jpeg_with_exif_orientation(tmp_path, render_sheet(), 6)
    img = load_image(p)
    assert img.shape[0] > img.shape[1]


def test_distractor_black_square_is_not_a_marker():
    assert markers_dark(locate(add_black_square(photograph(render_sheet()), 70)))


@pytest.mark.parametrize("seed", range(8))
def test_strong_perspective_many_seeds(seed):
    assert markers_dark(locate(photograph(render_sheet(), perspective=.08, seed=seed)))


def test_dark_background_never_returns_wrong_warp():
    try:
        w = locate(photograph(render_sheet(), background=30))
    except SheetUnreadable:
        return
    assert markers_dark(w)


def test_no_sheet_raises():
    with pytest.raises(SheetUnreadable):
        locate(np.full((1000, 800, 3), 220, np.uint8))


def test_load_image_rejects_bad_file(tmp_path):
    p = tmp_path / "hong.jpg"
    p.write_bytes(b"not an image")
    with pytest.raises(SheetUnreadable):
        load_image(str(p))
