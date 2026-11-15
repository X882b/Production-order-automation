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
  (u nalogu), OPIS and NAPOMENA; the die search has one field per column
- **next: the date and signature at the bottom** (see the template outline)
- then: generate the .docx from the form, in the template's layout

Open questions for the owner:
- date and signature: which date (today? editable?), and is a name printed
  under "Potpis," or only the dashed line for a handwritten signature?
- ALATI line: real orders write two codes,
  `štancna oznake <code> (<second code>), Z-93`; the form writes only
  `oznaka_stancne`. Which catalogue column goes first, which in brackets?
- colour-row exceptions the owner wants as presets in ŠIFRA BOJA: ZLATOTISAK
  (`folija zlatna, lepakzafoliju UVH0-0007+“zlatna“ folija KFA 100 Gloss
  Gold,ras. 140l/cm,` on its own station, e.g. VII), SREBRNA and BELA (texts
  not given yet)
- NAPOMENA: the leftover pieces are rounded up to 5 per roll (seen in one
  order only)

For the .docx step: the KOLIČINA line ends with the lanes, `- 3 reda`
(`rows_wide`); the form does not write that yet.

## Decisions already made

- Every text line is built word for word as in the template (single spaces
  where the template has stray double ones). Wording lives in
  `client/order_text.py` (no Qt) and is tested in `tests/test_order_text.py`.
- RASPORED in the die catalogue is lanes across the web × labels around the
  cylinder: "3x2" is 3 lanes, 2 around. `rows_wide` is the lanes (first
  number), `rows_long` the labels around (second). The lanes drive the split
  into rolls; the labels around drive otkucaja/rolna. Orders saved before
  this was fixed have the two swapped in `documents.rows_long`/`rows_wide`;
  nothing reads those columns yet.
- otkucaja/rolna = kom/rolna × die circumference ÷ labels around ÷ 100 (the
  roll's length in tenths of a metre). Checked against the owner's real
  orders (Z-93, 2 around: 1.000 kom → 1476; Z-81, 4 around: 1.225 kom → 788).
- The ALATI die search stays at the top of the form, because the chosen die
  fills DIMENZIJA, the quantity and the colour cylinders; the order's ALATI
  line is a separate row lower down. The search has one field per column
  (`client/alati_filter.py`, no Qt): a number field finds values that start
  with what is typed, a text field values that contain it, and a die must fit
  every field filled in. The chosen die is shown on its own line.
- NAPRED IDE is two inputs (letter, name). NAPOMENA's unwinding line is
  proposed with the letter at the other end of the name (the finished roll
  unwinds the other way round) and can be edited.
- The cores are three number inputs (inner Ø, outer Ø, width); the form
  writes "Ø" and "mm" itself.
- OPIS and the last NAPOMENA box start with standard text and are editable.
- The form saves text lines in `doc_params` (keys `napred_slovo`,
  `napred_naziv`, `alati`, `opis`, `napomena`; the watcher uses `alati`,
  `opis` and `napomena` for the same lines of the Word file). An emptied line
  is removed; fields left out of a request are not touched. No schema change.
- A line typed or changed by hand is never overwritten by an automatic
  refill (ALATI line, roll groups, unwinding line).
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
Pri odmotavanju gotove rolnice napred ide slovo „o“ u nazivu „Demo“.
Upakovati u kutije.
         Datum                                              Potpis,   (not bold)
      18.07.2025.                                                     (bold)
                                              --------------------------------
```

The watcher reads the date paragraph at the bottom as the order's date
(`datum_doc`) and the KOLIČINA, ALATI, OPIS and NAPOMENA lines as above.

Real orders vary the wording by hand ("u naslovu", "na 4 rolne", "kom."),
sometimes carry a line above the title, and are edited copies of earlier
orders, so they contain leftovers. Where one disagrees with its own
quantity, ask the owner which is right before changing a formula.

## Rules

- Never commit real business data: no real customers, products, people, die
  codes or the shop's own order files. Use the fictional set above (Primer
  d.o.o., DEMO-…, "Demo", ABC/XYZ die codes). The real die-code prefix list
  lives only in the production `.env` (`STANCNA_PREFIXES`); `.env` is never
  committed. Orders the owner uploads are reference only: test with their
  numbers in the scratchpad, and keep their names out of code, tests,
  comments and commit messages.
- Work on a branch; the owner decides when it goes to main.
- Check changes before pushing: `pytest`, `pyflakes`, and for form changes
  drive the form headless (QT_QPA_PLATFORM=offscreen) against a test stack
  (Postgres 16 + the API) and look at a screenshot.
- After a server change, the running stack needs `docker compose restart api`
  (the code is mounted, not baked in); requirements changes need
  `docker compose up -d --build`. A changed schema file is applied again
  with the README's psql command (the schema files are safe to re-run).
