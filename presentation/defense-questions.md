# Chuẩn bị vấn đáp: Hệ thống chấm bài trắc nghiệm bằng xử lý ảnh

Mỗi câu trả lời ngắn gọn, nêu cả nguyên lý, đặc trưng, thứ cần phát hiện và hàm dùng. Số liệu lấy từ code trong `src/` và slide. Hàm có dấu `_` ở đầu là hàm nội bộ của dự án, còn lại (`cv2.*`, `np.*`) là hộp đen của thư viện.

## A. Tổng quan

**1. Bài toán là gì? Đầu vào, đầu ra?**
Giáo viên chụp ảnh phiếu trả lời bằng điện thoại, đưa vào cùng file đáp án CSV (`cau,dap_an`, tối đa 40 câu). Hệ thống trả bảng điểm CSV: mã học sinh, số câu đúng, điểm thang 10, trạng thái (“Đã chấm” hoặc “Cần xem lại”) và ghi chú, kèm ảnh vẽ vòng xanh/đỏ để kiểm tra bằng mắt.

**2. Chuỗi xử lý gồm những bước nào?**
8 bước: (1) xám + Gauss, (2) ngưỡng thích nghi, (3) tìm 4 ô định vị, (4) biến đổi phối cảnh, (5) bù giấy cong, (6) khử ánh sáng, (7) đọc ô tô, (8) chấm điểm. Bước 1–4 nằm trong `omr_locate.py`, bước 5–7 trong `omr_read.py`, bước 8 trong `omr_grade.py`.

**3. Vì sao tự thiết kế phiếu mà không dùng phiếu có sẵn?**
Vì phiếu do ta sinh ra nên toạ độ từng ô đã biết trước (`omr_layout.py`, dùng chung cho vẽ và đọc). Sau khi nắn phiếu về khung chuẩn 1654 × 2339 px, ta đọc thẳng tại toạ độ đó thay vì phải dò từng ô trên ảnh.

**4. Nguyên tắc thiết kế quan trọng nhất?**
Đọc không chắc chắn thì không cho điểm. Chấm sai một bài tệ hơn nhiều so với việc bắt giáo viên xem lại một bài. Mọi ngưỡng đặt theo hướng này, và chỉ số cần tối ưu là số bài chấm sai bằng 0.

**5. Có dùng học máy / học sâu không?**
Không. Toàn bộ là xử lý ảnh cổ điển: ngưỡng, hình thái học, contour, biến đổi hình học, khớp mẫu. Lý do: phiếu có cấu trúc cố định nên không cần học; cách này giải thích được từng bước và không cần dữ liệu huấn luyện.

## B. Bước 1–2: Tiền xử lý và phân ngưỡng

**6. Tại sao chuyển ảnh xám? Tại sao lọc Gauss?**
Hệ thống chỉ cần biết điểm nào tối hay sáng (mực so với giấy), màu không thêm thông tin, bỏ màu giảm 3 lần dữ liệu. Công thức: xám = 0,299R + 0,587G + 0,114B. Gauss 5×5 thay mỗi điểm bằng trung bình có trọng số của lân cận, làm mịn nhiễu hạt và nhiễu JPEG để contour không bị răng cưa. Hàm: `cv2.cvtColor`, `cv2.GaussianBlur(gray, (5,5), 0)`.

**7. Ngưỡng thích nghi hoạt động thế nào? Tại sao không dùng Otsu hay ngưỡng cố định?**
Mỗi điểm có ngưỡng riêng T(x,y) = trung bình Gauss của 101×101 điểm quanh nó trừ C = 10; điểm tối hơn T thì thành 255 (mực). Otsu và ngưỡng cố định dùng một ngưỡng chung cho cả ảnh, nên hỏng khi ảnh có chỗ sáng chỗ tối (ảnh mẫu tối dần sang phải). Ngưỡng thích nghi chỉ hỏi “điểm này tối hơn xung quanh không”. Hàm: `cv2.adaptiveThreshold(..., ADAPTIVE_THRESH_GAUSSIAN_C, THRESH_BINARY_INV, 101, 10)`.

**8. Vì sao block size là 101, C là 10?**
Block phải lớn hơn ô định vị (~60 px trong ảnh đã thu): nếu nhỏ hơn thì giữa ô đặc, trung bình lân cận cũng là đen, ô sẽ “biến mất”. C = 10 trừ đi để giấy phẳng, nhiễu nhẹ không bị coi là mực. Hai giá trị này chọn bằng thử trên ảnh mô phỏng, chưa tối ưu trên ảnh thật.

