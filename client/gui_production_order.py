import copy
import os
import sys
from pathlib import Path
import math

import requests
from dotenv import load_dotenv

from PySide6.QtCore import Qt, QTimer, QDate, QUrl, QEvent, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QMessageBox,
    QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QPlainTextEdit, QScrollArea, QInputDialog
)

from formatting import (
    parse_int_sr, parse_float_sr, fmt_int_sr, fmt_float_sr,
    fmt_cylinder_from_zuba, _fmt_cylinder,
)
from order_text import (
    OPIS_DEFAULT, NAPOMENA_DEFAULT, KOM_PO_ROLNI_DEFAULT, MAX_D_DEFAULT,
    napred_ide_text, alati_text, stampa_text, ranije_serije,
    odmotavanje_text, otkucaji, split_rolls, rasecanje_text, napomena_text,
    caure_text,
)
import alati_filter

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
        self.chosen_tool = None   # the chosen die's catalogue row

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

        # Field edits auto-filled by the šifra lookup -> the text it put there
        self._autofilled = {}
        # The roll groups as last proposed; groups changed by hand are kept
        self._rolne_auto = []
        # The form as last saved or opened, to notice unsaved changes
        self._saved_state = None

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

        btn_open = QPushButton("Otvori nalog...")
        btn_open.setToolTip("Otvori nalog u formi onako kako je sačuvan")
        btn_open.clicked.connect(self.on_open_nalog)

        top_btns = QHBoxLayout()
        top_btns.addWidget(btn_search)
        top_btns.addWidget(btn_open)
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

        # ---- ALATI: the chosen die, and a search field per column ----
        self.alati_chosen = QLineEdit()
        self.alati_chosen.setReadOnly(True)
        self.alati_chosen.setPlaceholderText("(izaberite štancnu: pretraga ispod, dupli klik na red)")

        self.alati_search = AlatiSearch(collapsed=True)
        self.alati_search.table.setFixedHeight(230)   # the scrolling form would squeeze it
        self.alati_search.chosen.connect(self.apply_selected_alat)

        btn_expand_alati = QPushButton("Expand")
        btn_expand_alati.clicked.connect(self.on_expand_alati)

        alati_chosen_row = QHBoxLayout()
        alati_chosen_row.addWidget(self.alati_chosen, 1)
        alati_chosen_row.addWidget(btn_expand_alati, 0)

        alati_layout = QVBoxLayout()
        alati_layout.setContentsMargins(0, 0, 0, 0)
        alati_layout.setSpacing(4)
        alati_layout.addLayout(alati_chosen_row)
        alati_layout.addWidget(self.alati_search)

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

        # Proposed from the product's earlier runs; any text can be typed instead
        self.stampa_edit = ProposedText(lines=2, placeholder="(unesite šifru...)")

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
        stampa_layout.addWidget(self.stampa_edit)
        stampa_layout.addLayout(stampa_btns)

        stampa_widget = QWidget()
        stampa_widget.setLayout(stampa_layout)

        # ---- NAPRED IDE: which letter of the name is printed first ----
        self.napred_slovo_edit = QLineEdit()
        self.napred_slovo_edit.setPlaceholderText("D")
        self.napred_slovo_edit.setMaxLength(5)
        self.napred_slovo_edit.setFixedWidth(60)
        self.napred_naziv_edit = QLineEdit()
        self.napred_naziv_edit.setPlaceholderText("Demo")
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

        # ---- ALATI line as the order prints it (proposed from the chosen die) ----
        self.alati_nalog_edit = ProposedText(placeholder="štancna oznake ..., Z-...")

        # ---- OPIS ----
        self.opis_edit = QPlainTextEdit()
        self.opis_edit.setPlainText(OPIS_DEFAULT)
        self.opis_edit.setFixedHeight(self.opis_edit.fontMetrics().lineSpacing() * 4 + 12)

        # ---- NAPOMENA: slitting into rolls, unwinding, the rest ----
        # Core: inner Ø / outer Ø / width; the form writes "Ø" and "mm" itself
        self.caura_unutra_edit = QLineEdit()
        self.caura_unutra_edit.setPlaceholderText("45")
        self.caura_spolja_edit = QLineEdit()
        self.caura_spolja_edit.setPlaceholderText("52")
        self.caura_sirina_edit = QLineEdit()
        self.caura_sirina_edit.setPlaceholderText("65")
        for edit in (self.caura_unutra_edit, self.caura_spolja_edit, self.caura_sirina_edit):
            edit.setFixedWidth(60)
            edit.textChanged.connect(self.refresh_napomena_display)
        self.max_d_edit = QLineEdit(MAX_D_DEFAULT)
        self.max_d_edit.setFixedWidth(60)
        self.kom_po_rolni_edit = QLineEdit(KOM_PO_ROLNI_DEFAULT)
        self.kom_po_rolni_edit.setFixedWidth(100)
        self.max_d_edit.textChanged.connect(self.refresh_napomena_display)
        self.kom_po_rolni_edit.textChanged.connect(self.refresh_napomena)

        self.rolne_table = QTableWidget(0, 3)
        self.rolne_table.setHorizontalHeaderLabels(["Rolni", "kom/rolna", "otkucaja/rolna"])
        self.rolne_table.verticalHeader().setVisible(False)
        self.rolne_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.rolne_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rolne_table.setFixedHeight(   # room for three groups
            self.rolne_table.horizontalHeader().sizeHint().height()
            + self.rolne_table.verticalHeader().defaultSectionSize() * 3
            + self.rolne_table.frameWidth() * 2
        )
        self.rolne_table.itemChanged.connect(self.refresh_napomena_display)

        btn_add_group = QPushButton("+ grupa")
        btn_remove_group = QPushButton("− grupa")
        btn_add_group.clicked.connect(self.on_add_roll_group)
        btn_remove_group.clicked.connect(self.on_remove_roll_group)

        # The slitting line, proposed from the fields and roll groups above
        self.rasecanje_edit = ProposedText(lines=3, placeholder="(Raseći na čaure ...)")

        # Proposed from NAPRED IDE with the letter at the other end of the name
        self.odmotavanje_edit = ProposedText(
            placeholder="(Pri odmotavanju gotove rolnice napred ide slovo ...)"
        )

        self.napomena_ostalo_edit = QPlainTextEdit()
        self.napomena_ostalo_edit.setPlainText(NAPOMENA_DEFAULT)
        self.napomena_ostalo_edit.setFixedHeight(
            self.napomena_ostalo_edit.fontMetrics().lineSpacing() * 3 + 12
        )

        caure_row = QHBoxLayout()
        caure_row.addWidget(QLabel("čaure Ø"))
        caure_row.addWidget(self.caura_unutra_edit)
        caure_row.addWidget(QLabel("/ Ø"))
        caure_row.addWidget(self.caura_spolja_edit)
        caure_row.addWidget(QLabel("/"))
        caure_row.addWidget(self.caura_sirina_edit)
        caure_row.addWidget(QLabel("mm"))
        caure_row.addStretch()
        caure_row.addWidget(QLabel("max. Ø"))
        caure_row.addWidget(self.max_d_edit)
        caure_row.addWidget(QLabel("mm"))

        rolne_row = QHBoxLayout()
        rolne_row.addWidget(QLabel("kom/rolna"))
        rolne_row.addWidget(self.kom_po_rolni_edit)
        rolne_row.addStretch()
        rolne_row.addWidget(btn_add_group)
        rolne_row.addWidget(btn_remove_group)

        napomena_layout = QVBoxLayout()
        napomena_layout.setContentsMargins(0, 0, 0, 0)
        napomena_layout.setSpacing(4)
        napomena_layout.addLayout(caure_row)
        napomena_layout.addLayout(rolne_row)
        napomena_layout.addWidget(self.rolne_table)
        napomena_layout.addWidget(self.rasecanje_edit)
        napomena_layout.addWidget(self.odmotavanje_edit)
        napomena_layout.addWidget(self.napomena_ostalo_edit)
        napomena_layout.addStretch()   # spare height goes below, not between the rows

        napomena_widget = QWidget()
        napomena_widget.setLayout(napomena_layout)

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
        form.addRow("NAPOMENA:", napomena_widget)

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
        self._saved_state = self.form_state()

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
            self.refresh_stampa_display()   # which runs count as earlier depends on the order
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
            if dlg.open_in_form:
                self.open_document(dlg.selected_row_data.get("broj_naloga"))
            else:
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
        self.alati_nalog_edit.propose(hit.get("alati") or "", force=True)
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
            self.refresh_napomena()
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
        self.refresh_napomena()

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
    # ALATI
    # ------------------------------------------------------------------

    def on_expand_alati(self):
        try:
            rows = get_json("/lookup/tools", {"q": "", "limit": 5000})
            dlg = AlatiDialog(self, rows)
            if dlg.exec() == QDialog.Accepted and dlg.selected_row_data:
                self.apply_selected_alat(dlg.selected_row_data)
        except Exception as e:
            QMessageBox.critical(self, "ALATI error", str(e))

    def _alati_proposal(self) -> str:
        """The order's ALATI line for the chosen die; empty without one."""
        tool = self.chosen_tool or {}
        return alati_text(tool.get("oznaka_stancne") or "", self.k_broj_zuba)

    def apply_selected_alat(self, best):
        self.chosen_tool = best
        self.selected_tool_id = best.get("id")
        self.alati_chosen.setText(alati_filter.summary(best))
        dim = alati_filter.dimenzija_text(best)
        if dim:
            self.dim_edit.setText(dim)
        self.k_stancna_mm  = float(best["obim_cilindra_mm"]) if best.get("obim_cilindra_mm") is not None else None
        self.k_rows_long   = best.get("rows_long")
        self.k_rows_wide   = best.get("rows_wide")
        self.k_broj_zuba   = best.get("broj_zuba")
        self.recompute_kolicina_display()
        self.alati_search.table.hide()

        # The order's ALATI line follows the chosen die, unless changed by hand
        self.alati_nalog_edit.propose(self._alati_proposal())

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
        """Propose the Štampa line from the product's earlier runs."""
        serije = ranije_serije(self.series_dates, self.doc_number)
        self.probni_datum_row.setVisible(not serije)
        self.stampa_edit.propose(stampa_text(
            serije, self.probni_datum_edit.date().toString(Qt.ISODate)
        ))

    def refresh_napred_display(self):
        self.napred_display.setText(napred_ide_text(
            self.napred_slovo_edit.text(), self.napred_naziv_edit.text()
        ))
        # NAPOMENA's unwinding line follows, unless it was changed by hand
        self.odmotavanje_edit.propose(odmotavanje_text(
            self.napred_slovo_edit.text(), self.napred_naziv_edit.text()
        ))

    # ------------------------------------------------------------------
    # NAPOMENA
    # ------------------------------------------------------------------

    def _roll_groups(self):
        """The (rolls, kom/rolna) groups in the table; incomplete rows are skipped."""
        groups = []
        for r in range(self.rolne_table.rowCount()):
            cells = [self.rolne_table.item(r, c) for c in (0, 1)]
            try:
                rolls, kom = (parse_int_sr(cell.text() if cell else "") for cell in cells)
            except ValueError:
                continue
            if rolls and kom:
                groups.append((rolls, kom))
        return groups

    def _roll_rows(self):
        """The table's (rolls, kom/rolna) cells as typed, incomplete rows too."""
        def cell(r, c):
            item = self.rolne_table.item(r, c)
            return item.text() if item else ""
        return [[cell(r, 0), cell(r, 1)] for r in range(self.rolne_table.rowCount())]

    def _set_roll_rows(self, rows):
        self.rolne_table.blockSignals(True)
        self.rolne_table.setRowCount(0)
        for row in rows:
            rolls, kom = (list(row) + ["", ""])[:2]
            self._append_roll_row(str(rolls), str(kom))
        self.rolne_table.blockSignals(False)

    def _set_roll_groups(self, groups):
        self._set_roll_rows([(rolls, fmt_int_sr(kom)) for rolls, kom in groups])

    def _append_roll_row(self, rolls="", kom=""):
        r = self.rolne_table.rowCount()
        self.rolne_table.insertRow(r)
        self.rolne_table.setItem(r, 0, QTableWidgetItem(rolls))
        self.rolne_table.setItem(r, 1, QTableWidgetItem(kom))
        computed = QTableWidgetItem("")
        computed.setFlags(computed.flags() & ~Qt.ItemIsEditable)
        self.rolne_table.setItem(r, 2, computed)

    def on_add_roll_group(self):
        self.rolne_table.blockSignals(True)
        self._append_roll_row()
        self.rolne_table.blockSignals(False)

    def on_remove_roll_group(self):
        rows = sorted({i.row() for i in self.rolne_table.selectedIndexes()}, reverse=True)
        if not rows and self.rolne_table.rowCount():
            rows = [self.rolne_table.rowCount() - 1]
        for r in rows:
            self.rolne_table.removeRow(r)
        self.refresh_napomena_display()

    def refresh_napomena(self):
        """Propose the roll groups from the quantity, kom/rolna and the die's
        lanes (unless changed by hand), then refresh the lines."""
        try:
            kom_po_rolni = parse_int_sr(self.kom_po_rolni_edit.text())
        except ValueError:
            kom_po_rolni = None
        proposed = split_rolls(self.k_kom_naruceno, kom_po_rolni, self.k_rows_wide)
        if self._roll_groups() in ([], self._rolne_auto):
            self._set_roll_groups(proposed)
        self._rolne_auto = proposed
        self.refresh_napomena_display()

    def refresh_napomena_display(self):
        # otkucaja/rolna for each group, from the chosen die
        self.rolne_table.blockSignals(True)
        for r in range(self.rolne_table.rowCount()):
            cell = self.rolne_table.item(r, 1)
            try:
                kom = parse_int_sr(cell.text() if cell else "")
            except ValueError:
                kom = None
            otk = otkucaji(kom, self.k_stancna_mm, self.k_rows_long)
            self.rolne_table.item(r, 2).setText("" if otk is None else str(otk))
        self.rolne_table.blockSignals(False)

        # The slitting line follows, unless it was changed by hand
        self.rasecanje_edit.propose(self._rasecanje_line())

    def _rasecanje_line(self):
        caure = caure_text(
            self.caura_unutra_edit.text(), self.caura_spolja_edit.text(),
            self.caura_sirina_edit.text(),
        )
        return rasecanje_text(
            caure, self._roll_groups(),
            self.k_stancna_mm, self.k_rows_long, self.max_d_edit.text(),
        )

    def napomena_full_text(self):
        """NAPOMENA as the order has it: slitting, unwinding, then the rest."""
        return napomena_text(
            self.rasecanje_edit.text(),
            self.odmotavanje_edit.text(),
            self.napomena_ostalo_edit.toPlainText(),
        )

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
            "stampa":                self.stampa_edit.text().strip() or None,
            "napred_slovo":          self.napred_slovo_edit.text().strip() or None,
            "napred_naziv":          self.napred_naziv_edit.text().strip() or None,
            "alati":                 self.alati_nalog_edit.text().strip() or None,
            "opis":                  self.opis_edit.toPlainText().strip() or None,
            "napomena":              self.napomena_full_text() or None,
            # every field as it is now, to reopen this order as saved
            "form_state":            self.form_state(),
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

            self._saved_state = self.form_state()
            QMessageBox.information(self, "Saved", f"Saved document #{res['doc_number']}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    # ------------------------------------------------------------------
    # The whole form, saved with an order and reopened from it
    # ------------------------------------------------------------------

    def form_state(self) -> dict:
        """Every field of the form, to reopen this order exactly as it is now."""
        return {
            "version": 1,
            "masina": self.machine_cb.currentText(),
            "sifra": self.sifra_edit.text(),
            "naziv": self.naziv_edit.text(),
            "dimenzija": self.dim_edit.text(),
            "materijal": self.mat_edit.text(),
            "sirina": self.sirina_edit.text(),
            "narucilac": self.narucilac_edit.text(),
            "customer_id": self.selected_customer_id,
            "material_id": self.selected_material_id,
            "alat": copy.deepcopy(self.chosen_tool),
            "kolicina": {
                "kom": self.kolicina_kom_input.text(),
                "stancna_mm": self.k_stancna_mm,
                "rows_long": self.k_rows_long,
                "rows_wide": self.k_rows_wide,
                "broj_zuba": self.k_broj_zuba,
                "note": self.k_note,
            },
            "rok_isporuke": self.rok_edit.date().toString(Qt.ISODate),
            "boje": copy.deepcopy(self.color_rows),
            "probni_datum": self.probni_datum_edit.date().toString(Qt.ISODate),
            "stampa": self.stampa_edit.text(),
            "napred_slovo": self.napred_slovo_edit.text(),
            "napred_naziv": self.napred_naziv_edit.text(),
            "alati": self.alati_nalog_edit.text(),
            "opis": self.opis_edit.toPlainText(),
            "napomena": {
                "caura_unutra": self.caura_unutra_edit.text(),
                "caura_spolja": self.caura_spolja_edit.text(),
                "caura_sirina": self.caura_sirina_edit.text(),
                "max_d": self.max_d_edit.text(),
                "kom_po_rolni": self.kom_po_rolni_edit.text(),
                "rolne": self._roll_rows(),
                "rasecanje": self.rasecanje_edit.text(),
                "odmotavanje": self.odmotavanje_edit.text(),
                "ostalo": self.napomena_ostalo_edit.toPlainText(),
            },
        }

    def apply_form_state(self, state: dict):
        """Fill the form from a saved order. What was saved wins over what the
        form would propose now; such a text counts as changed by hand."""
        nap = state.get("napomena") or {}
        kol = state.get("kolicina") or {}

        idx = self.machine_cb.findText(state.get("masina") or "", Qt.MatchFixedString)
        if idx >= 0:
            self.machine_cb.setCurrentIndex(idx)
        for edit, text in (
            (self.sifra_edit,        state.get("sifra")),
            (self.naziv_edit,        state.get("naziv")),
            (self.dim_edit,          state.get("dimenzija")),
            (self.mat_edit,          state.get("materijal")),
            (self.sirina_edit,       state.get("sirina")),
            (self.narucilac_edit,    state.get("narucilac")),
            (self.napred_slovo_edit, state.get("napred_slovo")),
            (self.napred_naziv_edit, state.get("napred_naziv")),
            (self.caura_unutra_edit, nap.get("caura_unutra")),
            (self.caura_spolja_edit, nap.get("caura_spolja")),
            (self.caura_sirina_edit, nap.get("caura_sirina")),
            (self.max_d_edit,        nap.get("max_d")),
            (self.kom_po_rolni_edit, nap.get("kom_po_rolni")),
        ):
            edit.setText(text or "")
        self._autofilled = {}   # the order's values are not from the catalogue
        self.selected_customer_id = state.get("customer_id")
        self.selected_material_id = state.get("material_id")

        self.chosen_tool = copy.deepcopy(state.get("alat"))
        self.selected_tool_id = self.chosen_tool.get("id") if self.chosen_tool else None
        self.alati_chosen.setText(alati_filter.summary(self.chosen_tool) if self.chosen_tool else "")
        self.alati_search.table.hide()

        self.k_stancna_mm = kol.get("stancna_mm")
        self.k_rows_long = kol.get("rows_long")
        self.k_rows_wide = kol.get("rows_wide")
        self.k_broj_zuba = kol.get("broj_zuba")
        self.k_note = kol.get("note") or ""
        self.kolicina_kom_input.setText(kol.get("kom") or "")
        self.recompute_kolicina_display()   # the die may differ though the number does not

        for edit, iso in (
            (self.rok_edit,          state.get("rok_isporuke")),
            (self.probni_datum_edit, state.get("probni_datum")),
        ):
            day = QDate.fromString(iso or "", Qt.ISODate)
            if day.isValid():
                edit.setDate(day)

        self.color_rows = copy.deepcopy(state.get("boje") or [])
        self.refresh_colors_preview()
        self.opis_edit.setPlainText(state.get("opis") or "")
        self.napomena_ostalo_edit.setPlainText(nap.get("ostalo") or "")
        self.load_series(self.sifra_edit.text().strip())
        self.alati_nalog_edit.propose(self._alati_proposal())

        # Last, what can differ from the proposals made on the way here
        self._set_roll_rows(nap.get("rolne") or [])
        self.refresh_napomena_display()
        self.alati_nalog_edit.set_text(state.get("alati") or "")
        self.stampa_edit.set_text(state.get("stampa") or "")
        self.rasecanje_edit.set_text(nap.get("rasecanje") or "")
        self.odmotavanje_edit.set_text(nap.get("odmotavanje") or "")

    def on_open_nalog(self):
        num, ok = QInputDialog.getInt(
            self, "Otvori nalog", "Broj naloga:", int(self.doc_number or 1), 1, 2147483647
        )
        if ok:
            self.open_document(num)

    def open_document(self, num):
        """Reopen an order in the form as it was saved from it."""
        try:
            r = requests.get(url(f"/documents/form/{int(num)}"), headers=headers(), timeout=5)
            if r.status_code == 404:
                QMessageBox.warning(
                    self, "Otvori nalog",
                    f"Nalog {num} nije sačuvan iz forme, pa nema šta da se otvori.",
                )
                return
            r.raise_for_status()
            state = r.json()["form_state"]
        except Exception as e:
            QMessageBox.critical(self, "Otvori nalog", str(e))
            return

        if self.form_state() != self._saved_state:
            answer = QMessageBox.question(
                self, "Nesačuvane izmene",
                f"Izmene u formi koje nisu sačuvane biće izgubljene. Otvoriti nalog {num}?",
            )
            if answer != QMessageBox.Yes:
                return

        self.doc_number = int(num)
        self.title_lbl.setText(f"NALOG ZA PROIZVODNJU {num}")
        self.apply_form_state(state)
        self._saved_state = self.form_state()


# ---------------------------------------------------------------------------
# ProposedText – an editable line the form fills in until the user changes it
# ---------------------------------------------------------------------------

class ProposedText(QWidget):
    """An editable text that follows a proposal until it is changed by hand.

    propose() replaces the text only while it still is the previous
    proposal; a text typed or changed by hand stays, an emptied one too.
    The "Auto" button, enabled while the two differ, puts the proposal back.
    """

    def __init__(self, lines=1, placeholder=""):
        super().__init__()
        self._proposed = ""

        self.edit = QLineEdit() if lines == 1 else QPlainTextEdit()
        self.edit.setPlaceholderText(placeholder)
        if lines > 1:
            self.edit.setFixedHeight(self.edit.fontMetrics().lineSpacing() * lines + 12)
        self.edit.textChanged.connect(self._update_auto_btn)

        self.auto_btn = QPushButton("Auto")
        self.auto_btn.setToolTip("Vrati automatski tekst")
        self.auto_btn.setFixedWidth(self.auto_btn.fontMetrics().horizontalAdvance("Auto") + 24)
        self.auto_btn.setEnabled(False)
        self.auto_btn.clicked.connect(lambda: self.set_text(self._proposed))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.auto_btn, 0, Qt.AlignTop)

    def text(self) -> str:
        if isinstance(self.edit, QLineEdit):
            return self.edit.text()
        return self.edit.toPlainText()

    def set_text(self, text: str):
        if text != self.text():   # setting the same text would still move the cursor
            if isinstance(self.edit, QLineEdit):
                self.edit.setText(text)
            else:
                self.edit.setPlainText(text)
        self._update_auto_btn()

    def propose(self, text: str, force=False):
        """Take a new proposal. `force` also replaces a text changed by hand."""
        follows = force or self.text() == self._proposed
        self._proposed = text
        if follows:
            self.set_text(text)
        self._update_auto_btn()

    def _update_auto_btn(self):
        self.auto_btn.setEnabled(self.text() != self._proposed)


