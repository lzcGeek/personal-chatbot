import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.document_outbox import DocumentOutbox
from app.models.user import User
from app.schemas.document import DocumentInfo, GraphMode
from app.services.auth_dependencies import get_current_user
from app.services.document_parser import DocumentParser


router = APIRouter(prefix="/api/documents", tags=["documents"])


def serialize_document(document: Document) -> DocumentInfo:
    return DocumentInfo(
        id=document.id,
        filename=document.original_filename,
        media_type=document.media_type,
        byte_size=document.byte_size,
        status=document.status,
        processing_phase=document.processing_phase,
        graph_mode=document.graph_mode,
        graph_status=document.graph_status,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("", response_model=DocumentInfo, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    graph_mode: GraphMode = Form("inherit"),
    user: User = Depends(get_current_user),
) -> DocumentInfo:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=422, detail="Filename is required")
    try:
        extension = DocumentParser.validate(filename, file.content_type)
        document_id = uuid.uuid4()
        stored = await request.app.state.document_storage.save_upload(
            file, user.id, document_id, extension
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = Document(
        id=document_id,
        user_id=user.id,
        original_filename=filename,
        media_type=file.content_type or "application/octet-stream",
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        storage_path=str(stored.path),
        embedding_model=request.app.state.settings.embedding_model,
        graph_mode=graph_mode,
        graph_status="skipped" if graph_mode == "disabled" else "pending",
    )
    try:
        async with SessionLocal() as session:
            async with session.begin():
                session.add(document)
                session.add(
                    DocumentOutbox(
                        document_id=document.id,
                        user_id=user.id,
                        operation="process_document",
                        revision=document.revision,
                    )
                )
            await session.refresh(document)
    except Exception:
        request.app.state.document_storage.delete(user.id, document_id)
        raise
    return serialize_document(document)


async def _queue_graph(
    document_id: uuid.UUID,
    user: User,
    request: Request,
    *,
    rebuild: bool,
) -> DocumentInfo:
    if request.app.state.graph_store is None or request.app.state.graph_extractor is None:
        raise HTTPException(status_code=503, detail="Knowledge graph service is unavailable")
    async with SessionLocal() as session:
        async with session.begin():
            document = (
                await session.execute(
                    select(Document)
                    .where(
                        Document.id == document_id,
                        Document.user_id == user.id,
                        Document.status == "ready",
                        Document.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if document is None:
                raise HTTPException(status_code=404, detail="Ready document not found")
            active = await session.scalar(
                select(DocumentOutbox.id).where(
                    DocumentOutbox.document_id == document.id,
                    DocumentOutbox.user_id == user.id,
                    DocumentOutbox.operation == "index_graph",
                    DocumentOutbox.revision == document.revision,
                    DocumentOutbox.status.in_(("pending", "processing")),
                )
            )
            document.graph_mode = "enabled"
            document.error_message = None
            if active is None:
                document.graph_status = "queued"
                session.add(
                    DocumentOutbox(
                        document_id=document.id,
                        user_id=user.id,
                        operation="index_graph",
                        revision=document.revision,
                    )
                )
            elif rebuild:
                document.graph_status = "queued"
        await session.refresh(document)
        return serialize_document(document)


@router.post("/{document_id}/graph/build", response_model=DocumentInfo)
async def build_document_graph(
    document_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> DocumentInfo:
    return await _queue_graph(document_id, user, request, rebuild=False)


@router.post("/{document_id}/graph/rebuild", response_model=DocumentInfo)
async def rebuild_document_graph(
    document_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> DocumentInfo:
    return await _queue_graph(document_id, user, request, rebuild=True)


@router.get("", response_model=list[DocumentInfo])
async def list_documents(user: User = Depends(get_current_user)) -> list[DocumentInfo]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Document)
            .where(Document.user_id == user.id, Document.status != "deleted")
            .order_by(Document.created_at.desc())
        )
        return [serialize_document(item) for item in result.scalars()]


@router.get("/{document_id}", response_model=DocumentInfo)
async def get_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user)
) -> DocumentInfo:
    async with SessionLocal() as session:
        document = (
            await session.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.user_id == user.id,
                    Document.status != "deleted",
                )
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return serialize_document(document)


@router.post("/{document_id}/retry", response_model=DocumentInfo)
async def retry_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user)
) -> DocumentInfo:
    async with SessionLocal() as session:
        async with session.begin():
            document = (
                await session.execute(
                    select(Document).where(
                        Document.id == document_id,
                        Document.user_id == user.id,
                        or_(Document.status == "failed", Document.graph_status == "failed"),
                    )
                )
            ).scalar_one_or_none()
            if document is None:
                raise HTTPException(status_code=404, detail="Failed document not found")
            if document.processing_phase == "delete_failed":
                document.status = "deleting"
                document.processing_phase = "deleting"
                operation = "delete_document"
            elif document.status == "ready" and document.graph_status == "failed":
                document.graph_status = "queued"
                operation = "index_graph"
            else:
                document.revision += 1
                document.status = "uploaded"
                document.processing_phase = "uploaded"
                document.graph_status = "pending"
                operation = "process_document"
            document.error_message = None
            session.add(
                DocumentOutbox(
                    document_id=document.id,
                    user_id=user.id,
                    operation=operation,
                    revision=document.revision,
                )
            )
        await session.refresh(document)
        return serialize_document(document)


@router.delete("/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_document(
    document_id: uuid.UUID, user: User = Depends(get_current_user)
) -> dict[str, str]:
    async with SessionLocal() as session:
        async with session.begin():
            document = (
                await session.execute(
                    select(Document).where(
                        Document.id == document_id,
                        Document.user_id == user.id,
                        Document.status.not_in(("deleting", "deleted")),
                    )
                )
            ).scalar_one_or_none()
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            document.status = "deleting"
            document.processing_phase = "deleting"
            session.add(
                DocumentOutbox(
                    document_id=document.id,
                    user_id=user.id,
                    operation="delete_document",
                    revision=document.revision,
                )
            )
    return {"status": "deleting"}
