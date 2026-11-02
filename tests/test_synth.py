from omr_layout import PAGE_H, question_bubble
from omr_sheet import render_sheet
from synth import fill_sheet, photograph


def test_fill_darkens_only_target_bubble():
    img = fill_sheet(render_sheet(), "001234", {1: "B"})
    x, y = question_bubble(1, "B")
    assert img[y, x] < 80
    x, y = question_bubble(1, "A")
    assert img[y, x] > 200


def test_photograph_is_deterministic_and_larger():
    src = render_sheet()
    a = photograph(src, angle=5, perspective=.05, seed=1)
    b = photograph(src, angle=5, perspective=.05, seed=1)
    assert a.ndim == 3 and (a == b).all() and a.shape[0] > PAGE_H