# ---------------------------------------------------------------------------
# AlatiSearch – the die catalogue with a search field per column
# ---------------------------------------------------------------------------

class _NumberItem(QTableWidgetItem):
    """A table cell that sorts as a number."""

    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except ValueError:
            return self.text() < other.text()


class AlatiSearch(QWidget):
    """One search field per column above the table of dies; a die must fit
    every field that is filled in. Double-clicking a die emits `chosen`.

    collapsed: the table stays hidden until a field is clicked or typed in,
    and hides again once a die is chosen or Esc is pressed (for the form,
    where the table would take too much room). The catalogue is loaded on
    first use unless `rows` is given.
    """

    chosen = Signal(dict)

    # Relative column widths, in the order of alati_filter.COLUMNS: the two
    # die codes need the most room
    _SHARES = (4, 5, 2, 2, 2, 3, 2)

    def __init__(self, parent=None, rows=None, collapsed=False):
        super().__init__(parent)
        self._rows = None if rows is None else list(rows)
        self._shown = []
        self._collapsed = collapsed

        # The fields are placed by hand (see resizeEvent), each above its column
        self.filters = {}   # row key -> its search field
        self._filter_bar = QWidget()
        self._filter_bar.setFixedHeight(QLineEdit().sizeHint().height())
        for header, key, _kind in alati_filter.COLUMNS:
            edit = QLineEdit(self._filter_bar)
            edit.setPlaceholderText(header)
            edit.setClearButtonEnabled(True)
            edit.textChanged.connect(lambda _: self.filter_timer.start())
            edit.installEventFilter(self)
            self.filters[key] = edit

        # Refill the table once typing pauses, not on every key
        self.filter_timer = QTimer(self)
        self.filter_timer.setInterval(150)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.apply_filters)

        self.table = QTableWidget(0, len(alati_filter.COLUMNS))
        self.table.setHorizontalHeaderLabels([header for header, _key, _kind in alati_filter.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._on_double_click)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._filter_bar)
        layout.addWidget(self.table)

        if collapsed:
            self.table.hide()
        else:
            self.apply_filters()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Share the width between the columns and put each field above its own
        frame = self.table.frameWidth()
        room = max(self.width() - 2 * frame - self.table.verticalScrollBar().sizeHint().width(), 0)
        x = frame
        edits = list(self.filters.values())
        for col, (edit, share) in enumerate(zip(edits, self._SHARES)):
            width = room * share // sum(self._SHARES)
            if edit is edits[-1]:
                width = frame + room - x   # the last one takes what rounding left
            self.table.setColumnWidth(col, width)
            edit.setGeometry(x, 0, width, self._filter_bar.height())
            x += width

    def eventFilter(self, obj, event):
        if self._collapsed:
            # A click opens the table; tabbing through the form does not
            if event.type() == QEvent.MouseButtonPress and self.table.isHidden():
                self.apply_filters()
            elif event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.table.hide()
        return super().eventFilter(obj, event)

    def apply_filters(self):
        """Show the dies that fit the search fields (loading them if needed)."""
        if self._rows is None:
            try:
                self._rows = get_json("/lookup/tools", {"q": "", "limit": 5000})
            except Exception as e:
                QMessageBox.critical(self, "ALATI error", str(e))
                return
        typed = {key: edit.text() for key, edit in self.filters.items()}
        self._shown = [row for row in self._rows if alati_filter.matches(row, typed)]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._shown))
        for i, row in enumerate(self._shown):
            for col, (_header, key, kind) in enumerate(alati_filter.COLUMNS):
                cell = _NumberItem if kind == "number" else QTableWidgetItem
                item = cell(alati_filter.cell_text(row, key))
                item.setData(Qt.UserRole, i)   # original index: rows move when sorted
                self.table.setItem(i, col, item)
        self.table.setSortingEnabled(True)
        self.table.show()

    def _on_double_click(self, row, _column):
        item = self.table.item(row, 0)
        if not item:
            return
        index = item.data(Qt.UserRole)
        if index is None or int(index) >= len(self._shown):
            return
        if self._collapsed:
            self.table.hide()
        self.chosen.emit(self._shown[int(index)])


