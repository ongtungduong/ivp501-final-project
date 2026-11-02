import cv2
import numpy as np

from omr_layout import question_bubble
from omr_read import classify_ratio, read_sheet
from omr_sheet import render_sheet
from synth import add_glare, fill_bubble, fill_sheet, photograph, shift_content
import pytest


@pytest.fixture
def read(tmp_path):
    def _read(img, **kw):
        p = tmp_path / "a.png"
        cv2.imwrite(str(p), photograph(img, **kw))
        return read_sheet(str(p))
    return _read


def test_classify_ratio_bands():
    assert [classify_ratio(r) for r in (0.1, 0.4, 0.9)] == ["blank", "uncertain", "filled"]


def test_clean_sheet_reads_exactly(read):
    answers = {q: "ABCD"[q % 4] for q in range(1, 41)}
    r = read(fill_sheet(render_sheet(), "001234", answers), angle=4, perspective=.04)
    assert r.student_id == "001234" and not r.problems and not r.uncertain
    assert r.marks == {q: [answers[q]] for q in answers}


def test_blank_and_double_marks(read):
    img = fill_sheet(render_sheet(), "123456", {1: "A"})
    fill_bubble(img, question_bubble(2, "A"))
    fill_bubble(img, question_bubble(2, "C"))
    r = read(img)
    assert r.marks[1] == ["A"] and r.marks[2] == ["A", "C"] and r.marks[3] == []


def test_faint_mark_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(5, "B"), darkness=170, coverage=.5)
    assert 5 in read(img).uncertain


def test_light_full_fill_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(6, "A"), darkness=170)
    assert 6 in read(img).uncertain


def test_badly_erased_residue_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(7, "A"), darkness=228)
    assert 7 in read(img).uncertain


def test_clean_erase_reads_blank(read):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(7, "A"), darkness=246)
    r = read(img)
    assert r.marks[7] == [] and 7 not in r.uncertain


@pytest.mark.parametrize("darkness", [180, 195, 210, 225])
def test_light_solid_fill_is_never_certain_blank(read, darkness):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(5, "B"), darkness=darkness)
    assert 5 in read(img).uncertain


@pytest.mark.parametrize("coverage", [.15, .3, .45, .6])
def test_partial_fill_is_never_certain_blank(read, coverage):
    img = fill_sheet(render_sheet(), "123456", {})
    fill_bubble(img, question_bubble(5, "B"), coverage=coverage)
    assert 5 in read(img).uncertain


def test_center_dot_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {})
    cv2.circle(img, question_bubble(5, "B"), 6, 30, -1)
    assert 5 in read(img).uncertain


def test_glare_spot_on_filled_bubble_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {5: "B"})
    cv2.circle(img, question_bubble(5, "B"), 14, 255, -1)
    assert 5 in read(img).uncertain


@pytest.mark.parametrize("width,level", [(20, .6), (40, .5), (50, .6)])
def test_vertical_shadow_is_not_read_as_marks(read, width, level):
    img = fill_sheet(render_sheet(), "123456", {q: "A" for q in range(1, 41)})
    x = question_bubble(1, "C")[0]
    img[:, x - width // 2:x + width // 2] = (img[:, x - width // 2:x + width // 2] * level).astype(img.dtype)
    r = read(img)
    assert r.problems or set(range(1, 11)) <= set(r.uncertain)


def test_horizontal_shadow_is_not_read_as_marks(read):
    img = fill_sheet(render_sheet(), "123456", {q: "A" for q in range(1, 41)})
    y = question_bubble(3, "A")[1]
    img[y - 20:y + 20] = (img[y - 20:y + 20] * .6).astype(img.dtype)
    r = read(img)
    assert r.problems or {3, 13, 23, 33} <= set(r.uncertain)


def test_dark_residue_beside_real_answer_is_uncertain(read):
    img = fill_sheet(render_sheet(), "123456", {9: "A"})
    fill_bubble(img, question_bubble(9, "C"), darkness=150)
    assert 9 in read(img).uncertain


def test_equally_dark_double_mark_stays_double(read):
    img = fill_sheet(render_sheet(), "123456", {9: "A"})
    fill_bubble(img, question_bubble(9, "C"))
    r = read(img)
    assert r.marks[9] == ["A", "C"] and 9 not in r.uncertain


def test_grey_paper_dark_pencil_reads_correctly(read):
    img = (fill_sheet(render_sheet(), "123456", {1: "A"}).astype("float32") * .75).astype("uint8")
    r = read(img)
    assert r.marks[1] == ["A"] and not r.uncertain and not r.problems


def test_two_sheets_in_one_photo_go_to_review(tmp_path):
    a = fill_sheet(render_sheet(), "111111", {1: "A"})
    b = fill_sheet(render_sheet(), "222222", {1: "B"})
    p = tmp_path / "two.png"
    cv2.imwrite(str(p), np.hstack([a, np.full((a.shape[0], 60), 255, a.dtype), b]))
    r = read_sheet(str(p))
    assert r.problems and r.student_id is None


def test_extreme_shape_image_does_not_raise(tmp_path):
    p = tmp_path / "dai.png"
    cv2.imwrite(str(p), np.full((1, 20000), 200, np.uint8))
    assert read_sheet(str(p)).problems


def test_incomplete_id_is_reported(read):
    r = read(fill_sheet(render_sheet(), "123", {}))
    assert r.student_id is None and r.id_problems


def test_blur_and_glare_reported(read):
    assert read(render_sheet(), blur=31).problems
    assert read(add_glare(render_sheet())).problems


def test_misaligned_grid_reported(read):
    assert read(shift_content(render_sheet(), dx=25)).problems


def test_dim_uneven_light_reads_correctly(read):
    img = fill_sheet(render_sheet(), "987654", {1: "D", 40: "A"})
    r = read(img, brightness=.5, gradient=.5)
    assert r.student_id == "987654" and r.marks[1] == ["D"] and r.marks[40] == ["A"]
    assert not r.problems and not r.uncertain


def test_unreadable_files_do_not_raise(tmp_path):
    p = tmp_path / "hong.jpg"
    p.write_bytes(b"not an image")
    assert read_sheet(str(p)).problems


def test_steps_available(read):
    assert {"goc", "xam", "nhi_phan", "dinh_vi", "nan_phoi_canh"} <= set(read(render_sheet()).steps)
