# Các hàm quan trọng trong từng bước

Mỗi hàm gồm: **làm gì**, **nhận gì / trả gì**, **tham số trong dự án và lý do chọn**. Hàm `cv2.*` và `np.*` là của thư viện (OpenCV, NumPy). Hàm có dấu `_` ở đầu là hàm nội bộ do dự án tự viết.

Luồng tổng quát: `read_sheet()` (`omr_read.py`) gọi lần lượt bước 1→7, rồi `grade_reading()` (`omr_grade.py`) thực hiện bước 8.

---

## Bước 1: Ảnh xám + lọc Gauss (`omr_locate.preprocess`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.cvtColor(bgr, COLOR_BGR2GRAY)` | Đổi ảnh màu 3 kênh sang 1 kênh mức xám: 0,299R + 0,587G + 0,114B. | Màu không thêm thông tin cho bài toán “mực đen trên giấy trắng”, bỏ màu giảm 3 lần dữ liệu. |
| `cv2.GaussianBlur(gray, (5,5), 0)` | Tích chập với nhân Gauss: mỗi điểm thành trung bình có trọng số của 5×5 điểm quanh nó. | Nhân 5×5, σ = 0 (OpenCV tự tính từ kích thước nhân). Làm mịn nhiễu hạt và nhiễu JPEG để contour ở bước 3 không bị răng cưa. |
| `load_image` (tự viết) | Đọc ảnh, xoay theo EXIF của điện thoại, thu về tối đa 3000 px cạnh dài. | Ảnh 12 MP làm chậm, 3000 px vẫn đủ nét để thấy ô định vị. |

## Bước 2: Ngưỡng thích nghi (`omr_locate.preprocess`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.adaptiveThreshold(blur, 255, ADAPTIVE_THRESH_GAUSSIAN_C, THRESH_BINARY_INV, 101, 10)` | Tính ngưỡng riêng cho từng điểm: T(x,y) = trung bình Gauss của vùng 101×101 quanh nó trừ C. Điểm tối hơn T thành 255, ngược lại 0. | **Block 101**: lớn hơn ô định vị (~60 px) để trung bình lân cận chủ yếu là giấy. **C = 10**: giấy phẳng và nhiễu nhẹ không bị coi là mực. **`BINARY_INV`**: nét đen thành 255 để `findContours` coi là vật thể. Dùng thay Otsu vì ảnh chụp sáng tối không đều. |

## Bước 3: Tìm 4 ô định vị (`omr_locate._candidates`, `find_markers`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.findContours(binary, RETR_LIST, CHAIN_APPROX_SIMPLE)` | Tìm đường biên của các vùng trắng liên thông; trả danh sách contour. | `RETR_LIST`: lấy mọi contour, không cần quan hệ lồng nhau (ô định vị là khối đặc). `CHAIN_APPROX_SIMPLE`: nén các đoạn thẳng, chỉ giữ đỉnh. |
| `cv2.contourArea` | Diện tích contour. | Loại nhiễu nhỏ (dưới (cạnh dài ảnh / 200)²) và vật quá lớn (trên 2% ảnh). |
| `cv2.approxPolyDP(c, 0.06 × chu vi, True)` | Xấp xỉ contour bằng đa giác ít đỉnh nhất trong sai số cho phép. | Sai số 6% chu vi: ô vuông ra đúng 4 đỉnh, chữ cái và vòng tròn thì không. Kết hợp `cv2.isContourConvex` để chỉ nhận tứ giác lồi. |
| `cv2.minAreaRect(c)` | Hộp chữ nhật nhỏ nhất (có xoay) bao contour: trả tâm, (rộng, cao), góc. | Lấy tỉ lệ rộng/cao trong 0,5–2 (gần vuông), chịu được phiếu xoay. Tâm hộp dùng làm toạ độ ô. |
| `cv2.convexHull` | Bao lồi của contour. | Độ đặc = diện tích / diện tích bao lồi ≥ 0,9; tính theo bao lồi vì phối cảnh mạnh làm ô vuông thành hình bình hành. |
| `_ink_on_paper` (tự viết) | So trung vị xám trong contour với dải giấy bao quanh (tạo bằng `cv2.dilate`). | Trung vị < 0,3 × giấy thì mới là “mực trên giấy”. Loại phím bàn phím, vật tối trên nền tối. |
| `itertools.combinations(cands, 4)` + `_rect_error` + `_bar_present` (tự viết) | Thử mọi bộ 4 trong tối đa 12 ứng viên (495 bộ), giữ bộ tạo tứ giác lồi đúng tỉ lệ phiếu và có thanh định hướng. | Tỉ lệ cạnh dọc/ngang ≈ 1,46 (sai số 35%), diện tích 4 ô chênh < 2 lần, cạnh đối chênh < 1,5 lần. Hai bộ hợp lệ rời nhau → “có nhiều hơn một phiếu”. |
| `_order` (tự viết) | Sắp 4 điểm theo vòng quanh tâm bằng `np.arctan2`. | Không phụ thuộc phiếu xoay thế nào. Chưa biết trên/dưới, việc đó của bước 4. |

