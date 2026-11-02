"""Chay he thong cham bai tren may: python main.py [--port 7860]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from omr_sheet import save_pdf  # noqa: E402
from omr_ui import build_ui  # noqa: E402

SHEET_PDF = Path(__file__).parent / "templates" / "answer_sheet.pdf"


def main():
    parser = argparse.ArgumentParser(description="Hệ thống chấm bài trắc nghiệm")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    if not SHEET_PDF.exists():
        SHEET_PDF.parent.mkdir(exist_ok=True)
        save_pdf(str(SHEET_PDF))
    print(f"Phiếu trắng để in: {SHEET_PDF}")
    build_ui().launch(server_name="127.0.0.1", server_port=args.port)


if __name__ == "__main__":
    main()