**9. `THRESH_BINARY_INV` để làm gì?**
Đảo để nét đen thành 255 (trắng), vì `findContours` coi vùng trắng là vật thể.

## C. Bước 3: Tìm 4 ô định vị

**10. Làm sao máy biết đâu là ô định vị trong 743 contour?**
Lọc nhiều lớp trong `_candidates`: (a) diện tích đủ lớn nhưng không quá 2% ảnh; (b) `cv2.approxPolyDP` với sai số 6% chu vi phải ra đúng 4 đỉnh và lồi (loại chữ cái, vòng tròn); (c) `cv2.minAreaRect` cho tỉ lệ cạnh 0,5–2 (chịu được xoay); (d) độ đặc = diện tích / diện tích bao lồi ≥ 0,9; (e) `_ink_on_paper`: trung vị xám trong contour < 0,3 × trung vị dải giấy quanh nó (loại phím bàn phím, vật tối trên nền tối). Còn tối đa 12 ứng viên.

**11. Ô đã tô đen cũng vuông và đặc. Sao không nhầm?**
Đúng, chúng vào danh sách 12 ứng viên (thấy các vòng vàng trên slide). Bước chọn bộ 4 (`find_markers`) loại chúng: bộ 4 phải tạo tứ giác lồi có tỉ lệ đúng phiếu A4 (cạnh dọc/ngang ≈ 1,46, sai số 35%), 4 diện tích chênh < 2 lần, hai cạnh đối chênh < 1,5 lần, và có thanh đen định hướng ở mép trên.

**12. Có bao nhiêu tổ hợp được thử? Có chậm không?**
C(12,4) = 495 tổ hợp, mỗi tổ hợp chỉ vài phép tính hình học, nên không đáng kể. Giới hạn 12 ứng viên chính là để số tổ hợp không bùng nổ.

**13. Ảnh có hai phiếu, hoặc thiếu ô thì sao?**
Thiếu ô: không có bộ hợp lệ, báo “Không tìm thấy 4 ô định vị”. Hai bộ hợp lệ nằm rời nhau: báo “Ảnh có nhiều hơn một phiếu”. Bài đó là “Cần xem lại”, các bài khác vẫn được chấm.

**14. Thanh đen ở mép trên để làm gì?**
Bốn ô định vị giống hệt nhau nên không phân biệt được phiếu có bị ngược đầu không. Thanh đen chỉ có ở mép trên: sau khi nắn, so độ tối dải mép trên với ảnh lật 180°, bên nào tối hơn là mép trên (`fix_orientation`). Hai bên gần bằng nhau thì báo lỗi, không đoán.

## D. Bước 4–5: Hình học

**15. Biến đổi phối cảnh (homography) là gì?**
Ma trận 3×3 (8 ẩn, vì định nghĩa sai khác một hệ số tỉ lệ) ánh xạ mặt phẳng này sang mặt phẳng khác khi chụp nghiêng. Giải từ 4 cặp điểm tương ứng: 4 góc thấy trong ảnh → 4 tâm chuẩn trong `MARKER_CENTERS`. 4 cặp là số tối thiểu (mỗi cặp cho 2 phương trình, đủ 8), nên thiếu một ô định vị là không nắn được. Hàm: `cv2.getPerspectiveTransform`, `cv2.warpPerspective` (nội suy song tuyến tính).

**16. Nếu đã nắn phối cảnh rồi, sao còn cần bù giấy cong?**
Phối cảnh chỉ đúng với mặt phẳng. Giấy cầm tay bị cong làm các ô ở giữa lệch khỏi vị trí chuẩn vài chục pixel, trong khi bốn góc vẫn đúng. Ô cách nhau ~70 px nên lệch như vậy có thể đọc nhầm sang ô bên cạnh.

**17. Bù giấy cong làm thế nào?**
(1) Khớp mẫu vòng tròn viền ô trên cả phiếu bằng `cv2.matchTemplate` (TM_CCORR, mẫu có vòng dương ở viền in và vòng âm ở giấy ngoài), được bản đồ điểm `ring_score`. (2) Lấy cực đại cục bộ (`cv2.dilate` 21×21) làm vị trí viền thật. (3) Ghép từng ô chuẩn với đỉnh gần nhất (chỉ nhận nếu đỉnh gần nhất rõ hơn đỉnh thứ hai ≥ 1,5 lần), thu được vector lệch. (4) Hồi quy đa thức hai biến bậc 1 → 2 → 3 bằng bình phương tối thiểu (`np.linalg.lstsq`), ghim 4 ô định vị có lệch 0. (5) Nội suy Gauss (σ = 60 px) phần dư cho chỗ giấy gập. (6) Tính trường lệch trên lưới 16 px rồi `cv2.remap`.

