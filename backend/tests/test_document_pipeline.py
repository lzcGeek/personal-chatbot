import hashlib
import io
import uuid

import pytest
from fastapi import UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.document_chunker import DocumentChunker
from app.services.document_parser import DocumentParser, ParsedUnit
from app.services.document_storage import DocumentStorage


def test_markdown_parser_preserves_section_provenance(tmp_path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# 项目背景\n这是背景内容。\n\n## 决策\n使用混合检索。", encoding="utf-8")

    units = DocumentParser().parse(path, ".md")

    assert [unit.section for unit in units] == ["项目背景", "决策"]
    assert "混合检索" in units[1].text


def test_pdf_parser_preserves_page_number(tmp_path) -> None:
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Personal knowledge) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)

    units = DocumentParser().parse(path, ".pdf")

    assert units[0].page_number == 1
    assert "Personal knowledge" in units[0].text


def test_pdf_parser_extracts_tables_without_duplicating_table_text(tmp_path) -> None:
    path = tmp_path / "table.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    commands = [
        "0.5 w",
        *(f"72 {y} m 330 {y} l S" for y in (720, 690, 660, 630)),
        *(f"{x} 630 m {x} 720 l S" for x in (72, 180, 255, 330)),
        "BT /F1 10 Tf",
        "1 0 0 1 72 760 Tm (Quarterly report) Tj",
        "1 0 0 1 82 700 Tm (Item) Tj",
        "1 0 0 1 190 700 Tm (2024) Tj",
        "1 0 0 1 265 700 Tm (2023) Tj",
        "1 0 0 1 82 670 Tm (Revenue) Tj",
        "1 0 0 1 190 670 Tm (120) Tj",
        "1 0 0 1 265 670 Tm (100) Tj",
        "1 0 0 1 82 640 Tm (Cost) Tj",
        "1 0 0 1 190 640 Tm (70) Tj",
        "1 0 0 1 265 640 Tm (60) Tj ET",
    ]
    stream.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)

    units = DocumentParser().parse(path, ".pdf")

    text_units = [unit for unit in units if unit.metadata.get("content_type") == "text"]
    table_units = [unit for unit in units if unit.metadata.get("content_type") == "table"]
    assert len(table_units) == 1
    assert "| Item | 2024 | 2023 |" in table_units[0].text
    assert "| Revenue | 120 | 100 |" in table_units[0].text
    assert table_units[0].metadata["row_count"] == 2
    assert table_units[0].metadata["column_count"] == 3
    assert table_units[0].metadata["parser"] == "pdfplumber"
    assert text_units and "Quarterly report" in text_units[0].text
    assert "Revenue" not in text_units[0].text


def test_pdf_layout_mode_skips_table_extraction(tmp_path) -> None:
    path = tmp_path / "layout.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Layout fallback) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)

    units = DocumentParser(mode="layout").parse(path, ".pdf")

    assert len(units) == 1
    assert units[0].metadata == {"content_type": "text", "parser": "pypdf_layout"}


def test_pdf_parser_falls_back_when_layout_extraction_is_empty(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "plain-fallback.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 72 720 Td "
        b"(Securities registered pursuant to Section 12b) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)

    monkeypatch.setattr(DocumentParser, "_layout_text", staticmethod(lambda page: ""))

    units = DocumentParser().parse(path, ".pdf")

    assert len(units) == 1
    assert "Securities registered" in units[0].text
    assert units[0].page_number == 1
    assert units[0].metadata == {
        "content_type": "text",
        "parser": "pypdf_plain_fallback",
    }

    monkeypatch.setattr(DocumentParser, "_plain_text", staticmethod(lambda page: ""))

    plumber_units = DocumentParser().parse(path, ".pdf")

    assert len(plumber_units) == 1
    assert "Securities registered" in plumber_units[0].text
    assert plumber_units[0].metadata == {
        "content_type": "text",
        "parser": "pdfplumber_text_fallback",
    }


def test_pdf_table_normalization_rejects_bullet_lists() -> None:
    rows = DocumentParser._normalized_table(  # noqa: SLF001
        [["•", "First list item"], ["•", "Second list item"]]
    )

    assert rows is None


def test_parser_removes_postgres_incompatible_null_characters(tmp_path) -> None:
    path = tmp_path / "null-byte.txt"
    path.write_bytes(b"before\x00after")

    units = DocumentParser().parse(path, ".txt")

    assert units[0].text == "beforeafter"


def test_chunker_adds_neighbor_context_without_losing_provenance() -> None:
    chunker = DocumentChunker(chunk_characters=20, overlap_characters=4, context_window=1)
    chunks = chunker.chunk(
        [ParsedUnit(text="第一句内容很长。第二句内容也很长。第三句作为结尾。", page_number=3, section="计划")]
    )

    assert len(chunks) >= 2
    assert all(chunk.page_number == 3 and chunk.section == "计划" for chunk in chunks)
    assert len(chunks[0].context_text) >= len(chunks[0].content)


def test_chunker_merges_short_paragraphs_before_embedding() -> None:
    chunker = DocumentChunker(
        chunk_characters=100,
        overlap_characters=20,
        context_window=0,
    )
    text = "\n\n".join(f"table-cell-{index:02d}" for index in range(30))

    chunks = chunker.chunk([ParsedUnit(text=text, page_number=7)])

    assert len(chunks) < 10
    assert all(chunk.page_number == 7 for chunk in chunks)
    assert all(len(chunk.content) <= 100 for chunk in chunks)
    assert all(f"table-cell-{index:02d}" in "\n".join(c.content for c in chunks) for index in range(30))


def test_chunker_repeats_markdown_table_header_for_each_chunk() -> None:
    chunker = DocumentChunker(
        chunk_characters=120,
        overlap_characters=20,
        context_window=0,
    )
    header = "| Item | 2024 | 2023 |\n| --- | --- | --- |"
    rows = "\n".join(
        f"| metric-{index} | {100 + index} | {90 + index} |"
        for index in range(10)
    )
    chunks = chunker.chunk(
        [
            ParsedUnit(
                text=f"{header}\n{rows}",
                page_number=9,
                metadata={"content_type": "table", "table_id": "page-9-table-1"},
            )
        ]
    )

    assert len(chunks) > 1
    assert all("| Item | 2024 | 2023 |" in chunk.content for chunk in chunks)
    assert all(len(chunk.content) <= 120 for chunk in chunks)
    joined = "\n".join(chunk.content for chunk in chunks)
    assert all(f"metric-{index}" in joined for index in range(10))
    assert all(chunk.metadata["content_type"] == "table" for chunk in chunks)


@pytest.mark.asyncio
async def test_storage_hashes_upload_and_deletes_only_document_directory(tmp_path) -> None:
    storage = DocumentStorage(tmp_path / "documents", max_upload_bytes=1024)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    content = b"private notes"
    upload = UploadFile(filename="notes.txt", file=io.BytesIO(content))

    stored = await storage.save_upload(upload, user_id, document_id, ".txt")

    assert stored.path.read_bytes() == content
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    storage.delete(user_id, document_id)
    assert not stored.path.exists()


@pytest.mark.asyncio
async def test_storage_rejects_oversized_upload_and_cleans_partial_file(tmp_path) -> None:
    storage = DocumentStorage(tmp_path / "documents", max_upload_bytes=3)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    upload = UploadFile(filename="large.txt", file=io.BytesIO(b"too large"))

    with pytest.raises(ValueError, match="upload limit"):
        await storage.save_upload(upload, user_id, document_id, ".txt")

    assert not (storage.root / str(user_id) / str(document_id)).exists()
