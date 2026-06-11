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
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

from core.database import get_connection

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

def run_ingestion():
    print("=== Hive-Mind: Ingestão de Documentos ===")
    inbox_dir = Path(SINAPSE_HOME) / "cerebro" / "inbox" / "documents"
    attachments_dir = Path(SINAPSE_HOME) / "cerebro" / "attachments"
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

        # 3. Registrar na tabela document_memories
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

        # 4. Criar Observação no SQLite para o Dream Cycle
        obs_id = str(hashlib.sha256(f_path.name.encode()).hexdigest()[:8])
        metadata = {
            "source": "document_ingest",
            "file_hash": file_hash,
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

if __name__ == "__main__":
    run_ingestion()
