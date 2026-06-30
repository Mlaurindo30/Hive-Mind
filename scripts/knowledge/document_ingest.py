#!/usr/bin/env python3
"""
Hive-Mind — Motor de Ingestão de Documentos (PDF/DOCX)
Extrai texto estruturado e alimenta o pipeline de observações.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent))
sys.path.append(SINAPSE_HOME)

from core.database import get_connection
from core.document_pipeline import DocumentPipeline

# Dependências opcionais
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

def extract_pdf_text(path: Path) -> str:
    if not fitz: return "Erro: PyMuPDF não instalado."
    text = ""
    try:
        with fitz.open(path) as doc:
            for page in doc:
                text += page.get_text() + "\n\n"
        return text.strip()
    except Exception as e:
        return f"Erro ao ler PDF: {e}"

def extract_docx_text(path: Path) -> str:
    if not DocxDocument: return "Erro: python-docx não instalado."
    try:
        doc = DocxDocument(path)
        return "\n\n".join([p.text for p in doc.paragraphs]).strip()
    except Exception as e:
        return f"Erro ao ler DOCX: {e}"


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _can_use_document_pipeline(conn) -> bool:
    if _table_exists(conn, "vec_documents"):
        return True
    try:
        conn.execute("SELECT vec_version()").fetchone()
        return True
    except Exception:
        return False


def _try_pipeline_ingest(conn, f_path: Path, *, project: str = "Hive-Mind"):
    if not _can_use_document_pipeline(conn):
        return None
    return DocumentPipeline(conn).ingest(f_path, project=project)

def run_ingestion():
    print("=== Hive-Mind: Ingestão de Documentos ===")
    from core import paths as cp
    inbox_dir = cp.INBOX_DOCUMENTS              # cortex/parietal/inbox/documents
    attachments_dir = cp.ATTACHMENTS_ROOT
    inbox_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    files = list(inbox_dir.glob("*.pdf")) + list(inbox_dir.glob("*.docx"))
    if not files:
        print("  Nenhum documento pendente.")
        return

    conn = get_connection()
    processed = 0

    for f_path in files:
        print(f"  [Document] Processando: {f_path.name}...")
        
        # 1. Calcular hash do binário (Integridade P2P)
        with open(f_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # 2. Extrair Texto
        if f_path.suffix.lower() == ".pdf":
            content = extract_pdf_text(f_path)
        else:
            content = extract_docx_text(f_path)

        if content.startswith("Erro"):
            print(f"    [!] {content}")
            continue

        # 3. Registrar na tabela document_memories + chunks/vetores quando K6
        # estiver disponivel. Testes antigos com schema minimo caem no legado.
        pipeline_result = _try_pipeline_ingest(conn, f_path)
        if pipeline_result is None:
            doc_id = f"doc-{file_hash[:12]}"
            doc_metadata = {
                "source": "document_ingest",
                "original_name": f_path.name,
                "ingested_at": datetime.now().isoformat()
            }
            conn.execute("""
                INSERT OR REPLACE INTO document_memories (id, file_path, file_hash, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                doc_id,
                str(f_path.name), # Guardamos o nome, o path real será em attachments/
                file_hash,
                json.dumps(doc_metadata)
            ))
        else:
            doc_id = pipeline_result.document_id

        # 4. Criar Observação no SQLite para o Dream Cycle
        obs_id = str(hashlib.sha256(f_path.name.encode()).hexdigest()[:8])
        metadata = {
            "source": "document_ingest",
            "file_hash": file_hash,
            "document_id": doc_id,
            "original_name": f_path.name,
            "ingested_at": datetime.now().isoformat()
        }

        # Usamos o helper de database se disponível ou SQL direto
        conn.execute("""
            INSERT INTO observations (id, type, title, content, metadata, archived)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            f"doc-{obs_id}-{file_hash[:8]}",
            "document_ingest",
            f"Documento: {f_path.name}",
            content,
            json.dumps(metadata),
            0
        ))

        # 5. Mover para attachments (Preservação)
        target_path = attachments_dir / f_path.name
        if target_path.exists():
            target_path = attachments_dir / f"{file_hash[:8]}_{f_path.name}"
        
        os.rename(f_path, target_path)
        
        processed += 1
        print(f"    [+] Ingerido e arquivado em attachments/")

    conn.commit()
    conn.close()
    print(f"=== Ingestão Concluída ({processed} documentos) ===")

def ingest_single_file(f_path: Path) -> bool:
    """Process a single PDF or DOCX file directly, without requiring it to be in the inbox.

    Returns True on success, False on error.
    """
    f_path = f_path.resolve()
    if not f_path.exists():
        print(f"  [!] File not found: {f_path}", file=sys.stderr)
        return False
    if f_path.suffix.lower() not in (".pdf", ".docx"):
        print(f"  [!] Unsupported file type: {f_path.suffix}", file=sys.stderr)
        return False

    print(f"  [Document] Processando: {f_path.name}...")

    with open(f_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    if f_path.suffix.lower() == ".pdf":
        content = extract_pdf_text(f_path)
    else:
        content = extract_docx_text(f_path)

    if content.startswith("Erro"):
        print(f"    [!] {content}", file=sys.stderr)
        return False

    conn = get_connection()
    pipeline_result = _try_pipeline_ingest(conn, f_path)
    if pipeline_result is None:
        doc_id = f"doc-{file_hash[:12]}"
        doc_metadata = {
            "source": "document_ingest",
            "original_name": f_path.name,
            "ingested_at": datetime.now().isoformat()
        }
        conn.execute("""
            INSERT OR REPLACE INTO document_memories (id, file_path, file_hash, metadata)
            VALUES (?, ?, ?, ?)
        """, (doc_id, str(f_path.name), file_hash, json.dumps(doc_metadata)))
    else:
        doc_id = pipeline_result.document_id

    obs_id = str(hashlib.sha256(f_path.name.encode()).hexdigest()[:8])
    metadata = {
        "source": "document_ingest",
        "file_hash": file_hash,
        "document_id": doc_id,
        "original_name": f_path.name,
        "ingested_at": datetime.now().isoformat()
    }
    conn.execute("""
        INSERT OR IGNORE INTO observations (id, type, title, content, metadata, archived)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        f"doc-{obs_id}-{file_hash[:8]}",
        "document_ingest",
        f"Documento: {f_path.name}",
        content,
        json.dumps(metadata),
        0
    ))

    conn.commit()
    conn.close()
    print(f"    [+] Ingerido: {f_path.name}")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hive-Mind document ingestion")
    parser.add_argument("--file", metavar="PATH", help="Ingest a single PDF or DOCX file directly")
    args = parser.parse_args()
    if args.file:
        ok = ingest_single_file(Path(args.file))
        sys.exit(0 if ok else 1)
    else:
        run_ingestion()