**18. Vì sao dùng đa thức bậc thấp trước?**
Bậc thấp mô tả hình dạng tổng thể, ít bậc tự do nên khó “học vẹt” vết bẩn hay chữ in nhầm là ô. Phần còn lại mới để nội suy cục bộ xử lý.

**19. Khi nào bước này từ chối sửa?**
Ghép được dưới 50% ô, hoặc độ lệch ước lượng > 80 px (không thể là giấy cong nhẹ, nhiều khả năng ghép nhầm). Khi đó giữ nguyên ảnh, và `check_quality` ở bước đọc sẽ bắt nếu lưới thật sự lệch.

## E. Bước 6–7: Khử sáng và đọc ô

**20. Khử ánh sáng bằng phép đóng hình thái hoạt động ra sao?**
Closing = giãn nở rồi co lại. Giãn nở (lấy max) xoá các vết tối hẹp hơn nhân (nét mực, chữ, vòng ô), co lại trả hình dạng vùng sáng, kết quả là “nền giấy” không có mực nhưng vẫn giữ chỗ sáng tối. Nhân elip 61 px lớn hơn đường kính ô (40 px) nên xoá hết mực. Rồi chia ảnh cho nền: giấy ≈ 1, mực ≈ 0. Hàm: `cv2.morphologyEx(..., MORPH_CLOSE, ellipse 61×61)`.

**21. Vì sao chia mà không trừ?**
Ánh sáng là hệ số nhân với độ phản xạ của giấy (ảnh = ánh sáng × phản xạ), nên chia cho nền triệt tiêu ánh sáng. Trừ chỉ đúng với nhiễu cộng.

**22. Một ô được xác định “đã tô” thế nào?**
Sau căn tâm theo viền in (`_snap`, tìm cực đại `cv2.minMaxLoc` trong ±12 px), lấy lõi ô bán kính 14 px (0,7R, bỏ viền in) và đếm tỉ lệ điểm có độ sáng chuẩn hoá < 0,75. Dưới 0,25 là trống, trên 0,75 là đã tô, ở giữa là không chắc (`classify_ratio`).

**23. Đặc trưng nào dùng ngoài tỉ lệ điểm đen?**
Độ đậm trung bình (nét tô nhạt), mức tối của giấy quanh ô (bóng đổ, vật đè), phần trong viền (vết tẩy chưa sạch), hai ô cùng tô phải đậm như nhau, ô trống phải thấy được viền in (không bị lóa), và độ nét của ảnh. Vi phạm cái nào thì ô đó là “không chắc”.

**24. Mã học sinh đọc thế nào?**
Cùng cơ chế với câu hỏi: 6 cột, mỗi cột 10 ô (0–9), mỗi cột phải tô đúng một ô. Thiếu hoặc nhiều ô không rõ ràng thì “Cần xem lại”.

## F. Bước 8 và quy tắc chấm

**25. Điểm tính thế nào?**
Một câu đúng khi học sinh tô đúng một ô và ô đó là đáp án. Điểm = số câu đúng / số câu trong file đáp án × 10, làm tròn 2 chữ số. Chia cho số câu trong đáp án, không cố định 40, nên đề 20 câu vẫn ra thang 10.

**26. Phân biệt “học sinh sai” và “máy không chắc” thế nào?**
Bỏ trống hoặc tô nhiều ô rõ ràng là quyết định của học sinh: chấm bình thường, câu đó 0 điểm, ghi chú. Còn ô nhạt, tẩy dở, bóng đổ, ảnh mờ là máy không chắc đọc đúng: cả bài “Cần xem lại”, không cho điểm.

**27. Một ảnh hỏng có làm hỏng cả lớp không?**
Không. `grade_batch` xử lý từng ảnh độc lập; lỗi một ảnh chỉ làm riêng bài đó thành “Cần xem lại”.

## G. Đánh giá, hạn chế

**28. Độ chính xác bao nhiêu? Kiểm thử thế nào?**
Trên ảnh mô phỏng (`tests/synth.py`, seed cố định): 11 kịch bản (sạch, xoay, phối cảnh, tối, ánh sáng lệch, mờ, vết tẩy...) × 30 ảnh = 330 ảnh, không bài nào chấm sai. 3 kịch bản bắt buộc phải bị chặn (nét nhạt, nét nhạt + mờ, tẩy dở) chặn đủ 90/90. README ghi đã thử 900 ảnh; 330 là lần chạy lại để kiểm chứng. Chạy lại bằng `tools/evaluate.py`.

