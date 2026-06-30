"""K6 DocumentPipeline with parent context and citations.

The canonical store is UMC (`document_memories`, `document_chunks`,
`document_vectors`). RAGFlow is optional/headless and never becomes the source of
truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
from typing import Any, Iterable

from core.database import embed_text, ensure_migrations, get_connection
from core.vector_backend import SQLiteVecBackend


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    parent_id: str
    parent_type: str
    source_uri: str
    chunk_index: int
    heading: str | None
    content: str
    offset_start: int
    offset_end: int
    hash: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    file_hash: str
    source_uri: str
    chunks_count: int
    indexed_vectors: int


class RAGFlowAdapter:
    """Optional K6 adapter. It is a health/extension point, not canonical IO."""

    def health(self) -> dict[str, Any]:
        try:
            from integrations.ragflow.client import assert_health

            return assert_health(strict=False)
        except Exception as exc:
            return {"ok": False, "service": "ragflow", "reason": str(exc)}


class DocumentPipeline:
    def __init__(self, conn=None, *, workspace_id: str = "default", adapter: str | None = None):
        self.conn = conn or get_connection()
        self.workspace_id = workspace_id
        self.adapter_name = adapter or os.environ.get("DOCUMENT_PIPELINE_ADAPTER", "local")
        ensure_migrations(self.conn)

    # -- public API -------------------------------------------------------
    def ingest(self, path: str | Path, *, project: str = "default") -> IngestResult:
        source = Path(path).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        file_hash = _sha256_bytes(source.read_bytes())
        document_id = f"doc-{file_hash[:16]}"
        source_uri = str(source)
        content_type = _content_type(source)

        parsed_text = self._parse(source)
        chunks = self._chunk_text(
            parsed_text,
            document_id=document_id,
            source_uri=source_uri,
            content_type=content_type,
        )
        if not chunks:
            fallback = f"Documento {source.name} sem texto extraivel; hash={file_hash}"
            chunks = self._chunk_text(
                fallback,
                document_id=document_id,
                source_uri=source_uri,
                content_type=content_type,
                fallback=True,
            )

        metadata = {
            "source": "document_pipeline",
            "adapter": self.adapter_name,
            "content_type": content_type,
            "original_name": source.name,
            "source_uri": source_uri,
            "workspace_id": self.workspace_id,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        self.conn.execute(
            """
            INSERT OR REPLACE INTO document_memories(
                id, file_path, file_hash, summary, topics, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                source_uri,
                file_hash,
                chunks[0].content[:500] if chunks else "",
                json.dumps([chunk.heading for chunk in chunks if chunk.heading], ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        old_ids = [
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        ]
        backend = SQLiteVecBackend(self.conn)
        for old_id in old_ids:
            backend.delete("document_vectors", old_id)
        self.conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        self.conn.execute(
            "DELETE FROM vector_metadata WHERE collection = 'document_vectors' AND parent_id = ?",
            (document_id,),
        )
        for chunk in chunks:
            self._insert_chunk(chunk)
        indexed = self._index_chunks(chunks, project=project)
        self.conn.commit()
        return IngestResult(
            document_id=document_id,
            file_hash=file_hash,
            source_uri=source_uri,
            chunks_count=len(chunks),
            indexed_vectors=indexed,
        )

    def query(self, text: str, *, top_k: int = 5, project: str | None = None) -> list[dict[str, Any]]:
        vector = embed_text(text)
        filters = {"workspace_id": self.workspace_id}
        if project:
            filters["project"] = project
        hits = SQLiteVecBackend(self.conn).query("document_vectors", vector, top_k=top_k, filters=filters)
        citations: list[dict[str, Any]] = []
        for hit in hits:
            row = self.conn.execute("SELECT * FROM document_chunks WHERE id = ?", (hit["id"],)).fetchone()
            if row is None:
                continue
            parent = self.conn.execute("SELECT * FROM document_memories WHERE id = ?", (row["document_id"],)).fetchone()
            parent_metadata = _loads(parent["metadata"] if parent else None)
            citations.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "heading": row["heading"],
                    "score": hit.get("score"),
                    "source_uri": row["source_uri"],
                    "offset_start": row["offset_start"],
                    "offset_end": row["offset_end"],
                    "parent": {
                        "id": row["parent_id"],
                        "type": row["parent_type"],
                        "source_uri": parent["file_path"] if parent else row["source_uri"],
                        "file_hash": parent["file_hash"] if parent else None,
                        "metadata": parent_metadata,
                    },
                }
            )
        return citations

    def ragflow_health(self) -> dict[str, Any]:
        return RAGFlowAdapter().health()

    # -- parsing ----------------------------------------------------------
    def _parse(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".md", ".markdown", ".txt"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".pdf":
            return _extract_pdf_text(path)
        if suffix == ".docx":
            return _extract_docx_text(path)
        raise ValueError(f"tipo documental nao suportado: {suffix}")

    def _chunk_text(
        self,
        text: str,
        *,
        document_id: str,
        source_uri: str,
        content_type: str,
        fallback: bool = False,
        max_chars: int = 1800,
    ) -> list[DocumentChunk]:
        if content_type == "text/markdown" and not fallback:
            sections = _markdown_sections(text)
        else:
            sections = [(None, 0, len(text), text)]

        chunks: list[DocumentChunk] = []
        for heading, start, end, section_text in sections:
            for piece_start, piece_end, piece in _split_section(section_text, start, max_chars=max_chars):
                content = piece.strip()
                if not content:
                    continue
                chunk_hash = _sha256(content)
                chunk_id = f"chunk-{_sha256(f'{document_id}:{piece_start}:{piece_end}:{chunk_hash}')[:24]}"
                chunks.append(
                    DocumentChunk(
                        id=chunk_id,
                        document_id=document_id,
                        parent_id=document_id,
                        parent_type="document",
                        source_uri=source_uri,
                        chunk_index=len(chunks),
                        heading=heading,
                        content=content,
                        offset_start=piece_start,
                        offset_end=piece_end,
                        hash=chunk_hash,
                        metadata={"content_type": content_type, "fallback": fallback},
                    )
                )
        return chunks

    # -- persistence ------------------------------------------------------
    def _insert_chunk(self, chunk: DocumentChunk) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO document_chunks(
                id, document_id, parent_id, parent_type, source_uri, chunk_index,
                heading, content, offset_start, offset_end, hash, metadata,
                workspace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.id,
                chunk.document_id,
                chunk.parent_id,
                chunk.parent_type,
                chunk.source_uri,
                chunk.chunk_index,
                chunk.heading,
                chunk.content,
                chunk.offset_start,
                chunk.offset_end,
                chunk.hash,
                json.dumps(chunk.metadata, ensure_ascii=False),
                self.workspace_id,
            ),
        )

    def _index_chunks(self, chunks: Iterable[DocumentChunk], *, project: str) -> int:
        backend = SQLiteVecBackend(self.conn)
        indexed = 0
        for chunk in chunks:
            metadata = {
                "parent_id": chunk.parent_id,
                "parent_type": chunk.parent_type,
                "brain_lobe": "parietal",
                "knowledge_type": "document_chunk",
                "project": project,
                "source_uri": chunk.source_uri,
                "hash": chunk.hash,
                "valid_at": datetime.now(timezone.utc).isoformat(),
                "workspace_id": self.workspace_id,
            }
            backend.upsert("document_vectors", chunk.id, embed_text(chunk.content), metadata)
            indexed += 1
        return indexed


