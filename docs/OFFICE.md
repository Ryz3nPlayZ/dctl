# Office Guide

`dctl` provides three paths for office document work:

1. **Direct DOCX editing** via python-docx — for `.docx` files
2. **Direct XLSX editing** via openpyxl — for `.xlsx` files
3. **LibreOffice UNO bridge** — for live application control on Linux

Use the direct file-model path whenever the format is known. Use LibreOffice when you need the live application. Use the browser for Google Docs/Sheets.

## DOCX Editing

`dctl docx` edits `.docx` files directly, preserving formatting and structure.

### Basic Operations

```bash
dctl docx inspect paper.docx          # Document structure overview
dctl docx read paper.docx             # Full text content
dctl docx paragraphs paper.docx       # Paragraph-by-paragraph listing
```

### Editing

```bash
dctl docx append paper.docx "New paragraph"
dctl docx insert-before paper.docx 3 "Inserted text"
dctl docx set-paragraph paper.docx 3 "Replacement text"
dctl docx replace paper.docx "old text" "new text"
```

### Safety

```bash
dctl docx backup paper.docx           # Create timestamped backup
dctl docx diff paper.docx --against paper_backup.docx  # Compare versions
```

### Worksheet-Style Documents

For documents with question/answer structure, forms, or tables with labeled cells:

```bash
# Map the document's question/table structure
dctl docx worksheet-map paper.docx

# Answer a specific question
dctl docx answer-question paper.docx --question "What is photosynthesis?" --answer "Plants convert light to chemical energy."

# Answer all questions from a JSON file
dctl docx answer-all paper.docx answers.json

# Fill a table by semantic labels
dctl docx fill-table paper.docx --table "Results" entries.json
```

Use `--exact` with `answer-question` to require exact question text matching.

## XLSX Editing

`dctl xlsx` edits `.xlsx` files directly via openpyxl.

### Basic Operations

```bash
dctl xlsx inspect data.xlsx           # Workbook structure overview
dctl xlsx sheets data.xlsx            # List sheet names
dctl xlsx read data.xlsx Sheet1 A1:D10  # Read a cell range
```

### Editing

```bash
dctl xlsx write-cell data.xlsx Sheet1 B2 42
dctl xlsx write-range data.xlsx Sheet1 A1:B2 '[["A","B"],["1","2"]]'
```

### Safety

```bash
dctl xlsx backup data.xlsx
dctl xlsx diff data.xlsx --against data_backup.xlsx
```

### Worksheet-Style Spreadsheets

For spreadsheets with header rows, labeled rows, and answer columns:

```bash
# Map the spreadsheet structure
dctl xlsx worksheet-map data.xlsx --sheet Sheet1

# Find a cell by row and column labels
dctl xlsx locate-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number"

# Fill a cell by semantic labels
dctl xlsx fill-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8

# Fill multiple cells from a JSON file
dctl xlsx fill-table data.xlsx Sheet1 entries.json

# Limit to a named table within the sheet
dctl xlsx fill-cell data.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8 --table "Elements"
```

## LibreOffice UNO Bridge

Live LibreOffice control on Linux. Requires `soffice` or `libreoffice` on PATH.

### Process Control

```bash
dctl libreoffice start --headless      # Start the UNO bridge
dctl libreoffice docs                  # List open documents
dctl libreoffice open report.docx      # Open a document
dctl libreoffice info <DOCUMENT>       # Document metadata
dctl libreoffice save <DOCUMENT>       # Save changes
dctl libreoffice close <DOCUMENT>      # Close document
dctl libreoffice stop --pid <PID>      # Stop the bridge
```

### Writer Commands

```bash
dctl libreoffice writer-text <DOCUMENT>           # Full text
dctl libreoffice writer-paragraphs <DOCUMENT>     # Paragraph listing
dctl libreoffice writer-append <DOCUMENT> "Text"  # Append paragraph
dctl libreoffice writer-set-paragraph <DOCUMENT> 3 "New text"  # Replace paragraph
```

### Calc Commands

```bash
dctl libreoffice calc-sheets <DOCUMENT>                          # List sheets
dctl libreoffice calc-read <DOCUMENT> Sheet1 A1:D10              # Read range
dctl libreoffice calc-write-cell <DOCUMENT> Sheet1 B2 42         # Write cell
dctl libreoffice calc-write-range <DOCUMENT> Sheet1 A1:B2 '...'  # Write range
```

## Decision Tree

1. **`.docx` file?** Use `dctl docx`
2. **`.xlsx` file?** Use `dctl xlsx`
3. **Live LibreOffice control?** Use `dctl libreoffice`
4. **Google Docs/Sheets?** Use `dctl browser`
5. **None of the above?** Use desktop commands

## Safety Rules

- Create backups before mutating documents
- Verify changed text or cell ranges after every write
- Do not rely on document previews — inspect the actual content
- Prefer direct structure edits over GUI typing