**29. Kết quả đó có đáng tin không? Điểm yếu?**
Chưa đủ. Toàn bộ là ảnh mô phỏng; chưa thử phiếu in thật chụp bằng điện thoại. Ngưỡng đọc ô mới chỉ chỉnh trên ảnh mô phỏng, với bút chì nhạt hoặc giấy xám kết quả có thể khác. Nếu ngưỡng quá chặt thì tỉ lệ bài “Cần xem lại” sẽ cao (đây là cái giá của nguyên tắc an toàn). Cần thử 10–20 phiếu thật và chỉnh ngưỡng trong `omr_read.py`.

**30. Còn hạn chế nào khác về phần mềm?**
`main.ipynb` đã chạy hết trên máy (trừ ô mở giao diện), chưa chạy trên Colab thật. `main.m` (MATLAB) chưa từng chạy trên MATLAB hoặc Octave. Hệ thống không đọc được ảnh nếu không thấy đủ 4 ô định vị.

**31. Ảnh mẫu trong slide có phải ảnh chụp thật?**
Không, là ảnh mô phỏng do `tests/synth.py` sinh (xoay, nghiêng, nền chuyển sáng tối). Nêu rõ điều này khi demo.

**32. Nếu có thêm thời gian, cải tiến gì?**
Thu 10–20 phiếu in thật với nhiều loại bút và giấy để chỉnh ngưỡng; đo tỉ lệ “Cần xem lại” trên ảnh thật; chạy `main.m` trên Octave để đối chiếu với bản Python; có thể cho giáo viên sửa tay các bài “Cần xem lại” ngay trên giao diện.

## H. Triển khai

**33. Ba cách chạy khác nhau thế nào?**
`main.ipynb` (Google Colab, Gradio, tự chứa toàn bộ code, sinh từ `src/` bằng `tools/build_notebook.py` để không lệch code), `main.py` (Python trên máy, Gradio cổng 7860), `main.m` (MATLAB cơ bản, không cần Image Processing Toolbox, in bảng điểm và ghi `scores.csv`).

**34. File CSV xuất ra mở bằng Excel có lỗi tiếng Việt không?**
Không, ghi bằng `utf-8-sig` (có BOM) để Excel đọc UTF-8. Lưu ý Excel có thể ẩn số 0 đầu mã học sinh khi hiển thị, nhưng dữ liệu trong file vẫn đúng.

## I. Câu hỏi bẫy hay gặp

**35. Sao không dùng Hough để tìm vòng tròn?**
Hough vòng tròn nhạy với tham số và cho nhiều dương tính giả trên phiếu có 240+ ô, chữ và số. Vì toạ độ ô đã biết sau khi nắn, chỉ cần căn tâm trong ±12 px, rẻ và ổn định hơn. Khớp mẫu viền đã dùng ở bước bù cong.

**36. Sao không dùng OCR / mã QR cho mã học sinh?**
Mã học sinh tô bằng 6 cột ô tròn, cùng cơ chế đọc với câu hỏi, không cần thêm thành phần. OCR chữ viết tay kém tin cậy hơn nhiều, trái với nguyên tắc “không chắc thì không chấm”. Mã QR là hướng mở rộng hợp lý nhưng phải in sẵn từng phiếu.

**37. Điểm nào trong dự án là tự làm, điểm nào là thư viện?**
Hộp đen của OpenCV/NumPy: chuyển xám, Gauss, ngưỡng thích nghi, `findContours`, `approxPolyDP`, `minAreaRect`, homography, `matchTemplate`, `morphologyEx`, `remap`, `lstsq`. Phần tự thiết kế: bộ lọc ứng viên ô định vị và chọn bộ 4 theo tỉ lệ phiếu, thanh định hướng, bù giấy cong (ghép + đa thức + nội suy Gauss), khử sáng + căn tâm + phân loại ô theo nhiều dấu hiệu, và quy tắc từ chối chấm.

**38. Nếu ảnh chụp thiếu một góc phiếu?**
Không tìm đủ 4 ô nên bài đó “Cần xem lại” với lý do “Không tìm thấy 4 ô định vị”. Không có cách nắn đáng tin với 3 điểm, vì homography cần 4 cặp.