def _content_type(path: Path) -> str:
    if path.suffix.lower() in {".md", ".markdown"}:
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "text/plain"


def _markdown_sections(text: str) -> list[tuple[str | None, int, int, str]]:
    heading_matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if not heading_matches:
        return [(None, 0, len(text), text)]
    sections: list[tuple[str | None, int, int, str]] = []
    for idx, match in enumerate(heading_matches):
        start = match.start()
        end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(text)
        heading = match.group(2).strip()
        sections.append((heading, start, end, text[start:end]))
    if heading_matches[0].start() > 0 and text[: heading_matches[0].start()].strip():
        sections.insert((0), (None, 0, heading_matches[0].start(), text[: heading_matches[0].start()]))
    return sections


def _split_section(section_text: str, absolute_start: int, *, max_chars: int) -> list[tuple[int, int, str]]:
    if len(section_text) <= max_chars:
        return [(absolute_start, absolute_start + len(section_text), section_text)]
    parts: list[tuple[int, int, str]] = []
    cursor = 0
    paragraphs = list(re.finditer(r".+?(?:\n\s*\n|\Z)", section_text, flags=re.DOTALL))
    buffer = ""
    buffer_start = 0
    for paragraph in paragraphs:
        piece = paragraph.group(0)
        if not buffer:
            buffer_start = paragraph.start()
        if buffer and len(buffer) + len(piece) > max_chars:
            parts.append((absolute_start + buffer_start, absolute_start + buffer_start + len(buffer), buffer))
            buffer = piece
            buffer_start = paragraph.start()
        else:
            buffer += piece
        cursor = paragraph.end()
    if buffer:
        parts.append((absolute_start + buffer_start, absolute_start + buffer_start + len(buffer), buffer))
    if not parts and cursor == 0:
        for idx in range(0, len(section_text), max_chars):
            part = section_text[idx : idx + max_chars]
            parts.append((absolute_start + idx, absolute_start + idx + len(part), part))
    return parts


def _extract_pdf_text(path: Path) -> str:
    errors: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if text:
            return text
        errors.append("pypdf returned empty text")
    except Exception as exc:
        errors.append(f"pypdf: {exc}")
    try:
        import fitz

        with fitz.open(path) as doc:
            text = "\n\n".join(page.get_text() or "" for page in doc).strip()
            if text:
                return text
            errors.append("pymupdf returned empty text")
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")
    return f"PDF sem texto extraivel em {path.name}. {'; '.join(errors)}"


def _extract_docx_text(path: Path) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise RuntimeError("python-docx nao instalado para parser DOCX") from exc
    try:
        doc = DocxDocument(str(path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        if paragraphs:
            return "\n\n".join(paragraphs)
        return f"DOCX sem texto extraivel em {path.name}."
    except Exception as exc:
        raise RuntimeError(f"falha ao ler DOCX {path}: {exc}") from exc


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
