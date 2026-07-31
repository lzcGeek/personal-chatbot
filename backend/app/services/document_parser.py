import re
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pdfplumber
from docx import Document as DocxDocument
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
SUPPORTED_MEDIA_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedUnit:
    text: str
    page_number: int | None = None
    section: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class DocumentParser:
    def __init__(self, mode: str = "auto") -> None:
        normalized = mode.strip().lower()
        if normalized not in {"auto", "layout"}:
            raise ValueError("PDF parser mode must be 'auto' or 'layout'")
        self.mode = normalized

    @staticmethod
    def validate(filename: str, media_type: str | None) -> str:
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError("Supported document types are PDF, DOCX, TXT and Markdown")
        if media_type and media_type not in SUPPORTED_MEDIA_TYPES:
            raise ValueError("File content type is not supported")
        return ".md" if extension == ".markdown" else extension

    def parse(self, path: Path, extension: str) -> list[ParsedUnit]:
        if extension == ".pdf":
            units = self._parse_pdf(path)
        elif extension == ".docx":
            units = self._parse_docx(path)
        elif extension in {".md", ".markdown"}:
            units = self._parse_markdown(path)
        else:
            units = self._parse_text(path)
        units = [replace(unit, text=unit.text.replace("\x00", "")) for unit in units]
        if not units or not any(unit.text.strip() for unit in units):
            raise ValueError("No extractable text was found in the document")
        return units

    def _parse_pdf(self, path: Path) -> list[ParsedUnit]:
        reader = PdfReader(str(path))
        if self.mode == "layout":
            return self._layout_units(reader)

        try:
            plumber_document = pdfplumber.open(str(path))
        except Exception:
            logger.exception("pdfplumber could not open PDF; using pypdf layout fallback")
            return self._layout_units(reader)

        units: list[ParsedUnit] = []
        with plumber_document as plumber_pdf:
            for index, page in enumerate(reader.pages):
                page_number = index + 1
                page_text, fallback_parser = self._pypdf_page_text(page)
                if index >= len(plumber_pdf.pages):
                    if page_text:
                        units.append(
                            self._text_unit(page_text, page_number, fallback_parser)
                        )
                    continue

                plumber_page = plumber_pdf.pages[index]
                if not page_text:
                    page_text = self._pdfplumber_text(plumber_page)
                    fallback_parser = "pdfplumber_text_fallback"
                if not page_text:
                    continue

                if not self._looks_like_table(page_text):
                    units.append(self._text_unit(page_text, page_number, fallback_parser))
                    continue
                try:
                    page_units = self._table_aware_page(
                        plumber_page,
                        page_number,
                        page_text,
                        fallback_parser,
                    )
                except Exception:
                    logger.exception(
                        "Table extraction failed for PDF page %s; using page text fallback",
                        page_number,
                    )
                    page_units = [
                        self._text_unit(page_text, page_number, fallback_parser)
                    ]
                units.extend(page_units)
        return units

    @staticmethod
    def _looks_like_table(layout_text: str) -> bool:
        """Cheap, domain-neutral prefilter before pdfplumber's geometry scan."""
        aligned_lines = 0
        numeric_aligned_lines = 0
        for line in layout_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            columns = [value for value in re.split(r"\s{2,}", stripped) if value]
            if len(columns) < 2:
                continue
            aligned_lines += 1
            if any(re.search(r"\d", value) for value in columns):
                numeric_aligned_lines += 1
        return aligned_lines >= 3 and (
            numeric_aligned_lines >= 2 or aligned_lines >= 6
        )

    @classmethod
    def _layout_units(cls, reader: PdfReader) -> list[ParsedUnit]:
        units: list[ParsedUnit] = []
        for index, page in enumerate(reader.pages):
            text, parser = cls._pypdf_page_text(page)
            if text:
                units.append(cls._text_unit(text, index + 1, parser))
        return units

    @classmethod
    def _pypdf_page_text(cls, page: Any) -> tuple[str, str]:
        layout_text = cls._layout_text(page)
        if layout_text:
            return layout_text, "pypdf_layout"
        plain_text = cls._plain_text(page)
        if plain_text:
            return plain_text, "pypdf_plain_fallback"
        return "", "pypdf_plain_fallback"

    @staticmethod
    def _layout_text(page: Any) -> str:
        return (
            page.extract_text(
                extraction_mode="layout",
                layout_mode_space_vertically=False,
            )
            or ""
        ).strip()

    @staticmethod
    def _plain_text(page: Any) -> str:
        return (page.extract_text() or "").strip()

    @staticmethod
    def _pdfplumber_text(page: Any) -> str:
        layout_text = (page.extract_text(layout=True) or "").strip()
        if layout_text:
            return layout_text
        return (page.extract_text() or "").strip()

    @staticmethod
    def _text_unit(text: str, page_number: int, parser: str) -> ParsedUnit:
        return ParsedUnit(
            text=text,
            page_number=page_number,
            metadata={"content_type": "text", "parser": parser},
        )

    @classmethod
    def _table_aware_page(
        cls,
        page: Any,
        page_number: int,
        text_fallback: str,
        fallback_parser: str,
    ) -> list[ParsedUnit]:
        tables = []
        for table in page.find_tables():
            rows = cls._normalized_table(table.extract())
            if rows is not None:
                tables.append((table, rows))

        if not tables:
            return (
                [cls._text_unit(text_fallback, page_number, fallback_parser)]
                if text_fallback
                else []
            )

        table_boxes = [tuple(float(value) for value in table.bbox) for table, _ in tables]

        def outside_tables(obj: dict[str, Any]) -> bool:
            if obj.get("object_type") != "char":
                return True
            center_x = (float(obj.get("x0", 0)) + float(obj.get("x1", 0))) / 2
            center_y = (float(obj.get("top", 0)) + float(obj.get("bottom", 0))) / 2
            return not any(
                x0 <= center_x <= x1 and top <= center_y <= bottom
                for x0, top, x1, bottom in table_boxes
            )

        filtered = page.filter(outside_tables)
        body_text = (filtered.extract_text(layout=True) or "").strip()
        units: list[ParsedUnit] = []
        if body_text:
            units.append(cls._text_unit(body_text, page_number, "pdfplumber_layout"))

        for table_index, (table, rows) in enumerate(tables, start=1):
            markdown = cls._table_markdown(rows)
            units.append(
                ParsedUnit(
                    text=markdown,
                    page_number=page_number,
                    metadata={
                        "content_type": "table",
                        "parser": "pdfplumber",
                        "table_id": f"page-{page_number}-table-{table_index}",
                        "table_index": table_index,
                        "row_count": max(0, len(rows) - 1),
                        "column_count": len(rows[0]),
                        "columns": rows[0],
                        "bbox": [round(float(value), 3) for value in table.bbox],
                    },
                )
            )
        return units

    @classmethod
    def _normalized_table(cls, raw_rows: Any) -> list[list[str]] | None:
        if not isinstance(raw_rows, list):
            return None
        rows: list[list[str]] = []
        width = 0
        for raw_row in raw_rows:
            if not isinstance(raw_row, (list, tuple)):
                continue
            row = [
                re.sub(r"\s+", " ", str(cell or "")).strip()
                for cell in raw_row
            ]
            if any(row):
                rows.append(row)
                width = max(width, len(row))
        if len(rows) < 2 or width < 2:
            return None
        normalized = [row + [""] * (width - len(row)) for row in rows]
        nonempty_columns = sum(any(row[index] for row in normalized) for index in range(width))
        first_column = [row[0].strip() for row in normalized if row[0].strip()]
        if first_column and all(cls._is_bullet_marker(value) for value in first_column):
            return None
        return normalized if nonempty_columns >= 2 else None

    @staticmethod
    def _is_bullet_marker(value: str) -> bool:
        compact = value.strip().lower().rstrip(".)、")
        return compact in {"•", "·", "▪", "◦", "‣", "-", "–", "—"}

    @staticmethod
    def _table_markdown(rows: list[list[str]]) -> str:
        def escape(value: str) -> str:
            return value.replace("|", "\\|").replace("\n", "<br>")

        header = "| " + " | ".join(escape(value) for value in rows[0]) + " |"
        separator = "| " + " | ".join("---" for _ in rows[0]) + " |"
        body = [
            "| " + " | ".join(escape(value) for value in row) + " |"
            for row in rows[1:]
        ]
        return "\n".join([header, separator, *body])

    @staticmethod
    def _parse_docx(path: Path) -> list[ParsedUnit]:
        document = DocxDocument(str(path))
        units: list[ParsedUnit] = []
        section: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                units.append(ParsedUnit(text="\n".join(buffer), section=section))
                buffer.clear()

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                flush()
                section = text
            else:
                buffer.append(text)
        flush()
        return units

    @staticmethod
    def _parse_markdown(path: Path) -> list[ParsedUnit]:
        text = DocumentParser._read_text(path)
        units: list[ParsedUnit] = []
        section: str | None = None
        buffer: list[str] = []
        for line in text.splitlines():
            heading = re.match(r"^#{1,6}\s+(.+)$", line.strip())
            if heading:
                if buffer:
                    units.append(ParsedUnit(text="\n".join(buffer).strip(), section=section))
                    buffer.clear()
                section = heading.group(1).strip()
            else:
                buffer.append(line)
        if buffer:
            units.append(ParsedUnit(text="\n".join(buffer).strip(), section=section))
        return [unit for unit in units if unit.text]

    @staticmethod
    def _parse_text(path: Path) -> list[ParsedUnit]:
        return [ParsedUnit(text=DocumentParser._read_text(path).strip())]

    @staticmethod
    def _read_text(path: Path) -> str:
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Text document encoding is not supported")
