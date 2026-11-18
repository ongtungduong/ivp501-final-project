"""Toa do cua phieu tra loi, dung chung cho viec ve phieu va doc phieu.

Y tuong cot loi cua he thong: phieu la bieu mau CO DINH. Neu dua duoc anh chup ve dung khung
PAGE_W x PAGE_H thi o tron cua cau q, lua chon c luon nam o mot toa do biet truoc, khong can
"tim" o tron. File nay la nguon su that duy nhat: omr_sheet.py (ve phieu) va omr_read.py (doc
phieu) cung goi question_bubble/id_bubble, nen phieu in ra va phieu doc vao khong the lech nhau.
Doi bo cuc chi can sua o day.

He toa do: goc tren-trai la (0, 0), x sang phai, y xuong duoi, don vi pixel.
"""

# A4 = 210 x 297 mm. O 200 DPI: 210/25.4*200 = 1654, 297/25.4*200 = 2339.
# 200 DPI du net de o tron (duong kinh 40 px) con ro sau khi nan, ma anh khong qua nang.
PAGE_W = 1654
PAGE_H = 2339
NUM_QUESTIONS = 40
CHOICES = "ABCD"
ID_DIGITS = 6
BUBBLE_RADIUS = 20  # ban kinh o tron in tren phieu (px); cac vung do trong omr_read.py tinh theo so nay
MARKER_SIZE = 60  # canh o vuong dinh vi (px)
# Tam 4 o dinh vi theo thu tu vong quanh: TL, TR, BR, BL. Cach mep 80 px de o khong bi cat
# khi chup lech. Thu tu nay la thu tu getPerspectiveTransform ghep cap diem (omr_locate.warp).
MARKER_CENTERS = [(80, 80), (1574, 80), (1574, 2259), (80, 2259)]
# x, y, w, h cua thanh den dinh huong. Chi co o mep TREN, khong doi xung: 4 o goc giong het nhau
# nen phieu quay 180 do nhin y het phieu thuong; thanh den la thu duy nhat phan biet duoc.
ORIENTATION_BAR = (677, 70, 300, 20)

# Luoi ma hoc sinh: 6 cot (moi chu so mot cot), moi cot 10 o ung voi 0..9 chay doc xuong.
_ID_X, _ID_Y, _ID_DX, _ID_DY = 1050, 260, 70, 62  # o dau tien, buoc ngang giua cac cot, buoc doc giua cac so
# Luoi cau hoi: 4 cot x 10 cau; trong moi cau, A..D xep ngang cach nhau _Q_DX.
_Q_X, _Q_Y, _Q_DX, _Q_DY = 250, 1000, 70, 110
_Q_COL_GAP = 350  # khoang cach giua hai cot cau (cau 1-10, 11-20, 21-30, 31-40)
_Q_PER_COL = 10


def question_bubble(q, choice):
    """Tam o tron cua cau q (1..40), lua chon choice (A..D)."""
    # divmod(q-1, 10): cau 1..10 -> cot 0, cau 11..20 -> cot 1, ... ; row la hang trong cot
    col, row = divmod(q - 1, _Q_PER_COL)
    return (_Q_X + col * _Q_COL_GAP + CHOICES.index(choice) * _Q_DX, _Q_Y + row * _Q_DY)


def id_bubble(pos, digit):
    """Tam o tron cua chu so thu pos (0..5) trong ma hoc sinh, gia tri digit (0..9)."""
    return (_ID_X + pos * _ID_DX, _ID_Y + digit * _ID_DY)
