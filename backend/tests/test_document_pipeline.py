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


def test_chunker_adds_neighbor_context_without_losing_provenance() -> None:
    chunker = DocumentChunker(chunk_characters=20, overlap_characters=4, context_window=1)
    chunks = chunker.chunk(
        [ParsedUnit(text="第一句内容很长。第二句内容也很长。第三句作为结尾。", page_number=3, section="计划")]
    )

    assert len(chunks) >= 2
    assert all(chunk.page_number == 3 and chunk.section == "计划" for chunk in chunks)
    assert len(chunks[0].context_text) >= len(chunks[0].content)


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