## Bước 4: Biến đổi phối cảnh (`omr_locate.warp`, `fix_orientation`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.getPerspectiveTransform(src, dst)` | Giải ma trận đồng nhất 3×3 (8 ẩn) từ 4 cặp điểm tương ứng. | `src` = 4 góc tìm được trong ảnh, `dst` = `MARKER_CENTERS` (4 tâm chuẩn). 4 cặp là tối thiểu, nên thiếu một ô là không nắn được. |
| `cv2.warpPerspective(gray, m, (1654, 2339), INTER_LINEAR)` | Áp ma trận lên mọi điểm ảnh, nội suy song tuyến tính. | Khung chuẩn 1654 × 2339 px (A4, 200 DPI). Sau bước này mọi ô tròn ở toạ độ đã biết trong `omr_layout.py`. |
| `fix_orientation` + `_bar_level` (tự viết) và `cv2.rotate(…, ROTATE_180)` | So độ tối dải thanh định hướng ở mép trên với ảnh lật 180°; bên nào tối hơn là mép trên. | Hai bên gần bằng nhau (< 0,6 lần chênh) thì báo lỗi, không đoán chiều. |

## Bước 5: Bù giấy cong (`omr_read.unbend`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.matchTemplate(1 - light, _RING_TEMPLATE, TM_CCORR)` (`ring_score`) | Trượt mẫu vòng tròn khắp phiếu, cho bản đồ điểm khớp viền ô. | Mẫu có vòng dương (viền in, dày 5 px) và vòng âm (giấy ngoài), tổng chuẩn hoá = 1, nên điểm = độ tối viền − độ tối giấy quanh. Ô đã tô vẫn khớp vì viền in vẫn còn. Không qua nhị phân nên chịu được ảnh mờ. |
| `cv2.dilate` 21×21 (trong `_ring_peaks`) | Dùng làm bộ lọc cực đại: điểm bằng max của cửa sổ 21×21 và dương là đỉnh. | Lấy vị trí viền ô thật; giữ tối đa 2 × số ô đỉnh mạnh nhất. |
| `_bend_field` > `match` (tự viết) | Ghép từng ô chuẩn với đỉnh gần nhất, thu vector lệch. | Chỉ nhận nếu đỉnh gần nhất cách < bán kính ghép và rõ hơn đỉnh thứ hai ≥ 1,5 lần; ghép được < 50% ô thì bỏ cuộc. |
| `np.linalg.lstsq(_poly(src, deg), dst)` | Bình phương tối thiểu: tìm hệ số đa thức hai biến sao cho độ lệch dự đoán ≈ độ lệch đo được. | Bậc 1 → 2 → 3, bán kính ghép 45 → 25 → 15 px (từ thô đến mịn). Đa thức bậc thấp khó “học vẹt” vết bẩn. 4 ô định vị được ghim lệch 0 (nhân trọng số 5). |
| `_smooth` (tự viết) | Nội suy Gauss (σ = 60 px) phần dư sau đa thức. | Bán kính ghép 30 → 20 → 12 → 8 px; xử lý chỗ giấy gập mà đa thức không bắt được. |
| `cv2.remap(warped, xs + dx, ys + dy, INTER_LINEAR, BORDER_REPLICATE)` | Lấy điểm ảnh từ vị trí đã dịch, kéo ô thật về đúng ô chuẩn. | Trường lệch tính trên lưới thưa 16 px rồi nội suy tuyến tính ra từng điểm cho nhanh. Lệch > 80 px thì không tin, giữ nguyên ảnh. |

## Bước 6: Khử ánh sáng (`omr_read._normalize_light`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `cv2.getStructuringElement(MORPH_ELLIPSE, (61, 61))` | Tạo nhân hình elip. | 61 px lớn hơn đường kính ô (40 px) để xoá hết nét mực, nhưng vẫn đủ nhỏ để theo kịp bóng đổ đổi chậm. |
| `cv2.morphologyEx(blurred, MORPH_CLOSE, kernel)` | Đóng = giãn nở (lấy max) rồi co lại. Giãn nở xoá vết tối hẹp hơn nhân (mực, chữ, vòng ô). | Kết quả là “nền giấy” không có mực nhưng vẫn giữ chỗ sáng tối. |
| `blurred / np.maximum(background, 1)` | Chia ảnh cho nền. | Ánh sáng là hệ số nhân với phản xạ giấy nên chia sẽ triệt tiêu: giấy ≈ 1, mực ≈ 0. `max(…, 1)` tránh chia 0. |

