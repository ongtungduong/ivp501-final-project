"""Ghep cac module trong src/ thanh mot notebook tu chua de chay tren Colab."""
import ast
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "main.ipynb"
INTERNAL = ("omr_", "synth")

MODULES = [
    ("src/omr_layout.py", """## Bước 1. Bố cục phiếu
Mọi tọa độ nằm ở một chỗ, dùng chung khi vẽ và khi đọc phiếu. Phiếu A4 ở 200 DPI có kích thước 1654×2339 px. Nhờ vậy, sau khi nắn ảnh về đúng kích thước này, ta biết chính xác vị trí từng ô."""),
    ("src/omr_sheet.py", """## Bước 2. Vẽ phiếu và xuất PDF
Phiếu có 4 ô vuông đen ở góc để định vị và một thanh đen chỉ ở mép trên. Bốn ô góc giống nhau nên không phân biệt được ảnh ngược đầu; thanh đen giải quyết việc đó."""),
    ("src/omr_locate.py", """## Bước 3. Tìm phiếu và nắn ảnh
1. **Ảnh xám** và **lọc Gauss** để giảm nhiễu.
2. **Phân ngưỡng thích nghi**: mỗi điểm được so với vùng lân cận, nên ánh sáng không đều vẫn tách được nét đen.
3. **Tìm contour**: giữ các hình 4 đỉnh gần vuông, đặc và tối hơn hẳn giấy bao quanh, đó là ứng viên ô định vị. Bộ 4 ô đúng phải xếp đúng tỉ lệ phiếu và khớp với thanh định hướng, nhờ vậy loại được vật đen vuông ngoài phiếu.
4. **Biến đổi phối cảnh**: từ 4 cặp điểm tính ma trận 3×3, đưa ảnh nghiêng về khung chuẩn."""),
    ("src/omr_read.py", """## Bước 4. Đọc ô tô
- **Bù giấy cong**: tìm viền các ô in, ghép với vị trí chuẩn, ước lượng độ lệch mềm (đa thức rồi nội suy Gauss cục bộ) và nắn lại ảnh.
- **Khử ánh sáng**: phép đóng hình thái ước lượng nền giấy, chia ảnh cho nền và cho mức sáng giấy của chính phiếu để giấy gần 1 và mực gần 0.
- **Căn lại tâm ô**: khớp mẫu vòng tròn với viền in để bù sai số còn lại sau khi nắn.
- **Tỉ lệ điểm đen** trong lõi mỗi ô (bỏ viền in): dưới 0.25 là trống, trên 0.75 là đã tô, ở giữa là không chắc. Ô tô đủ diện tích nhưng quá nhạt cũng là không chắc.
- **"Trống" phải có bằng chứng**: phần trong viền ô và giấy quanh ô đều sạch. Nếu không, ô được coi là không chắc, nhờ vậy nét tô nhạt, vết tẩy và bóng đổ không bị chấm nhầm.
- **Kiểm tra chất lượng**: độ dốc tại cạnh ô định vị cho biết ảnh mờ; không thấy viền in của nhiều ô nghĩa là ảnh lóa hoặc lưới lệch."""),
    ("src/omr_grade.py", """## Bước 5. Chấm điểm
Điểm = số câu đúng / N × 10. Câu trống hoặc tô nhiều ô được 0 điểm và có ghi chú. Bài có điểm không chắc chắn được đánh dấu **Cần xem lại** và không cho điểm: thà để giáo viên xem lại còn hơn chấm sai."""),
    ("tests/synth.py", """## Bước 6. Sinh ảnh mô phỏng
Tạo ảnh có xoay, nghiêng, tối và ánh sáng không đều với đáp án biết trước, dùng để thử hệ thống khi chưa có phiếu thật."""),
    ("src/omr_ui.py", """## Bước 7. Giao diện Gradio"""),
]

INTRO = """# Hệ thống chấm bài trắc nghiệm

Quy trình: in phiếu → học sinh tô bài → giáo viên chụp ảnh → upload đáp án và ảnh → nhận điểm.

**Cách chạy trên Colab:** chọn *Runtime → Run all*, rồi kéo xuống cuối notebook để mở giao diện. Phiếu trắng và dữ liệu mẫu nằm trong thanh *Files* bên trái."""

DEMO = """## Bước 8. Tạo phiếu, dữ liệu mẫu và thử một bài
from pathlib import Path
import matplotlib.pyplot as plt

Path("templates").mkdir(exist_ok=True)
save_pdf("templates/answer_sheet.pdf")

mau = Path("samples")
mau.mkdir(exist_ok=True)
dap_an = {q: "ABCD"[q % 4] for q in range(1, 41)}
(mau / "sample_answer_key.csv").write_text(
    "cau,dap_an\\n" + "".join(f"{q},{a}\\n" for q, a in dap_an.items()))

bai_lam = dict(dap_an)
bai_lam[3] = "A" if dap_an[3] != "A" else "B"  # co y to sai cau 3
del bai_lam[7]  # co y bo trong cau 7
phieu = fill_sheet(render_sheet(), "001234", bai_lam)
anh_mau = mau / "sample_submission.jpg"
cv2.imwrite(str(anh_mau), photograph(phieu, angle=6, perspective=.03, gradient=.4))

ket_qua = grade_batch([str(anh_mau)], load_answer_key(str(mau / "sample_answer_key.csv")))[0]
print(ket_qua.status, ket_qua.student_id, ket_qua.score, ket_qua.notes)

fig, axes = plt.subplots(2, 4, figsize=(18, 10))
for ax in axes.flat:
    ax.axis("off")
for ax, (ten, anh) in zip(axes.flat, ket_qua.steps.items()):
    ax.imshow(anh[..., ::-1] if anh.ndim == 3 else anh, cmap="gray")
    ax.set_title(ten)
plt.show()

plt.figure(figsize=(8, 11))
plt.imshow(ket_qua.annotated[..., ::-1])
plt.axis("off")
plt.show()"""

LAUNCH = """import os

demo = build_ui()
if not os.environ.get("OMR_SKIP_LAUNCH"):
    # share=False: giao dien hien ngay trong Colab, khong tao link cong khai chua bai cua hoc sinh.
    # Neu khung giao dien khong hien, doi thanh share=True (bat ky ai co link deu vao duoc).
    demo.launch(share=False)"""


def strip_internal_imports(source):
    """Bo cac dong import giua cac module noi bo vi moi thu da nam chung notebook."""
    lines = source.splitlines()
    drop = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module.startswith(INTERNAL):
            drop.update(range(node.lineno - 1, node.end_lineno))
    return "\n".join(l for i, l in enumerate(lines) if i not in drop).strip()


def build():
    cells = [new_markdown_cell(INTRO), new_code_cell("%pip install -q gradio==6.31.0")]
    for path, explanation in MODULES:
        cells.append(new_markdown_cell(explanation))
        cells.append(new_code_cell(strip_internal_imports((ROOT / path).read_text(encoding="utf-8"))))
    title, code = DEMO.split("\n", 1)
    cells += [new_markdown_cell(title), new_code_cell(code),
              new_markdown_cell("## Bước 9. Mở giao diện chấm bài"), new_code_cell(LAUNCH)]
    nb = new_notebook(cells=cells, metadata={"kernelspec": {
        "name": "python3", "display_name": "Python 3", "language": "python"}})
    nbformat.write(nb, OUTPUT)


if __name__ == "__main__":
    build()
