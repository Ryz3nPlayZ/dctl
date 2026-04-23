# Office Guide

`dctl` has two different office paths:

1. live office-app control through LibreOffice UNO
2. direct file-model editing through `docx` and `xlsx`

Use the file-model path whenever the format is known and the task is about the document itself.

Use LibreOffice when the agent needs the live application.

## LibreOffice on Linux

Start the office bridge:

```bash
python3 -m dctl libreoffice start --headless
```

Then open or inspect documents:

```bash
python3 -m dctl libreoffice open report.docx
python3 -m dctl libreoffice info <DOCUMENT>
python3 -m dctl libreoffice writer-text <DOCUMENT>
python3 -m dctl libreoffice calc-sheets <DOCUMENT>
```

Live Writer commands:

```bash
python3 -m dctl libreoffice writer-paragraphs <DOCUMENT>
python3 -m dctl libreoffice writer-append <DOCUMENT> "New paragraph"
python3 -m dctl libreoffice writer-set-paragraph <DOCUMENT> 3 "Replacement text"
```

Live Calc commands:

```bash
python3 -m dctl libreoffice calc-read <DOCUMENT> Sheet1 A1:D10
python3 -m dctl libreoffice calc-write-cell <DOCUMENT> Sheet1 B2 42
python3 -m dctl libreoffice calc-write-range <DOCUMENT> Sheet1 A1:B2 '[["A","B"],["1","2"]]'
```

## DOCX File Editing

`dctl docx` is the direct `.docx` editor.

Use it when:

- you want structure-aware edits
- you want to preserve formatting
- you want to avoid GUI typing
- you want predictable output for an agent

Useful commands:

```bash
python3 -m dctl docx read paper.docx
python3 -m dctl docx paragraphs paper.docx
python3 -m dctl docx worksheet-map paper.docx
python3 -m dctl docx answer-question paper.docx --question "What is..." --answer "..."
python3 -m dctl docx answer-all paper.docx answers.json
python3 -m dctl docx fill-table paper.docx --table "Questions" entries.json
```

### Worksheet-style DOCX files

For worksheet-like documents, `dctl docx` can:

- find likely questions
- insert an answer directly below the question
- preserve the question formatting
- keep answers in a consistent style
- fill tables by semantic row and column labels

This is the right path for forms, homework sheets, and rubric-style documents.

## XLSX File Editing

`dctl xlsx` is the direct `.xlsx` editor.

Useful commands:

```bash
python3 -m dctl xlsx sheets sheet.xlsx
python3 -m dctl xlsx read sheet.xlsx Sheet1 A1:D10
python3 -m dctl xlsx worksheet-map sheet.xlsx
python3 -m dctl xlsx locate-cell sheet.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number"
python3 -m dctl xlsx fill-cell sheet.xlsx Sheet1 --row-label "Oxygen" --column-label "Atomic Number" --value 8
python3 -m dctl xlsx fill-table sheet.xlsx Sheet1 entries.json
```

### Worksheet-style spreadsheets

Use the semantic helpers when the spreadsheet has:

- a header row
- labeled rows
- repeated answer cells
- table-like sections

That is the right path for:

- forms
- data-entry sheets
- gradebooks
- spreadsheet worksheets with prompts and answer columns

## Practical Decision Tree

Use this order:

1. `docx` or `xlsx` if the file format is known.
2. `libreoffice` if the live application matters.
3. `browser` if the content lives in Google Docs, Google Sheets, or another web app.
4. desktop controls only if none of the above expose enough structure.

## Safety Rules

For office editing:

- prefer direct structure edits over GUI typing
- create backups before mutating when the command supports it
- verify the changed text or cell range after every write
- do not rely on document previews alone

