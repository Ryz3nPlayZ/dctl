from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from docx import Document

from dctl.adapters import docx_files


class DocxAdapterTests(unittest.TestCase):
    def test_append_and_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.docx"
            document = Document()
            document.add_paragraph("hello world")
            document.save(path)

            docx_files.append(str(path), "second paragraph")
            replace_result = docx_files.replace(str(path), "world", "planet")
            read_result = docx_files.read(str(path))

            self.assertEqual(replace_result["replacements"], 1)
            self.assertIn("hello planet", read_result["paragraphs"])
            self.assertIn("second paragraph", read_result["paragraphs"])

    def test_insert_before_and_set_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.docx"
            document = Document()
            document.add_paragraph("alpha")
            document.add_paragraph("omega")
            document.save(path)

            docx_files.insert_before(str(path), 1, "middle")
            docx_files.set_paragraph(str(path), 0, "start")
            result = docx_files.paragraphs(str(path))

            self.assertEqual(result["items"][0]["text"], "start")
            self.assertEqual(result["items"][1]["text"], "middle")
            self.assertEqual(result["items"][2]["text"], "omega")


if __name__ == "__main__":
    unittest.main()
