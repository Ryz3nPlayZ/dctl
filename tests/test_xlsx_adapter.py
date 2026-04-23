from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from dctl.adapters import xlsx_files


class XlsxAdapterTests(unittest.TestCase):
    def test_read_and_write_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Sheet1"
            sheet["A1"] = "name"
            sheet["B1"] = "count"
            workbook.save(path)

            xlsx_files.write_cell(str(path), "Sheet1", "B2", "42", json_value=True)
            result = xlsx_files.read(str(path), "Sheet1", "A1:B2")

            self.assertEqual(result["values"], [["name", "count"], [None, 42]])

    def test_write_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.xlsx"
            workbook = Workbook()
            workbook.active.title = "Sheet1"
            workbook.save(path)

            xlsx_files.write_range(str(path), "Sheet1", "A1:B2", '[["a", 1], ["b", 2]]')
            result = xlsx_files.read(str(path), "Sheet1", "A1:B2")

            self.assertEqual(result["values"], [["a", 1], ["b", 2]])


if __name__ == "__main__":
    unittest.main()
