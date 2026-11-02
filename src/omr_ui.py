"""Giao dien Gradio: upload dap an va bai lam, xem diem va tung buoc xu ly."""
import os
import tempfile

import cv2
import gradio as gr

from omr_grade import AnswerKeyError, grade_batch, load_answer_key, write_csv

COLUMNS = ["Tên file", "Mã học sinh", "Số câu đúng", "Điểm", "Trạng thái", "Ghi chú"]


def _rgb(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 else img


def run_grading(key_path, image_paths):
    """Tra ve (hang cua bang, duong dan CSV, ket qua, thong bao)."""
    if not key_path:
        return [], None, [], "Hãy upload file đáp án."
    if not image_paths:
        return [], None, [], "Hãy upload ít nhất một ảnh bài làm."
    try:
        key = load_answer_key(key_path)
    except AnswerKeyError as e:
        return [], None, [], f"Lỗi file đáp án: {e}"
    results = grade_batch(image_paths, key)
    rows = [[r.filename, r.student_id or "", r.correct, r.score, r.status, "; ".join(r.notes)]
            for r in results]
    csv_path = os.path.join(tempfile.mkdtemp(), "scores.csv")
    write_csv(results, csv_path)
    review = sum(r.score is None for r in results)
    return rows, csv_path, results, f"Đã xử lý {len(results)} bài, {review} bài cần xem lại."


def show_sheet(index, results):
    """Tra ve (anh danh dau, [(anh tung buoc, ten buoc)]) cua bai thu index."""
    if index is None or not results or index >= len(results):
        return None, []
    r = results[index]
    annotated = None if r.annotated is None else _rgb(r.annotated)
    return annotated, [(_rgb(img), step) for step, img in r.steps.items()]


def build_ui():
    with gr.Blocks(title="Chấm bài trắc nghiệm") as demo:
        gr.Markdown("# Hệ thống chấm bài trắc nghiệm")
        results = gr.State([])
        with gr.Row():
            key = gr.File(label="1. File đáp án (CSV: cau,dap_an)", file_count="single",
                          file_types=[".csv"])
            images = gr.File(label="2. Ảnh bài làm (chọn được nhiều file)", file_count="multiple",
                             file_types=["image"])
        run = gr.Button("Chấm bài", variant="primary")
        message = gr.Markdown()
        table = gr.Dataframe(headers=COLUMNS, datatype="str", label="Kết quả", interactive=False)
        csv_file = gr.File(label="Tải file điểm (Excel có thể ẩn số 0 đầu mã học sinh)", interactive=False)
        choice = gr.Dropdown(label="Xem chi tiết bài", choices=[])
        with gr.Row():
            annotated = gr.Image(label="Đánh dấu: xanh là đáp án đúng, đỏ là ô tô sai")
            steps = gr.Gallery(label="Các bước xử lý ảnh", columns=3)

        def on_run(key_path, image_paths):
            rows, csv_path, res, msg = run_grading(key_path, image_paths)
            names = [(f"{i + 1}. {r.filename}", i) for i, r in enumerate(res)]
            return (rows, csv_path, res, msg, gr.update(choices=names, value=None), None, [])

        run.click(on_run, [key, images], [table, csv_file, results, message, choice, annotated, steps])
        choice.change(show_sheet, [choice, results], [annotated, steps])
    return demo