## Bước 7: Đọc ô tô (`omr_read._snap`, `_bubble_state`, `classify_ratio`)

| Hàm | Làm gì | Tham số và lý do |
|---|---|---|
| `_snap` + `cv2.minMaxLoc` | Trong cửa sổ ±12 px quanh tâm lý thuyết, tìm điểm khớp viền cao nhất trên `ring_score`, căn lại tâm ô. | 12 px nhỏ hơn nhiều so với khoảng cách hai ô gần nhất (~70 px) nên không nhảy sang ô bên cạnh. Bù sai số phối cảnh và giấy cong còn sót. |
| Mặt nạ `_CORE`, `_INNER`, `_OUTSIDE` (NumPy) | Chia vùng quanh ô: lõi (bán kính 14 px), trong viền, vành giấy ngoài. | Lõi bỏ viền in để viền không bị tính là mực; vành ngoài phát hiện bóng đổ hoặc vật đè. |
| `classify_ratio(ratio)` | Tỉ lệ điểm đen trong lõi (điểm có độ sáng chuẩn hoá < 0,75) → `blank` / `filled` / `uncertain`. | < 0,25 trống; > 0,75 đã tô; ở giữa là không chắc. Không có nhánh “đoán”. |
| `_bubble_state` | Gộp tỉ lệ đen với các kiểm tra phụ. | Ô “đã tô” còn phải đủ đậm (trung bình ≤ 0,65). Ô “trống” còn phải sạch: không có vết tay đỏ, điểm mực đậm, nét nhạt rộng (`cv2.blur` 7×7 để bỏ hạt nhiễu). Vi phạm → `uncertain`. |
| `_read_id` | Đọc 6 cột × 10 ô của mã học sinh. | Mỗi cột phải có đúng một ô tô và không ô nào không chắc, nếu không thì không đoán, mã học sinh là “Cần xem lại”. |
| `check_quality` | Kiểm tra cả ảnh: tỉ lệ ô không thấy viền in, độ nét. | > 5% ô mất viền → ảnh lóa hoặc lưới lệch; độ nét < 0,07 → quá mờ. |

## Bước 8: Chấm điểm (`omr_grade`)

| Hàm | Làm gì | Ghi chú |
|---|---|---|
| `load_answer_key` | Đọc file đáp án CSV, kiểm tra định dạng. | Chấp nhận dấu `;`, chữ thường, cột trống cuối. Số câu phải liên tục từ 1 và tối đa 40. |
| `grade_reading` | Quyết định điểm hoặc “Cần xem lại” cho một bài. | Có bất kỳ ghi chú lỗi đọc nào → “Cần xem lại”, không cho điểm. Còn lại: đúng khi `marks[q] == [đáp án]` (tô đúng một ô và là đáp án). Điểm = đúng / số câu trong đáp án × 10, làm tròn 2 chữ số. Bỏ trống hoặc tô nhiều ô chỉ ghi chú, câu đó 0 điểm. |
| `_annotate` + `cv2.circle` | Vẽ vòng xanh ở đáp án đúng, vòng đỏ ở ô học sinh tô sai. | Vẽ cả khi “Cần xem lại” để giáo viên thấy chỗ nghi ngờ. |
| `grade_batch` | Chấm nhiều ảnh, mỗi ảnh độc lập; ghi chú các bài trùng mã học sinh. | Một ảnh lỗi không làm hỏng cả lớp. |
| `write_csv` | Ghi bảng điểm. | Dùng `utf-8-sig` để Excel hiển thị đúng tiếng Việt. |

---

## Nếu bị hỏi “hàm nào là quan trọng nhất?”

1. `cv2.adaptiveThreshold`: nhờ nó phát hiện được ô định vị trong ảnh sáng tối không đều.
2. `cv2.getPerspectiveTransform` + `cv2.warpPerspective`: biến ảnh chụp thành khung chuẩn để đọc bằng toạ độ cố định.
3. `cv2.matchTemplate` (`ring_score`): vừa dùng để bù giấy cong (bước 5), vừa để căn tâm từng ô (bước 7).
4. `cv2.morphologyEx(MORPH_CLOSE)`: khử ánh sáng để một ngưỡng đọc ô dùng được cho mọi ảnh.
5. `classify_ratio` / `_bubble_state` và `grade_reading`: phần tự thiết kế quyết định “đã tô”, “không chắc” và quy tắc từ chối chấm.
