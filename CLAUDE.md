# Working on this project

Production-order automation for a flexographic label printer: a desktop form
(PySide6, `client/gui_production_order.py`) prepares the order, the API
(FastAPI, `server/`) stores it in PostgreSQL, and the watcher
(`server/watcher_v2_1.py`) files and parses the Word orders staff save into
the orders folder. See README.md for setup.

## Where we are

The goal is for the form to produce the Word production order, word for word
and laid out like the shop's order template. The form is being built top to
bottom in the template's order:

- done: everything down to ŠTAMPA PREMA PRIPREMI, then NAPRED IDE, ALATI
  (u nalogu), OPIS and NAPOMENA
- **next: the date and signature at the bottom** (see the template outline)
- then: generate the .docx from the form, in the template's layout

Open questions for the owner:
- date and signature: which date (today? editable?), and is a name printed
  under "Potpis," or only the dashed line for a handwritten signature?
- NAPOMENA rules taken from the template, not yet confirmed: the leftover
  pieces are rounded up to 5 per roll; otkucaja/rolna = kom/rolna × die
  circumference ÷ rows along ÷ 100 (a length in tenths of a metre)

## Decisions already made

- Every text line is built word for word as in the template (single spaces
  where the template has stray double ones). Wording lives in
  `client/order_text.py` (no Qt) and is tested in `tests/test_order_text.py`.
- The ALATI die search stays at the top of the form, because the chosen die
  fills DIMENZIJA, the quantity and the colour cylinders; the order's ALATI
  line is a separate row lower down.
- NAPRED IDE is two inputs (letter, name); the same two fill NAPOMENA's
  unwinding line.
- OPIS and the last NAPOMENA box start with standard text and are editable.
- The form saves text lines in `doc_params` (keys `napred_slovo`,
  `napred_naziv`, `alati`, `opis`, `napomena`; the watcher uses `alati`,
  `opis` and `napomena` for the same lines of the Word file). An emptied line
  is removed; fields left out of a request are not touched. No schema change.
- A line typed or changed by hand is never overwritten by an automatic
  refill (ALATI line, roll groups).
- A Word file must reproduce the template exactly, so check new output
  against the outline below.

## Template outline (fictional values)

Page 216 × 279 mm, margins left 10, right 5, top 5, bottom 3 mm. Arial,
mostly bold. Labels are padded with spaces (not tabs) so values line up, and
the top fields are separated by empty paragraphs.

```
                 NALOG ZA PROIZVODNJU 6276                (centred, bold)
MAŠINA:          Nilpeter FA2500
ŠIFRA:           DEMO-250101
NAZIV:           nalepnica Demo sok 0,5 l, P+Z            (product name part italic, 14pt)
DIMENZIJA:       65 x 140 mm
MATERIJAL:       PE WHITE
ŠIRINA:          235 mm
NARUČILAC:       Primer d.o.o., Beograd
KOLIČINA:        4930 m dobrih (100.000 kom)  (20,32 kom/m) - 3 reda
                                       ("(20,32 kom/m) - 3 reda" 11pt, not bold)
ROK ZA ISPORUKU: 24.07.2025.                              (bold italic 14pt)
ŠIFRA BOJA:
I kliše oznake 0000, C, boja Process Cyan, raster 390l/cm,         Z-93
II … M, Magenta / III … Y, Yellow / IV … K, Black (same pattern)
VIII uređaj za lakiranje, UV lak, raster 160l/cm,                  Z-88
Štampa prema pripremi, prema uzorcima odštampanim kao probni uzorak 04.04.2025.
                                       (bold italic 14pt; the date italic)
Pri štampi napred ide slovo „D“ u nazivu „Demo“.         (letter and name 14pt, name italic)
ALATI:           štancna oznake 0000, Z-93
OPIS:            Svaki nastavak rolne izvršiti precizno zbog mašinskog etiketiranja.
                 Nastavak koji je fabrički urađen zameniti, odnosno, izbaciti iz rolne.
NAPOMENA:
Raseći na čaure Ø45/Ø52/65 mm, 99 rolni x 1.000 kom/rolna-1476 otkucaja/rolna + 3 rolne x 335 kom/rolna-495 otkucaja/rolna (max. Ø150mm),
                                       (the otkucaja parts 11pt, the second roll count bold)
Pri odmotavanju gotove rolnice napred ide slovo „D“ u nazivu „Demo“.
Upakovati u kutije.
         Datum                                              Potpis,   (not bold)
      18.07.2025.                                                     (bold)
                                              --------------------------------
```

The watcher reads the date paragraph at the bottom as the order's date
(`datum_doc`) and the KOLIČINA, ALATI, OPIS and NAPOMENA lines as above.

## Rules

- Never commit real business data: no real customers, products, people, die
  codes or the shop's own order files. Use the fictional set above (Primer
  d.o.o., DEMO-…, "Demo", ABC/XYZ die codes). The real die-code prefix list
  lives only in the production `.env` (`STANCNA_PREFIXES`); `.env` is never
  committed.
- Work on a branch; the owner decides when it goes to main.
- Check changes before pushing: `pytest`, `pyflakes`, and for form changes
  drive the form headless (QT_QPA_PLATFORM=offscreen) against a test stack
  (Postgres 16 + the API) and look at a screenshot.
- After a server change, the running stack needs `docker compose restart api`
  (the code is mounted, not baked in); requirements changes need
  `docker compose up -d --build`.