# ---------------------------------------------------------------------------
# AlatiDialog – the die search in a large window
# ---------------------------------------------------------------------------

class AlatiDialog(QDialog):
    def __init__(self, parent=None, rows=None):
        super().__init__(parent)
        self.setWindowTitle("ALATI search")
        self.resize(1100, 600)

        self.selected_row_data = None

        self.search = AlatiSearch(self, rows=rows or [])
        self.search.chosen.connect(self._on_chosen)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(btn_close)

        layout = QVBoxLayout()
        layout.addWidget(self.search)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

    def _on_chosen(self, row):
        self.selected_row_data = row
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
        self.open_in_form = False   # reopen the chosen order, not start a repeat of it

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
        btn_open.setToolTip("Otvori Word fajl naloga")
        btn_open.clicked.connect(self.on_open_document)
        btn_fill = QPushButton("Popuni formu")
        btn_fill.setToolTip("Novi nalog na osnovu ovog (ponovljeni posao)")
        btn_fill.clicked.connect(self.on_fill_form)
        btn_reopen = QPushButton("Otvori u formi")
        btn_reopen.setToolTip("Otvori ovaj nalog u formi onako kako je sačuvan")
        btn_reopen.clicked.connect(self.on_open_in_form)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.status_lbl, 1)
        bottom_row.addWidget(btn_open)
        bottom_row.addWidget(btn_fill)
        bottom_row.addWidget(btn_reopen)

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

    def on_open_in_form(self):
        if self._selected():
            self.open_in_form = True
            self.on_fill_form()


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