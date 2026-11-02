"""Toa do cua phieu tra loi, dung chung cho viec ve phieu va doc phieu."""

PAGE_W = 1654  # A4 o 200 DPI
PAGE_H = 2339
NUM_QUESTIONS = 40
CHOICES = "ABCD"
ID_DIGITS = 6
BUBBLE_RADIUS = 20
MARKER_SIZE = 60
MARKER_CENTERS = [(80, 80), (1574, 80), (1574, 2259), (80, 2259)]  # TL, TR, BR, BL
ORIENTATION_BAR = (677, 70, 300, 20)  # x, y, w, h: chi co o mep tren

_ID_X, _ID_Y, _ID_DX, _ID_DY = 1050, 260, 70, 62
_Q_X, _Q_Y, _Q_DX, _Q_DY = 250, 1000, 70, 110
_Q_COL_GAP = 350
_Q_PER_COL = 10


def question_bubble(q, choice):
    """Tam o tron cua cau q (1..40), lua chon choice (A..D)."""
    col, row = divmod(q - 1, _Q_PER_COL)
    return (_Q_X + col * _Q_COL_GAP + CHOICES.index(choice) * _Q_DX, _Q_Y + row * _Q_DY)


def id_bubble(pos, digit):
    """Tam o tron cua chu so thu pos (0..5) trong ma hoc sinh, gia tri digit (0..9)."""
    return (_ID_X + pos * _ID_DX, _ID_Y + digit * _ID_DY)
