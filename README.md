# Hệ thống chấm bài trắc nghiệm

Dự án cuối kỳ môn Xử lý ảnh và Video. Giáo viên chụp ảnh phiếu trả lời của học sinh, upload cùng file đáp án và nhận điểm của từng bài.

Dự án có ba cách chạy:

| Cách chạy | File | Giao diện |
|---|---|---|
| Google Colab | `main.ipynb` | Gradio |
| Python trên máy | `main.py` | Gradio |
| MATLAB | `main.m` | Dòng lệnh và hình vẽ |

## Quy trình sử dụng

1. In phiếu `templates/answer_sheet.pdf` (A4, 40 câu, lựa chọn A–D, mã học sinh 6 chữ số).
2. Học sinh tô bài bằng bút chì 2B hoặc bút mực tối màu.
3. Giáo viên chụp ảnh từng phiếu, thấy đủ 4 ô vuông đen ở góc.
4. Chuẩn bị file đáp án CSV.
5. Đưa file đáp án và ảnh bài làm vào hệ thống, rồi tải bảng điểm.

### File đáp án

File CSV có hai cột `cau,dap_an`, số câu liên tục từ 1 đến N (N tối đa 40). Hệ thống chỉ chấm N câu đầu.

```csv
cau,dap_an
1,A
2,C
3,B
```

Có thể lưu file từ Excel: dấu `;`, chữ thường và các cột trống ở cuối đều đọc được. Xem ví dụ tại `samples/sample_answer_key.csv`.

## Cách chạy

### Google Colab

1. Mở `main.ipynb` trên Colab.
2. Chọn *Runtime → Run all*.
3. Kéo xuống cuối notebook để dùng giao diện. Phiếu trắng và dữ liệu mẫu nằm trong thanh *Files* bên trái.

Notebook tự chứa toàn bộ code, không cần tải thêm file nào. Nếu giao diện không hiện, đổi `share=False` thành `share=True` ở ô cuối. Khi đó bất kỳ ai có link đều vào được, nên hãy cân nhắc vì ảnh bài làm chứa thông tin học sinh.

### Python trên máy

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Sau đó mở http://127.0.0.1:7860. Muốn đổi cổng thì thêm `--port 8000`.

### MATLAB

Chỉ dùng MATLAB cơ bản, không cần Image Processing Toolbox.

```matlab
main                                     % chấm dữ liệu mẫu trong samples/
main('dap_an.csv', {'a.jpg', 'b.jpg'})   % chấm bài của bạn
results = main('dap_an.csv', {'a.jpg'}, false)   % không hiện hình
```

Bảng điểm được in ra màn hình và ghi vào `scores.csv` trong thư mục hiện tại. Lệnh `main` với dữ liệu mẫu cho mã `001234`, điểm `9.5`, ghi chú `Câu bỏ trống: 7`.

## Cách hệ thống xử lý ảnh

1. **Ảnh xám và lọc Gauss:** giảm nhiễu.
2. **Phân ngưỡng thích nghi:** so mỗi điểm với vùng lân cận để tách nét đen khi ánh sáng không đều.
3. **Tìm 4 ô định vị:** chọn các vùng gần vuông, đặc, xếp đúng tỉ lệ phiếu và khớp với thanh đen ở mép trên.
4. **Biến đổi phối cảnh:** nắn ảnh về khung chuẩn 1654×2339 px. Thanh đen cho biết phiếu có bị ngược đầu không.
5. **Khử ánh sáng:** dùng phép đóng hình thái để ước lượng nền giấy, rồi chia ảnh cho nền.
6. **Đọc ô tô:** căn lại tâm từng ô theo viền in, rồi đo tỉ lệ điểm đen trong lõi ô.
7. **Chấm điểm:** điểm = số câu đúng / N × 10, làm tròn 2 chữ số thập phân.

## Quy tắc chấm

Hệ thống không cho điểm bài mà nó đọc không chắc chắn.

| Tình huống | Kết quả |
|---|---|
| Câu bỏ trống hoặc tô nhiều ô cùng độ đậm | Câu đó 0 điểm, có ghi chú |
| Ô tô nhạt, tô thiếu, tẩy chưa sạch | Cả bài "Cần xem lại", không cho điểm |
| Bóng đổ hoặc vật đen đè lên ô | Cả bài "Cần xem lại", không cho điểm |
| Ảnh mờ, lóa, lưới ô bị lệch | Cả bài "Cần xem lại", không cho điểm |
| Không thấy 4 ô định vị, ảnh có hai phiếu, file hỏng | Bài đó "Cần xem lại", các bài khác vẫn được chấm |
| Mã học sinh thiếu hoặc không đọc được | Cả bài "Cần xem lại", không cho điểm |
| Hai bài trùng mã học sinh | Vẫn chấm, có ghi chú ở cả hai bài |

Bảng điểm có các cột `ten_file,ma_hoc_sinh,so_cau_dung,diem,trang_thai,ghi_chu`. Excel có thể ẩn số 0 đầu mã học sinh khi hiển thị, nhưng dữ liệu trong file vẫn đúng.

## Tình trạng kiểm thử

| Hạng mục | Tình trạng |
|---|---|
| Code Python | Chạy bằng pytest trên máy, các test đều qua |
| Độ chính xác trên 900 ảnh mô phỏng | Không có bài nào bị chấm sai |
| `main.ipynb` | Đã chạy hết trên máy, trừ ô mở giao diện; chưa chạy trên Colab thật |
| `main.m` | **Chưa từng chạy** trên MATLAB hay Octave |
| Phiếu in thật chụp bằng điện thoại | **Chưa thử** |

Các ngưỡng đọc ô mới chỉ được chỉnh trên ảnh mô phỏng. Với ảnh thật, nhất là bút chì nhạt hoặc giấy xám, kết quả có thể khác. Nên thử 10–20 phiếu thật trước khi dùng, và chỉnh các ngưỡng trong `src/omr_read.py` nếu cần.

Chạy test và đo độ chính xác:

```bash
.venv/bin/pytest
.venv/bin/python tools/evaluate.py
```

Các test của `main.m` trong `tests/test_matlab.py` chỉ chạy khi máy có GNU Octave, nếu không sẽ tự bỏ qua.

## Cấu trúc thư mục

```text
.
├── main.ipynb              Notebook cho Colab (sinh từ tools/build_notebook.py)
├── main.py                 Chạy giao diện Gradio trên máy
├── main.m                  Bản MATLAB
├── requirements.txt
├── src/
│   ├── omr_layout.py       Tọa độ phiếu
│   ├── omr_sheet.py        Vẽ phiếu, xuất PDF
│   ├── omr_locate.py       Tìm và nắn phiếu
│   ├── omr_read.py         Đọc ô tô, kiểm tra chất lượng ảnh
│   ├── omr_grade.py        Đọc đáp án, chấm điểm, xuất CSV
│   └── omr_ui.py           Giao diện Gradio
├── templates/              Phiếu trắng để in
├── samples/                Đáp án và bài làm mẫu
├── tests/                  Test và bộ sinh ảnh mô phỏng
└── tools/                  Sinh notebook, đo độ chính xác
```

`main.ipynb` được sinh tự động, nên khi sửa code trong `src/` cần chạy lại:

```bash
.venv/bin/python tools/build_notebook.py
```
