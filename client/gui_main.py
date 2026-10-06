import sys
import os
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout
from PySide6.QtCore import QSizeF
from PySide6.QtGui import QPageSize

import requests
from dotenv import load_dotenv

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QMessageBox,
    QSplitter,
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog

# --- load .env from project root ---
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = os.getenv("SERVER_PORT", "8000")
API_KEY     = os.getenv("API_KEY", "")

def api_get(path: str):
    url = f"http://{SERVER_HOST}:{SERVER_PORT}{path}"
    r = requests.get(url, headers={"x-api-key": API_KEY}, timeout=5)
    r.raise_for_status()
    return r.json()

def api_post(path: str, params=None):
    url = f"http://{SERVER_HOST}:{SERVER_PORT}{path}"
    r = requests.post(url, headers={"x-api-key": API_KEY}, params=params or {}, timeout=5)
    r.raise_for_status()
    return r.json()


class LabelCanvas(QWidget):
    """Visual representation of a 90 x 60 mm label."""

    label_width_mm = 90
    label_height_mm = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc_number: str | None = None
        self.title = ""
        self.customer = ""
        self.date = ""
        self.setMinimumSize(400, 300)

    def sizeHint(self) -> QSize:
        return QSize(600, 400)

    # ---- drawing logic shared with printer ----
    def draw_label(self, painter: QPainter, target_rect: QRectF):
        # Fit label (in mm) into target_rect preserving aspect ratio.
        scale = min(
            target_rect.width() / self.label_width_mm,
            target_rect.height() / self.label_height_mm,
        )
        draw_w = self.label_width_mm * scale
        draw_h = self.label_height_mm * scale

        x = target_rect.x() + (target_rect.width() - draw_w) / 2
        y = target_rect.y() + (target_rect.height() - draw_h) / 2
        rect = QRectF(x, y, draw_w, draw_h)

        # Background
        painter.fillRect(rect, QBrush(Qt.white))

        # Border
        pen = QPen(Qt.black)
        pen.setWidthF(0.6 * scale)
        painter.setPen(pen)
        painter.drawRect(rect)

        margin = 4 * scale

        # Header text (title)
        header_rect = QRectF(
            rect.x() + margin,
            rect.y() + margin,
            rect.width() - 2 * margin,
            rect.height() * 0.25,
        )
        font = QFont("Sans Serif", int(4 * scale))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            header_rect,
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            self.title or "Demo etiketa (placeholder title)",
        )

        # Customer + date line
        info_rect = QRectF(
            rect.x() + margin,
            rect.y() + rect.height() * 0.25 + margin,
            rect.width() - 2 * margin,
            rect.height() * 0.15,
        )
        font_info = QFont("Sans Serif", int(3 * scale))
        painter.setFont(font_info)
        painter.drawText(
            info_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            f"Customer: {self.customer or '—'}   Date: {self.date or '—'}",
        )

        # Doc number at bottom right
        footer_rect = QRectF(
            rect.x() + margin,
            rect.y() + rect.height() - margin - rect.height() * 0.12,
            rect.width() - 2 * margin,
            rect.height() * 0.12,
        )
        font_footer = QFont("Sans Serif", int(3 * scale))
        painter.setFont(font_footer)
        painter.drawText(
            footer_rect,
            Qt.AlignRight | Qt.AlignVCenter,
            f"No: {self.doc_number or '—'}",
        )

        # Crosshair at center
        cx = rect.center().x()
        cy = rect.center().y()
        painter.drawLine(cx - 5 * scale, cy, cx + 5 * scale, cy)
        painter.drawLine(cx, cy - 5 * scale, cx, cy + 5 * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        target = QRectF(0, 0, self.width(), self.height())
        self.draw_label(painter, target)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("YU LABEL DMS – Prototype GUI")
        self.doc_number = None

        # --- status + buttons ---
        self.status_lbl = QLabel("Status: Not connected")
        btn_ping = QPushButton("Test connection")
        btn_ping.clicked.connect(self.on_test_connection)

        btn_new = QPushButton("New document number")
        btn_new.clicked.connect(self.on_new_document)

        btn_preview = QPushButton("Print preview")
        btn_preview.clicked.connect(self.on_print_preview)

        btn_print = QPushButton("Print")
        btn_print.clicked.connect(self.on_print)

        top_row = QHBoxLayout()
        top_row.addWidget(self.status_lbl, 1)
        top_row.addStretch()
        top_row.addWidget(btn_ping)
        top_row.addWidget(btn_new)
        top_row.addWidget(btn_preview)
        top_row.addWidget(btn_print)

        top_widget = QWidget()
        top_widget.setLayout(top_row)

        # --- left pane: metadata form ---
        self.doc_number_edit = QLineEdit()
        self.doc_number_edit.setReadOnly(True)

        self.title_edit = QLineEdit()
        self.customer_edit = QLineEdit()
        self.date_edit = QLineEdit()

        form = QFormLayout()
        form.addRow("Doc number:", self.doc_number_edit)
        form.addRow("Title:", self.title_edit)
        form.addRow("Customer:", self.customer_edit)
        form.addRow("Date:", self.date_edit)

        left_widget = QWidget()
        left_widget.setLayout(form)
        left_widget.setMinimumWidth(250)

        # --- center: label canvas ---
        self.canvas = LabelCanvas()

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout = QVBoxLayout()
        main_layout.addWidget(top_widget)
        main_layout.addWidget(splitter)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.resize(1000, 650)

    def configure_printer_for_label(self, printer: QPrinter):
        page_size = QPageSize(QSizeF(90, 60), QPageSize.Millimeter, "YU_LABEL_90x60")
        printer.setPageSize(page_size)
        printer.setFullPage(True)

        layout = printer.pageLayout()
        layout.setUnits(QPageLayout.Millimeter)
        layout.setPageSize(page_size)
        layout.setMargins(QMarginsF(0, 0, 0, 0))
        layout.setOrientation(QPageLayout.Portrait)  
        printer.setPageLayout(layout)
        printer.setFullPage(True)

    # ---- helpers ----
    def sync_canvas_metadata(self):
        self.canvas.doc_number = self.doc_number_edit.text() or None
        self.canvas.title = self.title_edit.text()
        self.canvas.customer = self.customer_edit.text()
        self.canvas.date = self.date_edit.text()
        self.canvas.update()

    # ---- slots ----
    def on_test_connection(self):
        try:
            data = api_get("/ping")
            if data.get("ok"):
                self.status_lbl.setText("Status: Connected ✅")
            else:
                self.status_lbl.setText("Status: Unexpected reply")
        except Exception as e:
            QMessageBox.critical(self, "Connection error", str(e))
            self.status_lbl.setText("Status: Failed ❌")

    def on_new_document(self):
        try:
            data = api_post("/documents/reserve-number", {"username": "gui"})
            num = data.get("doc_number")
            if num is None:
                QMessageBox.warning(self, "Error", "Server did not return a doc_number.")
                return
            self.doc_number = num
            self.doc_number_edit.setText(str(num))
            self.status_lbl.setText(f"Status: New document #{num}")
            self.sync_canvas_metadata()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def on_print_preview(self):
        self.sync_canvas_metadata()
        printer = QPrinter(QPrinter.HighResolution)
        self.configure_printer_for_label(printer)
        printer.setPageOrientation(QPageLayout.Landscape)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(self.print_on_printer)
        preview.exec()

    def on_print(self):
        self.sync_canvas_metadata()
        printer = QPrinter(QPrinter.HighResolution)
        self.configure_printer_for_label(printer)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.Accepted:
            self.print_on_printer(printer)

    def print_on_printer(self, printer: QPrinter):
        painter = QPainter(printer)
        painter.setRenderHint(QPainter.Antialiasing)
        sx = printer.logicalDpiX() / 25.4
        sy = printer.logicalDpiY() / 25.4
        painter.scale(sx, sy)
        target_mm = QRectF(0, 0, 90, 60)
        self.canvas.draw_label(painter, target_mm)
        painter.end()

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
