import os
import sys
from pathlib import Path
import math

import requests
from dotenv import load_dotenv

from PySide6.QtCore import Qt, QTimer, QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QMessageBox,
    QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QPlainTextEdit, QScrollArea
)

from formatting import (
    parse_int_sr, parse_float_sr, fmt_int_sr, fmt_float_sr,
    fmt_cylinder_from_zuba, _fmt_cylinder,
)
from order_text import OPIS_DEFAULT, napred_ide_text, alati_text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = os.getenv("SERVER_PORT", "8000")
API_KEY     = os.getenv("API_KEY", "")
DOCS_DIR    = Path(os.getenv("DOCS_DIR", ROOT / "docs"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def url(path: str) -> str:
    return f"http://{SERVER_HOST}:{SERVER_PORT}{path}"

def headers():
    return {"x-api-key": API_KEY}

def get_json(path: str, params=None):
    r = requests.get(url(path), headers=headers(), params=params or {}, timeout=5)
    r.raise_for_status()
    return r.json()

def post_json(path: str, payload: dict):
    r = requests.post(url(path), headers=headers(), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YU LABEL – Nalog za proizvodnju")

        self.doc_number = None
        self.selected_customer_id = None
        self.selected_material_id = None
        self.selected_tool_id = None

        self.color_rows = []
        self.series_dates = []

        # Quantity sub-state
        self.k_kom_naruceno = None
        self.k_kom_po_m = None
        self.k_m_dobrih = None
        self.k_add_m = None
        self.k_note = ""
        self.k_stancna_mm = None
        self.k_rows_long = None
        self.k_rows_wide = None
        self.k_broj_zuba = None

        # Tool live-search state
        self._alati_rows = []

        # Field edits auto-filled by the šifra lookup -> the text it put there
        self._autofilled = {}
        # The ALATI line as last filled in automatically (from the chosen die
        # or a past order); a line typed by hand is not replaced
        self._alati_auto = ""

        # ---- Top title ----
        self.title_lbl = QLabel("NALOG ZA PROIZVODNJU —")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: 700;")

        # ---- Buttons ----
        btn_new = QPushButton("New number")
        btn_new.clicked.connect(self.on_new_number)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.on_save)

        btn_search = QPushButton("Pretraži naloge...")
        btn_search.clicked.connect(self.on_search_nalozi)

        top_btns = QHBoxLayout()
        top_btns.addWidget(btn_search)
        top_btns.addStretch()
        top_btns.addWidget(btn_new)
        top_btns.addWidget(btn_save)

        # ---- Machine dropdown ----
        self.machine_cb = QComboBox()
        self.machine_cb.setEditable(False)
        self.machine_map = {}  # name -> id

        # ---- Basic fields ----
        self.sifra_edit = QLineEdit()
        self.naziv_edit = QLineEdit()
        self.dim_edit = QLineEdit()
        self.mat_edit = QLineEdit()
        self.sirina_edit = QLineEdit()
        self.narucilac_edit = QLineEdit()

        self.rok_edit = QDateEdit()
        self.rok_edit.setCalendarPopup(True)
        self.rok_edit.setDisplayFormat("dd.MM.yyyy")
        self.rok_edit.setDate(QDate.currentDate().addDays(7))

        # ---- ŠIFRA debounce lookup ----
        self.sifra_timer = QTimer(self)
        self.sifra_timer.setInterval(250)
        self.sifra_timer.setSingleShot(True)
        self.sifra_timer.timeout.connect(self.lookup_product_by_sifra)
        self.sifra_edit.textEdited.connect(lambda _: self.sifra_timer.start())

        # ---- ALATI live search ----
        self.alati_edit = QLineEdit()
        self.alati_edit.setPlaceholderText("Pretraži alat / štancnu")
        self.alati_edit.textEdited.connect(lambda _: self.alati_timer.start())
        self.alati_edit.cursorPositionChanged.connect(self.show_alati_table)

        self.alati_table = QTableWidget(0, 6)
        self.alati_table.setHorizontalHeaderLabels([
            "Oznaka štancne", "Oznaka proizvođača", "Dimenzija",
            "Zuba", "Obim cilindra", "Raspored",
        ])
        self.alati_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.alati_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.alati_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.alati_table.verticalHeader().setVisible(False)
        self.alati_table.setAlternatingRowColors(True)
        self.alati_table.setSortingEnabled(True)
        self.alati_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.alati_table.setMaximumHeight(230)
        self.alati_table.cellDoubleClicked.connect(self.on_alati_row_activated)
        self.alati_table.hide()

        self.alati_timer = QTimer(self)
        self.alati_timer.setInterval(200)
        self.alati_timer.setSingleShot(True)
        self.alati_timer.timeout.connect(self.lookup_alati_live)

        btn_expand_alati = QPushButton("Expand")
        btn_expand_alati.clicked.connect(self.on_expand_alati)

        alati_search_row = QHBoxLayout()
        alati_search_row.addWidget(self.alati_edit, 1)
        alati_search_row.addWidget(btn_expand_alati, 0)

        alati_layout = QVBoxLayout()
        alati_layout.setContentsMargins(0, 0, 0, 0)
        alati_layout.addLayout(alati_search_row)
        alati_layout.addWidget(self.alati_table)

        alati_widget = QWidget()
        alati_widget.setLayout(alati_layout)

        # ---- KOLIČINA ----
        self.kolicina_kom_input = QLineEdit()
        self.kolicina_kom_input.setPlaceholderText("Naručeno kom")
        self.kolicina_kom_input.textChanged.connect(self.on_kolicina_kom_changed)

        self.kolicina_display = QLineEdit()
        self.kolicina_display.setReadOnly(True)

        btn_kolicina = QPushButton("Količina...")
        btn_kolicina.clicked.connect(self.on_edit_kolicina)

        kolicina_top_row = QHBoxLayout()
        kolicina_top_row.addWidget(self.kolicina_kom_input, 0)
        kolicina_top_row.addWidget(btn_kolicina, 0)

        kolicina_layout = QVBoxLayout()
        kolicina_layout.addLayout(kolicina_top_row)
        kolicina_layout.addWidget(self.kolicina_display)

        kolicina_widget = QWidget()
        kolicina_widget.setLayout(kolicina_layout)

        # ---- ŠIFRA BOJA button + preview table ----
        btn_colors = QPushButton("Uredi boje / kliše...")
        btn_colors.clicked.connect(self.on_edit_colors)

        self.colors_preview = QTableWidget(0, 6)
        self.colors_preview.setHorizontalHeaderLabels([
            "Poz.", "Kliše", "Var.", "Boja", "Raster", "Cilindar"
        ])
        self.colors_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.colors_preview.setMinimumHeight(220)
        self.colors_preview.verticalHeader().setVisible(False)
        self.colors_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        colors_layout = QVBoxLayout()
        colors_layout.setContentsMargins(0, 0, 0, 0)
        colors_layout.setSpacing(4)
        colors_layout.addWidget(btn_colors)
        colors_layout.addWidget(self.colors_preview)

        colors_widget = QWidget()
        colors_widget.setLayout(colors_layout)

        # ---- ŠTAMPA PREMA PRIPREMI ----
        self.probni_datum_row = QWidget()
        probni_layout = QHBoxLayout(self.probni_datum_row)
        probni_layout.setContentsMargins(0, 0, 0, 0)
        probni_layout.addWidget(QLabel("Datum probnog uzorka:"))
        self.probni_datum_edit = QDateEdit()
        self.probni_datum_edit.setCalendarPopup(True)
        self.probni_datum_edit.setDisplayFormat("dd.MM.yyyy")
        self.probni_datum_edit.setDate(QDate.currentDate())
        self.probni_datum_edit.dateChanged.connect(self.refresh_stampa_display)
        probni_layout.addWidget(self.probni_datum_edit)
        probni_layout.addStretch()

        self.stampa_display = QLineEdit()
        self.stampa_display.setReadOnly(True)
        self.stampa_display.setPlaceholderText("(unesite šifru...)")

        btn_edit_series = QPushButton("Uredi serije...")
        btn_add_date    = QPushButton("Dodaj datum serije")
        btn_edit_series.clicked.connect(self.on_edit_series)
        btn_add_date.clicked.connect(self.on_add_series_date)

        stampa_btns = QHBoxLayout()
        stampa_btns.addWidget(btn_edit_series)
        stampa_btns.addWidget(btn_add_date)
        stampa_btns.addStretch()

        stampa_layout = QVBoxLayout()
        stampa_layout.setContentsMargins(0, 0, 0, 0)
        stampa_layout.setSpacing(4)
        stampa_layout.addWidget(self.probni_datum_row)
        stampa_layout.addWidget(self.stampa_display)
        stampa_layout.addLayout(stampa_btns)

        stampa_widget = QWidget()
        stampa_widget.setLayout(stampa_layout)

        # ---- NAPRED IDE: which letter of the name is printed first ----
        self.napred_slovo_edit = QLineEdit()
        self.napred_slovo_edit.setPlaceholderText("W")
        self.napred_slovo_edit.setMaxLength(5)
        self.napred_slovo_edit.setFixedWidth(60)
        self.napred_naziv_edit = QLineEdit()
        self.napred_naziv_edit.setPlaceholderText("EHW")
        self.napred_slovo_edit.textChanged.connect(self.refresh_napred_display)
        self.napred_naziv_edit.textChanged.connect(self.refresh_napred_display)

        self.napred_display = QLineEdit()
        self.napred_display.setReadOnly(True)
        self.napred_display.setPlaceholderText("(unesite slovo i naziv...)")

        napred_inputs = QHBoxLayout()
        napred_inputs.addWidget(QLabel("slovo"))
        napred_inputs.addWidget(self.napred_slovo_edit)
        napred_inputs.addWidget(QLabel("u nazivu"))
        napred_inputs.addWidget(self.napred_naziv_edit, 1)

        napred_layout = QVBoxLayout()
        napred_layout.setContentsMargins(0, 0, 0, 0)
        napred_layout.setSpacing(4)
        napred_layout.addLayout(napred_inputs)
        napred_layout.addWidget(self.napred_display)

        napred_widget = QWidget()
        napred_widget.setLayout(napred_layout)

        # ---- ALATI line as the order prints it (filled from the chosen die) ----
        self.alati_nalog_edit = QLineEdit()
        self.alati_nalog_edit.setPlaceholderText("štancna oznake ..., Z-...")

        # ---- OPIS ----
        self.opis_edit = QPlainTextEdit()
        self.opis_edit.setPlainText(OPIS_DEFAULT)
        self.opis_edit.setFixedHeight(self.opis_edit.fontMetrics().lineSpacing() * 4 + 12)

        # ---- Form ----
        form = QFormLayout()
        form.addRow("MAŠINA:", self.machine_cb)
        form.addRow("ŠIFRA:", self.sifra_edit)
        form.addRow("NAZIV:", self.naziv_edit)
        form.addRow("DIMENZIJA:", self.dim_edit)
        form.addRow("MATERIJAL:", self.mat_edit)
        form.addRow("ŠIRINA:", self.sirina_edit)
        form.addRow("NARUČILAC:", self.narucilac_edit)
        form.addRow("ALATI:", alati_widget)
        form.addRow("KOLIČINA:", kolicina_widget)
        form.addRow("ROK ZA ISPORUKU:", self.rok_edit)
        form.addRow("ŠIFRA BOJA:", colors_widget)
        form.addRow("ŠTAMPA PREMA PRIPREMI:", stampa_widget)
        form.addRow("NAPRED IDE:", napred_widget)
        form.addRow("ALATI (u nalogu):", self.alati_nalog_edit)
        form.addRow("OPIS:", self.opis_edit)

        center = QWidget()
        center.setLayout(form)

        # The form is taller than some screens: scroll instead of growing
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(center)

        root_layout = QVBoxLayout()
        root_layout.addWidget(self.title_lbl)
        root_layout.addLayout(top_btns)
        root_layout.addWidget(scroll)

        wrap = QWidget()
        wrap.setLayout(root_layout)
        self.setCentralWidget(wrap)

        self.resize(820, 760)
        self.load_machines()

    # ------------------------------------------------------------------
    # Machine dropdown
    # ------------------------------------------------------------------

    def load_machines(self):
        try:
            rows = get_json("/lookup/machines", {"q": ""})
            self.machine_cb.clear()
            self.machine_map.clear()
            for r in rows:
                self.machine_cb.addItem(r["name"])
                self.machine_map[r["name"]] = r["id"]
            if self.machine_cb.count() == 0:
                self.machine_cb.addItem("(no machines)")
        except Exception as e:
            QMessageBox.critical(self, "Machines error", str(e))

    # ------------------------------------------------------------------
    # Document number
    # ------------------------------------------------------------------

    def on_new_number(self):
        try:
            data = requests.post(
                url("/documents/reserve-number"),
                headers=headers(),
                params={"username": "gui"},   # the endpoint reads a query parameter
                timeout=5,
            )
            data.raise_for_status()
            num = data.json().get("doc_number")
            self.doc_number = num
            self.title_lbl.setText(f"NALOG ZA PROIZVODNJU {num}")
            self.rok_edit.setDate(QDate.currentDate().addDays(7))
        except Exception as e:
            QMessageBox.critical(self, "Reserve number error", str(e))

    # ------------------------------------------------------------------
    # Product lookup by ŠIFRA
    # ------------------------------------------------------------------

    def lookup_product_by_sifra(self):
        sifra = self.sifra_edit.text().strip()

        # Drop text auto-filled from a previous product, unless the user edited it
        for edit, value in self._autofilled.items():
            if edit.text() == value:
                edit.clear()
        self._autofilled = {}

        # Only an exact šifra match counts – never a partial match while typing
        best = None
        if sifra:
            try:
                rows = get_json("/lookup/products", {"q": sifra})
                best = next((r for r in rows
                             if (r.get("sifra") or "").strip().lower() == sifra.lower()), None)
            except Exception as e:
                print("lookup error:", e)

        # No match -> no customer/material, so a save can't use a stale one
        self.selected_customer_id = best.get("customer_id") if best else None
        self.selected_material_id = best.get("material_id") if best else None

        if best:
            for edit, value in (
                (self.naziv_edit,     best.get("naziv")),
                (self.dim_edit,       best.get("dimenzija")),
                (self.sirina_edit,    best.get("sirina")),
                (self.narucilac_edit, best.get("customer_name")),
                (self.mat_edit,       best.get("material_name")),
            ):
                if value:   # an empty catalogue value never blanks a field
                    edit.setText(value)
                    self._autofilled[edit] = value
        self.load_series(sifra)

    # ------------------------------------------------------------------
    # Search past orders (Meilisearch via /documents/search)
    # ------------------------------------------------------------------

    def on_search_nalozi(self):
        dlg = NaloziDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_row_data:
            self.apply_nalog(dlg.selected_row_data)

    def apply_nalog(self, hit):
        """Prefill the form from a past order, for a repeat job."""
        idx = self.machine_cb.findText(hit.get("masina") or "", Qt.MatchFixedString)
        if idx >= 0:
            self.machine_cb.setCurrentIndex(idx)
        self.sifra_edit.setText(hit.get("sifra") or "")
        self.naziv_edit.setText(hit.get("naziv") or "")
        self.dim_edit.setText(hit.get("dimenzija") or "")
        self.mat_edit.setText(hit.get("materijal") or "")
        self.sirina_edit.setText(hit.get("sirina") or "")
        self.narucilac_edit.setText(hit.get("narucilac") or "")
        # The past order's ALATI line as it was printed; choosing a die
        # afterwards replaces it
        self._alati_auto = hit.get("alati") or ""
        self.alati_nalog_edit.setText(self._alati_auto)
        self._autofilled = {}   # the order's values are not from the catalogue
        # An exactly matching catalogue product supplies customer/material IDs
        # (and its non-empty fields); series dates are loaded either way
        self.lookup_product_by_sifra()

    # ------------------------------------------------------------------
    # KOLIČINA
    # ------------------------------------------------------------------

    def recompute_kolicina_display(self):
        try:
            kom = parse_int_sr(self.kolicina_kom_input.text())
        except ValueError:
            kom = None
            self.kolicina_display.setText("Neispravan broj komada")

        stancna   = self.k_stancna_mm
        rows_long = self.k_rows_long
        rows_wide = self.k_rows_wide

        self.k_kom_naruceno = kom

        if not kom or not stancna or not rows_long or not rows_wide or stancna == 0:
            # Nothing computed -> don't keep values from an earlier tool/quantity
            self.k_kom_po_m = self.k_m_dobrih = self.k_add_m = None
            if kom is not None:
                self.kolicina_display.setText(f"({fmt_int_sr(kom)} kom)")
            elif self.kolicina_kom_input.text().strip() == "":
                self.kolicina_display.clear()
            return

        kom_po_m = (1000.0 / stancna) * rows_long * rows_wide
        raw_m    = math.ceil(kom / kom_po_m)
        add_m    = (10 - (raw_m % 10)) % 10
        m_dobrih = raw_m + add_m

        self.k_kom_po_m  = kom_po_m
        self.k_m_dobrih  = m_dobrih
        self.k_add_m     = add_m

        line = f"{m_dobrih} m dobrih ({fmt_int_sr(kom)} kom) ({fmt_float_sr(kom_po_m, 2)} kom/m)"
        self.kolicina_display.setText(line)

    def on_kolicina_kom_changed(self):
        self.recompute_kolicina_display()

    def on_edit_kolicina(self):
        initial = {
            "kom": self.kolicina_kom_input.text().strip() or (
                fmt_int_sr(self.k_kom_naruceno) if self.k_kom_naruceno is not None else ""
            ),
            "stancna":   fmt_float_sr(self.k_stancna_mm, 3) if self.k_stancna_mm is not None else "",
            "rows_long": str(self.k_rows_long) if self.k_rows_long is not None else "",
            "rows_wide": str(self.k_rows_wide) if self.k_rows_wide is not None else "",
            "note":      self.k_note or "",
        }

        dlg = KolicinaDialog(self, initial=initial)
        if dlg.exec() != QDialog.Accepted:
            return

        res = dlg.result_payload()

        if res["kom"] is None:
            QMessageBox.warning(self, "Količina", "Please enter enough data to compute.")
            return

        self.k_kom_naruceno = res["kom"]
        self.k_kom_po_m     = res["kom_po_m"]
        self.k_m_dobrih     = res["m_dobrih"]
        self.k_add_m        = res["add_m"]
        self.k_stancna_mm   = res["stancna"]
        self.k_rows_long    = res["rows_long"]
        self.k_rows_wide    = res["rows_wide"]
        self.k_note         = res["note"] or ""

        self.kolicina_kom_input.setText(fmt_int_sr(res["kom"]))
        self.recompute_kolicina_display()

    # ------------------------------------------------------------------
    # ALATI live search
    # ------------------------------------------------------------------

    def lookup_alati_live(self):
        q = self.alati_edit.text().strip()
        try:
            rows = get_json("/lookup/tools", {"q": q, "limit": 5000})
            self._alati_rows = rows
            self.populate_alati_table(rows)
            self.alati_table.show()
        except Exception as e:
            self.alati_table.hide()
            QMessageBox.critical(self, "ALATI error", str(e))

    def populate_alati_table(self, rows):
        self._alati_rows = rows
        self.alati_table.setSortingEnabled(False)
        self.alati_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            sir  = row.get("dimenzija_sirina_mm")
            vis  = row.get("dimenzija_visina_mm")
            if sir is not None and vis is not None:
                dim = f"{float(sir):g} x {float(vis):g} mm"
            elif sir is not None:
                dim = f"{float(sir):g} mm"
            elif vis is not None:
                dim = f"{float(vis):g} mm"
            else:
                dim = ""

            obim = row.get("obim_cilindra_mm")
            values = [
                row.get("oznaka_stancne") or "",
                row.get("oznaka_proizvodjaca") or "",
                dim,
                row.get("broj_zuba") or "",
                f"{float(obim):g}" if obim is not None else "",
                row.get("raspored") or "",
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, i)   # store original index for post-sort lookup
                self.alati_table.setItem(i, col, item)

        self.alati_table.setSortingEnabled(True)

    def show_alati_table(self):
        self.alati_table.show()
        if not self._alati_rows:
            self.lookup_alati_live()

    def on_alati_row_activated(self, row, _column):
        # Must use UserRole data – visual row != original index after sorting
        item = self.alati_table.item(row, 0)
        if not item:
            return
        original_index = item.data(Qt.UserRole)
        if original_index is None or int(original_index) >= len(self._alati_rows):
            return
        self.apply_selected_alat(self._alati_rows[int(original_index)])

    def on_expand_alati(self):
        try:
            rows = get_json("/lookup/tools", {"q": "", "limit": 5000})   # dialog filters locally: needs all
            dlg = AlatiDialog(self, rows)
            if dlg.exec() == QDialog.Accepted and dlg.selected_row_data:
                self.apply_selected_alat(dlg.selected_row_data)
        except Exception as e:
            QMessageBox.critical(self, "ALATI error", str(e))

    def apply_selected_alat(self, best):
        self.selected_tool_id = best.get("id")
        self.alati_edit.setText(best.get("oznaka_stancne") or "")
        sir = best.get("dimenzija_sirina_mm")
        vis = best.get("dimenzija_visina_mm")
        if sir is not None and vis is not None:
            self.dim_edit.setText(f"{float(sir):g} x {float(vis):g} mm")
        elif sir is not None:
            self.dim_edit.setText(f"{float(sir):g} mm")
        elif vis is not None:
            self.dim_edit.setText(f"{float(vis):g} mm")
        self.k_stancna_mm  = float(best["obim_cilindra_mm"]) if best.get("obim_cilindra_mm") is not None else None
        self.k_rows_long   = best.get("rows_long")
        self.k_rows_wide   = best.get("rows_wide")
        self.k_broj_zuba   = best.get("broj_zuba")
        self.recompute_kolicina_display()
        self.alati_table.hide()

        # The order's ALATI line follows the chosen die, unless typed by hand
        if self.alati_nalog_edit.text() in ("", self._alati_auto):
            self._alati_auto = alati_text(best.get("oznaka_stancne") or "", self.k_broj_zuba)
            self.alati_nalog_edit.setText(self._alati_auto)

        # Backfill Cilindar on existing color rows that are still empty
        new_cylinder = fmt_cylinder_from_zuba(self.k_broj_zuba)

        if new_cylinder:
            for row in self.color_rows:
                if (row.get("klise_code") or "").lower() == "uređaj za lakiranje":
                    continue
                old = (row.get("cylinder") or "").strip()
                if old == "" or old.upper().startswith("Z-"):
                    row["cylinder"] = new_cylinder

            self.refresh_colors_preview()

    # ------------------------------------------------------------------
    # ŠIFRA BOJA / color rows
    # ------------------------------------------------------------------

    def on_edit_colors(self):
        zuba = fmt_cylinder_from_zuba(self.k_broj_zuba)
        dlg = ColorRowsDialog(self, self.color_rows, defaults={
            "cylinder": zuba,
            "klise_code": self.sifra_edit.text().strip(),
        })
        if dlg.exec() == QDialog.Accepted:
            self.color_rows = dlg.result_rows()
            self.refresh_colors_preview()

    _PREVIEW_CENTERED = {0, 2, 4, 5}  # Poz., Var., Raster, Cilindar

    def refresh_colors_preview(self):
        self.colors_preview.setRowCount(len(self.color_rows))
        for r, row in enumerate(self.color_rows):
            values = [
                row.get("position_label") or "",
                row.get("klise_code") or "",
                row.get("variant") or "",
                row.get("color_text") or "",
                row.get("raster") or "",
                row.get("cylinder") or "",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c in self._PREVIEW_CENTERED:
                    item.setTextAlignment(Qt.AlignCenter)
                self.colors_preview.setItem(r, c, item)

    # ------------------------------------------------------------------
    # Štampa prema pripremi / series dates
    # ------------------------------------------------------------------

    def load_series(self, sifra: str):
        if not sifra:
            self.series_dates = []
            self.refresh_stampa_display()
            return
        try:
            self.series_dates = get_json("/series", {"sifra": sifra})
        except Exception as e:
            print("Series load error:", e)
            self.series_dates = []
        self.refresh_stampa_display()

    def refresh_stampa_display(self):
        from datetime import date as _date
        if not self.series_dates:
            self.probni_datum_row.show()
            date_str = self.probni_datum_edit.date().toString("dd.MM.yyyy")
            text = (
                f"Štampa prema pripremi, prema uzorcima odštampanim "
                f"kao probni uzorak {date_str}."
            )
        else:
            self.probni_datum_row.hide()
            dates = sorted(r["datum"] for r in self.series_dates)
            fmt = []
            for d_str in dates:
                try:
                    fmt.append(_date.fromisoformat(d_str).strftime("%d.%m.%Y"))
                except Exception:
                    fmt.append(d_str)
            if len(fmt) == 1:
                joined = fmt[0]
            else:
                joined = ",".join(fmt[:-1]) + " i " + fmt[-1]
            text = (
                f"Štampa prema pripremi i prema uzorcima odštampanim "
                f"u prethodnim serijama ({joined})."
            )
        self.stampa_display.setText(text)

    def refresh_napred_display(self):
        self.napred_display.setText(napred_ide_text(
            self.napred_slovo_edit.text(), self.napred_naziv_edit.text()
        ))

    def on_add_series_date(self):
        sifra = self.sifra_edit.text().strip()
        if not sifra:
            QMessageBox.warning(self, "Greška", "Unesite šifru pre dodavanja datuma.")
            return
        dlg = AddSeriesDateDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.get_date()
        try:
            post_json("/series", {"sifra": sifra, "datum": d.isoformat()})
            self.load_series(sifra)
        except Exception as e:
            QMessageBox.critical(self, "Greška", str(e))

    def on_edit_series(self):
        sifra = self.sifra_edit.text().strip()
        if not sifra:
            QMessageBox.warning(self, "Greška", "Unesite šifru pre uređivanja serija.")
            return
        dlg = SeriesDialog(self, sifra=sifra, dates=self.series_dates)
        dlg.exec()
        self.load_series(sifra)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def on_save(self):
        if not self.doc_number:
            QMessageBox.warning(self, "Missing number", "Click 'New number' first.")
            return

        machine_name = self.machine_cb.currentText()
        machine_id   = self.machine_map.get(machine_name)
        rok_py       = self.rok_edit.date().toPython()

        payload = {
            "doc_number":            int(self.doc_number),
            "machine_id":            machine_id,
            "sifra":                 self.sifra_edit.text().strip() or None,
            "naziv":                 self.naziv_edit.text().strip() or None,
            "dimenzija":             self.dim_edit.text().strip() or None,
            "sirina":                self.sirina_edit.text().strip() or None,
            "customer_id":           self.selected_customer_id,
            "material_id":           self.selected_material_id,
            "kolicina_text":         self.kolicina_display.text().strip() or None,
            "kolicina_kom_naruceno": self.k_kom_naruceno,
            "kolicina_kom_po_m":     self.k_kom_po_m,
            "kolicina_m_dobrih":     self.k_m_dobrih,
            "kolicina_add_m":        self.k_add_m,
            "stancna_mm":            self.k_stancna_mm,
            "rows_long":             self.k_rows_long,
            "rows_wide":             self.k_rows_wide,
            "kolicina_note":         self.k_note or None,
            "rok_isporuke":          rok_py.isoformat() if rok_py else None,
            "napred_slovo":          self.napred_slovo_edit.text().strip() or None,
            "napred_naziv":          self.napred_naziv_edit.text().strip() or None,
            "alati":                 self.alati_nalog_edit.text().strip() or None,
            "opis":                  self.opis_edit.toPlainText().strip() or None,
        }

        try:
            res = post_json("/documents/finalize", payload)
            # Always save, even an empty list, so removed rows are deleted
            post_json("/documents/colors/save", {
                "doc_number": int(self.doc_number),
                "rows": self.color_rows,
            })

            sifra = self.sifra_edit.text().strip()
            # One series entry per order: saving the same order again must not
            # record another production run
            already_recorded = any(
                r.get("doc_number") == int(self.doc_number) for r in self.series_dates
            )
            if sifra and not already_recorded:
                from datetime import date as _date
                if not self.series_dates:
                    series_datum = self.probni_datum_edit.date().toPython()
                else:
                    series_datum = _date.today()
                post_json("/series", {
                    "sifra": sifra,
                    "datum": series_datum.isoformat(),
                    "doc_number": int(self.doc_number),
                })
                self.load_series(sifra)

            QMessageBox.information(self, "Saved", f"Saved document #{res['doc_number']}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))


# ---------------------------------------------------------------------------
# AlatiDialog – expanded tool search
# ---------------------------------------------------------------------------

class AlatiDialog(QDialog):
    def __init__(self, parent=None, rows=None):
        super().__init__(parent)
        self.setWindowTitle("ALATI search")
        self.resize(1100, 600)

        self.all_rows = rows or []
        self.rows = list(self.all_rows)
        self.selected_row_data = None

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Pretraži alat...")
        self.search_edit.textChanged.connect(self.filter_rows)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(btn_close)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Oznaka štancne", "Oznaka proizvođača", "Dimenzija",
            "Zuba", "Obim cilindra", "Raspored",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)

        self.populate()

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def filter_rows(self):
        q = self.search_edit.text().strip().lower()
        if not q:
            self.rows = list(self.all_rows)
        else:
            self.rows = [
                row for row in self.all_rows
                if q in " ".join([
                    str(row.get("oznaka_stancne") or ""),
                    str(row.get("oznaka_proizvodjaca") or ""),
                    str(row.get("dimenzija_sirina_mm") or ""),
                    str(row.get("dimenzija_visina_mm") or ""),
                    str(row.get("broj_zuba") or ""),
                    str(row.get("obim_cilindra_mm") or ""),
                    str(row.get("raspored") or ""),
                ]).lower()
            ]
        self.populate()

    def populate(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))

        for i, row in enumerate(self.rows):
            sir  = row.get("dimenzija_sirina_mm")
            vis  = row.get("dimenzija_visina_mm")
            if sir is not None and vis is not None:
                dim = f"{float(sir):g} x {float(vis):g} mm"
            elif sir is not None:
                dim = f"{float(sir):g} mm"
            elif vis is not None:
                dim = f"{float(vis):g} mm"
            else:
                dim = ""

            obim = row.get("obim_cilindra_mm")
            values = [
                row.get("oznaka_stancne") or "",
                row.get("oznaka_proizvodjaca") or "",
                dim,
                row.get("broj_zuba") or "",
                f"{float(obim):g}" if obim is not None else "",
                row.get("raspored") or "",
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, i)
                self.table.setItem(i, col, item)

        self.table.setSortingEnabled(True)

    def on_row_double_clicked(self, row, _column):
        item = self.table.item(row, 0)
        if not item:
            return
        original_index = item.data(Qt.UserRole)
        if original_index is None or int(original_index) >= len(self.rows):
            return
        self.selected_row_data = self.rows[int(original_index)]
        self.accept()


# ---------------------------------------------------------------------------
# NaloziDialog – search past production orders
# ---------------------------------------------------------------------------

class NaloziDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pretraga naloga")
        self.resize(1100, 600)

        self.rows = []
        self.selected_row_data = None

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Pretraži naloge (broj, naziv, šifra, naručilac...)")
        self.search_edit.textEdited.connect(lambda _: self.search_timer.start())

        self.search_timer = QTimer(self)
        self.search_timer.setInterval(250)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.run_search)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(btn_close)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Broj", "Naziv", "Šifra", "Naručilac", "Dimenzija", "Rok",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(lambda row, _col: self.on_fill_form())

        self.status_lbl = QLabel("")

        btn_open = QPushButton("Otvori dokument")
        btn_open.clicked.connect(self.on_open_document)
        btn_fill = QPushButton("Popuni formu")
        btn_fill.clicked.connect(self.on_fill_form)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.status_lbl, 1)
        bottom_row.addWidget(btn_open)
        bottom_row.addWidget(btn_fill)

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        self.run_search()

    def run_search(self):
        try:
            self.rows = get_json("/documents/search", {"q": self.search_edit.text().strip()})
            self.status_lbl.setText(f"{len(self.rows)} naloga")
        except Exception as e:
            self.rows = []
            self.status_lbl.setText(f"Greška pretrage: {e}")
        self.populate()

    def populate(self):
        from datetime import date as _date
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))

        for i, row in enumerate(self.rows):
            rok = row.get("rok_isporuke") or ""
            try:
                rok = _date.fromisoformat(rok).strftime("%d.%m.%Y")
            except ValueError:
                pass
            values = [
                row.get("broj_naloga"),
                row.get("naziv") or "",
                row.get("sifra") or "",
                row.get("narucilac") or "",
                row.get("dimenzija") or "",
                rok,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem()
                if col == 0:
                    item.setData(Qt.DisplayRole, value)   # numeric sort
                else:
                    item.setText(str(value))
                item.setData(Qt.UserRole, i)
                self.table.setItem(i, col, item)

        self.table.setSortingEnabled(True)

    def _selected(self):
        # Must use UserRole data – visual row != original index after sorting
        item = self.table.item(self.table.currentRow(), 0)
        if not item:
            return None
        original_index = item.data(Qt.UserRole)
        if original_index is None or int(original_index) >= len(self.rows):
            return None
        return self.rows[int(original_index)]

    def on_open_document(self):
        row = self._selected()
        if not row:
            return
        path = DOCS_DIR / (row.get("rel_path") or "")
        if not row.get("rel_path") or not path.is_file():
            QMessageBox.warning(self, "Dokument", f"Fajl nije pronađen:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def on_fill_form(self):
        row = self._selected()
        if not row:
            return
        self.selected_row_data = row
        self.accept()


# ---------------------------------------------------------------------------
# ColorRowsDialog
# ---------------------------------------------------------------------------

class ColorRowsDialog(QDialog):
    ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    _CENTERED = {0, 2, 4, 5}  # Poz., Var., Raster, Cilindar

    def _item(self, col: int, text: str) -> "QTableWidgetItem":
        item = QTableWidgetItem(text)
        if col in self._CENTERED:
            item.setTextAlignment(Qt.AlignCenter)
        return item

    def __init__(self, parent=None, rows=None, defaults=None):
        super().__init__(parent)
        self.defaults = defaults or {}
        self.setWindowTitle("ŠIFRA BOJA / KLIŠE")
        self.resize(1150, 500)

        self.rows = rows or []
        self._next_pos = 0   # monotonically increasing; never resets on delete

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Poz.", "Kliše code", "Varijanta", "Boja",
            "Raster", "Cilindar", "Dobavljač", "Napomena",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.CurrentChanged | QAbstractItemView.SelectedClicked)
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setDefaultDropAction(Qt.MoveAction)
        self.table.setDragDropOverwriteMode(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        btn_add      = QPushButton("Add row")
        btn_remove   = QPushButton("Remove row")
        btn_up       = QPushButton("Move up")
        btn_down     = QPushButton("Move down")
        btn_renumber = QPushButton("Renumber Poz.")
        btn_cmyk     = QPushButton("Add CMYK…")
        btn_ok       = QPushButton("OK")
        btn_cancel   = QPushButton("Cancel")

        btn_add.clicked.connect(self.add_row)
        btn_remove.clicked.connect(self.remove_selected_row)
        btn_up.clicked.connect(self.move_selected_row_up)
        btn_down.clicked.connect(self.move_selected_row_down)
        btn_renumber.clicked.connect(self.renumber_positions)
        btn_cmyk.clicked.connect(self.on_add_cmyk)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(btn_add)
        buttons.addWidget(btn_remove)
        buttons.addWidget(btn_up)
        buttons.addWidget(btn_down)
        buttons.addWidget(btn_renumber)
        buttons.addWidget(btn_cmyk)
        buttons.addStretch()
        buttons.addWidget(btn_ok)
        buttons.addWidget(btn_cancel)

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self.table.itemChanged.connect(self._on_item_changed)
        self.load_rows()

    def _on_item_changed(self, item):
        col = item.column()

        if col == 4:  # Raster – auto-append l/cm
            text = item.text().strip()
            if not text or text.endswith("l/cm"):
                return
            for suffix in ("l/cm", "l/c", "l/"):
                if text.endswith(suffix):
                    text = text[: -len(suffix)].strip()
                    break
            new_text = f"{text} l/cm"
            self.table.blockSignals(True)
            item.setText(new_text)
            self.table.blockSignals(False)

        elif col == 5:  # Cilindar – auto-prepend Z-
            new_text = _fmt_cylinder(item.text())
            if new_text != item.text():
                self.table.blockSignals(True)
                item.setText(new_text)
                self.table.blockSignals(False)

    def on_add_cmyk(self):
        """Open a small dialog to configure then insert CMYK (+optional UV lak) rows."""
        dlg = CmykPresetDialog(
            self,
            default_cylinder=self.defaults.get("cylinder", ""),
            default_klise=self.defaults.get("klise_code", ""),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        cfg = dlg.result_cfg()
        klise   = cfg["klise"]
        raster  = cfg["raster"]       # already formatted with l/cm
        cyl     = cfg["cylinder"]
        add_uv  = cfg["add_uv"]
        uv_cyl  = cfg["uv_cylinder"]

        cmyk = [
            ("C", "Process Cyan"),
            ("M", "Process Magenta"),
            ("Y", "Process Yellow"),
            ("K", "Process Black"),
        ]

        self.table.blockSignals(True)
        for variant, color in cmyk:
            r = self.table.rowCount()
            self.table.insertRow(r)
            pos_label = self.ROMAN[self._next_pos] if self._next_pos < len(self.ROMAN) else str(self._next_pos + 1)
            self._next_pos += 1
            for c, val in enumerate([pos_label, klise, variant, color, raster, cyl, "", ""]):
                self.table.setItem(r, c, self._item(c, val))

        if add_uv:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate(["VIII", "uređaj za lakiranje", "", "UV lak", "160 l/cm", uv_cyl, "", ""]):
                self.table.setItem(r, c, self._item(c, val))

        self.table.blockSignals(False)

    def move_selected_row_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        self.swap_rows(row, row - 1)
        self.table.selectRow(row - 1)

    def move_selected_row_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self.swap_rows(row, row + 1)
        self.table.selectRow(row + 1)

    def swap_rows(self, row1, row2):
        cols = self.table.columnCount()
        values1 = []
        values2 = []

        for c in range(cols):
            item1 = self.table.item(row1, c)
            item2 = self.table.item(row2, c)
            values1.append(item1.text() if item1 else "")
            values2.append(item2.text() if item2 else "")

        for c in range(cols):
            self.table.setItem(row1, c, self._item(c, values2[c]))
            self.table.setItem(row2, c, self._item(c, values1[c]))

    def renumber_positions(self):
        for r in range(self.table.rowCount()):
            label = self.ROMAN[r] if r < len(self.ROMAN) else str(r + 1)
            self.table.setItem(r, 0, self._item(0, label))

    def load_rows(self):
        self.table.setRowCount(0)
        # seed the counter so new rows continue after the highest existing position
        if self.rows:
            self._next_pos = max((r.get("position_num") or 0) for r in self.rows)
        else:
            self._next_pos = 0
        if not self.rows:
            self.add_row()
            return
        for row in self.rows:
            self.add_row(row)

    def add_row(self, row=None):
        r = self.table.rowCount()
        self.table.insertRow(r)

        if row:
            # restoring a saved row — use its stored label and don't bump counter
            pos_label = row.get("position_label") or (
                self.ROMAN[self._next_pos] if self._next_pos < len(self.ROMAN) else str(self._next_pos + 1)
            )
            self._next_pos = max(self._next_pos, (row.get("position_num") or 0))
        else:
            # brand-new row — use next unused position
            pos_label = self.ROMAN[self._next_pos] if self._next_pos < len(self.ROMAN) else str(self._next_pos + 1)
            self._next_pos += 1

        values = [
            pos_label,
            row.get("klise_code", "") if row else self.defaults.get("klise_code", ""),
            row.get("variant", "") if row else "",
            row.get("color_text", "") if row else "",
            (lambda v: v if not v or v.endswith("l/cm") else f"{v} l/cm")(row.get("raster", "") if row else ""),
            row.get("cylinder", "") if row else self.defaults.get("cylinder", ""),
            row.get("supplier", "") if row else "",
            row.get("note", "") if row else "",
        ]

        for c, value in enumerate(values):
            self.table.setItem(r, c, self._item(c, str(value or "")))

    def remove_selected_row(self):
        rows = sorted(
            set(idx.row() for idx in self.table.selectedIndexes()),
            reverse=True,  # delete from bottom so indices stay valid
        )
        for row in rows:
            self.table.removeRow(row)

    def result_rows(self):
        result = []
        for r in range(self.table.rowCount()):
            def txt(c, _r=r):
                item = self.table.item(_r, c)
                return item.text().strip() if item else ""

            if not any(txt(c) for c in range(1, 8)):
                continue  # skip fully empty rows

            result.append({
                "position_num":   r + 1,
                "position_label": txt(0) or (self.ROMAN[r] if r < len(self.ROMAN) else str(r + 1)),
                "klise_code":     txt(1) or None,
                "variant":        txt(2) or None,
                "color_text":     txt(3) or None,
                "raster":         txt(4) or None,
                "cylinder":       txt(5) or None,
                "supplier":       txt(6) or None,
                "note":           txt(7) or None,
            })
        return result


# ---------------------------------------------------------------------------
# CmykPresetDialog
# ---------------------------------------------------------------------------

class CmykPresetDialog(QDialog):
    def __init__(self, parent=None, default_cylinder="", default_klise=""):
        super().__init__(parent)
        self.setWindowTitle("Add CMYK preset")
        self.resize(380, 220)

        self.klise_edit    = QLineEdit()
        self.raster_edit   = QLineEdit()
        self.cylinder_edit = QLineEdit()
        self.uv_cyl_edit   = QLineEdit()

        self.raster_edit.setPlaceholderText("e.g. 390")
        self.klise_edit.setText(default_klise)
        self.cylinder_edit.setText(default_cylinder)
        self.cylinder_edit.setPlaceholderText("e.g. 88")
        self.uv_cyl_edit.setPlaceholderText("e.g. 88")

        self.cylinder_edit.editingFinished.connect(
            lambda: self.cylinder_edit.setText(_fmt_cylinder(self.cylinder_edit.text()))
        )
        self.uv_cyl_edit.editingFinished.connect(
            lambda: self.uv_cyl_edit.setText(_fmt_cylinder(self.uv_cyl_edit.text()))
        )

        from PySide6.QtWidgets import QCheckBox
        self.uv_check = QCheckBox("Also add UV lak row (station VIII)")
        self.uv_check.setChecked(True)
        self.uv_check.toggled.connect(self.uv_cyl_edit.setEnabled)

        form = QFormLayout()
        form.addRow("Kliše oznaka:", self.klise_edit)
        form.addRow("Raster (CMYK):", self.raster_edit)
        form.addRow("Cilindar (CMYK):", self.cylinder_edit)
        form.addRow("", self.uv_check)
        form.addRow("Cilindar (UV lak):", self.uv_cyl_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout()
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.setLayout(lay)

    def result_cfg(self):
        raster = self.raster_edit.text().strip()
        if raster and not raster.endswith("l/cm"):
            raster = f"{raster} l/cm"
        return {
            "klise":       self.klise_edit.text().strip(),
            "raster":      raster,
            "cylinder":    _fmt_cylinder(self.cylinder_edit.text()),
            "add_uv":      self.uv_check.isChecked(),
            "uv_cylinder": _fmt_cylinder(self.uv_cyl_edit.text()),
        }


# ---------------------------------------------------------------------------
# KolicinaDialog
# ---------------------------------------------------------------------------

class KolicinaDialog(QDialog):
    def __init__(self, parent=None, initial=None):
        super().__init__(parent)
        self.setWindowTitle("Količina calculator")

        self.kom_edit     = QLineEdit()
        self.stancna_edit = QLineEdit()
        self.long_edit    = QLineEdit()
        self.wide_edit    = QLineEdit()
        self.note_edit    = QLineEdit()

        self.out_kom_po_m = QLabel("—")
        self.out_raw_m    = QLabel("—")
        self.out_add_m    = QLabel("—")
        self.out_m_dobrih = QLabel("—")
        self.out_line     = QLabel("—")
        self.out_line.setTextInteractionFlags(Qt.TextSelectableByMouse)

        if initial:
            self.kom_edit.setText(initial.get("kom", ""))
            self.stancna_edit.setText(initial.get("stancna", ""))
            self.long_edit.setText(initial.get("rows_long", ""))
            self.wide_edit.setText(initial.get("rows_wide", ""))
            self.note_edit.setText(initial.get("note", ""))

        for w in [self.kom_edit, self.stancna_edit, self.long_edit,
                  self.wide_edit, self.note_edit]:
            w.textChanged.connect(self.recompute)

        form = QFormLayout()
        form.addRow("Naručeno (kom):",           self.kom_edit)
        form.addRow("Štancna (mm):",             self.stancna_edit)
        form.addRow("Reda (dužina):",            self.long_edit)
        form.addRow("Reda (širina):",            self.wide_edit)
        form.addRow("Napomena (free):",          self.note_edit)
        form.addRow("Kom/m:",                    self.out_kom_po_m)
        form.addRow("Metri pre zaokruživanja:",  self.out_raw_m)
        form.addRow("Dodato (minimalno do 0):",  self.out_add_m)
        form.addRow("m dobrih:",                 self.out_m_dobrih)
        form.addRow("Preview linije:",           self.out_line)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout()
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.setLayout(lay)

        self.recompute()

    def _inputs(self):
        """(kom, stancna, rows_long, rows_wide); ValueError names a bad field."""
        values = []
        for label, edit, parse in (
            ("Naručeno (kom)", self.kom_edit,     parse_int_sr),
            ("Štancna (mm)",   self.stancna_edit, parse_float_sr),
            ("Reda (dužina)",  self.long_edit,    parse_int_sr),
            ("Reda (širina)",  self.wide_edit,    parse_int_sr),
        ):
            try:
                values.append(parse(edit.text()))
            except ValueError:
                raise ValueError(f"Neispravan broj u polju „{label}“: {edit.text().strip()}") from None
        return values

    def accept(self):
        try:
            self._inputs()
        except ValueError as e:
            QMessageBox.warning(self, "Količina", str(e))
            return
        super().accept()

    def recompute(self):
        try:
            kom, stancna, rows_long, rows_wide = self._inputs()
        except ValueError as e:
            for out in (self.out_kom_po_m, self.out_raw_m, self.out_add_m, self.out_m_dobrih):
                out.setText("—")
            self.out_line.setText(str(e))
            return
        note      = (self.note_edit.text() or "").strip()

        kom_po_m = None
        raw_m    = None
        add_m    = None
        m_dobrih = None

        if stancna and rows_long and rows_wide and stancna != 0:
            kom_po_m = (1000.0 / stancna) * rows_long * rows_wide

        if kom and kom_po_m and kom_po_m > 0:
            raw_m    = math.ceil(kom / kom_po_m)
            add_m    = (10 - (raw_m % 10)) % 10
            m_dobrih = raw_m + add_m

        self.out_kom_po_m.setText(fmt_float_sr(kom_po_m, 2) if kom_po_m else "—")
        self.out_raw_m.setText(str(raw_m) if raw_m is not None else "—")
        self.out_add_m.setText(str(add_m) if add_m is not None else "—")
        self.out_m_dobrih.setText(str(m_dobrih) if m_dobrih is not None else "—")

        if m_dobrih is not None and kom is not None and kom_po_m is not None:
            line = f"{m_dobrih} m dobrih ({fmt_int_sr(kom)} kom) ({fmt_float_sr(kom_po_m, 2)} kom/m)"
            if note:
                line += (" - " if not note.startswith("-") else " ") + note
            self.out_line.setText(line)
        else:
            self.out_line.setText("—")

    def result_payload(self):
        kom, stancna, rows_long, rows_wide = self._inputs()   # validated in accept()
        note      = (self.note_edit.text() or "").strip()

        kom_po_m = None
        raw_m    = None
        add_m    = None
        m_dobrih = None

        if stancna and rows_long and rows_wide and stancna != 0:
            kom_po_m = (1000.0 / stancna) * rows_long * rows_wide
        if kom and kom_po_m and kom_po_m > 0:
            raw_m    = math.ceil(kom / kom_po_m)
            add_m    = (10 - (raw_m % 10)) % 10
            m_dobrih = raw_m + add_m

        line = None
        if m_dobrih is not None and kom is not None and kom_po_m is not None:
            line = f"{m_dobrih} m dobrih ({fmt_int_sr(kom)} kom) ({fmt_float_sr(kom_po_m, 2)} kom/m)"
            if note:
                line += (" - " if not note.startswith("-") else " ") + note

        return {
            "kom":       kom,
            "kom_po_m":  kom_po_m,
            "raw_m":     raw_m,
            "add_m":     add_m,
            "m_dobrih":  m_dobrih,
            "stancna":   stancna,
            "rows_long": rows_long,
            "rows_wide": rows_wide,
            "note":      note,
            "line":      line,
        }


# ---------------------------------------------------------------------------
# SeriesDialog – manage production series dates for a šifra
# ---------------------------------------------------------------------------

class SeriesDialog(QDialog):
    def __init__(self, parent=None, sifra="", dates=None):
        super().__init__(parent)
        self.setWindowTitle(f"Serije – {sifra}")
        self.resize(520, 350)
        self.sifra = sifra
        self.dates = list(dates or [])

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Datum", "Nalog br.", "Napomena"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        btn_add    = QPushButton("Dodaj datum")
        btn_remove = QPushButton("Ukloni")
        btn_close  = QPushButton("Zatvori")

        btn_add.clicked.connect(self.on_add)
        btn_remove.clicked.connect(self.on_remove)
        btn_close.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(btn_add)
        btns.addWidget(btn_remove)
        btns.addStretch()
        btns.addWidget(btn_close)

        lay = QVBoxLayout()
        lay.addWidget(self.table)
        lay.addLayout(btns)
        self.setLayout(lay)

        self.populate()

    def populate(self):
        from datetime import date as _date
        self.table.setRowCount(0)
        for row in self.dates:
            r = self.table.rowCount()
            self.table.insertRow(r)
            try:
                datum_str = _date.fromisoformat(row["datum"]).strftime("%d.%m.%Y")
            except Exception:
                datum_str = str(row.get("datum", ""))
            self.table.setItem(r, 0, QTableWidgetItem(datum_str))
            self.table.setItem(r, 1, QTableWidgetItem(str(row.get("doc_number") or "")))
            self.table.setItem(r, 2, QTableWidgetItem(str(row.get("note") or "")))

    def on_add(self):
        dlg = AddSeriesDateDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.get_date()
        try:
            post_json("/series", {"sifra": self.sifra, "datum": d.isoformat()})
            self.dates = get_json("/series", {"sifra": self.sifra})
            self.populate()
        except Exception as e:
            QMessageBox.critical(self, "Greška", str(e))

    def on_remove(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.dates):
            return
        entry_id = self.dates[row].get("id")
        if not entry_id:
            return
        reply = QMessageBox.question(
            self, "Potvrda", "Ukloniti ovaj datum iz serije?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            r = requests.delete(url(f"/series/{entry_id}"), headers=headers(), timeout=5)
            r.raise_for_status()
            self.dates = get_json("/series", {"sifra": self.sifra})
            self.populate()
        except Exception as e:
            QMessageBox.critical(self, "Greška", str(e))


# ---------------------------------------------------------------------------
# AddSeriesDateDialog – simple date-picker dialog
# ---------------------------------------------------------------------------

class AddSeriesDateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dodaj datum serije")
        self.resize(300, 110)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(QDate.currentDate())

        form = QFormLayout()
        form.addRow("Datum:", self.date_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout()
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.setLayout(lay)

    def get_date(self):
        return self.date_edit.date().toPython()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()