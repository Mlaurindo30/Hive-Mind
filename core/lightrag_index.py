"""LightRAG: indexação de entidades/relações pós Dream Cycle (Fase P4)."""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

import numpy as np

_rag = None
_rag_lock = threading.Lock()
_rag_ready = False
_rag_ready_lock = threading.Lock()

_WORKING_DIR = str(
    Path(os.environ.get("SINAPSE_HOME", ".")) / "claude-mem" / "data" / "lightrag"
)


def get_rag():
    """Singleton: cria instância LightRAG alinhada ao projeto (Ollama bge-m3 1024d)."""
    global _rag, _rag_ready
    if _rag is not None and _rag_ready:
        return _rag

    with _rag_lock:
        if _rag is not None and _rag_ready:
            return _rag
        try:
            from lightrag import LightRAG, QueryParam
            from lightrag.utils import wrap_embedding_func_with_attrs

            # Reutiliza a infraestrutura de embeddings do projeto (P0)
            from core.database import get_embedder, OLLAMA_EMBED_MODEL
            _embedder = get_embedder()

            @wrap_embedding_func_with_attrs(
                embedding_dim=1024,
                max_token_size=8192,
                model_name="bge-m3:latest",
                supports_asymmetric=True,
            )
            async def _embedding_func(
                texts: list[str],
                embedding_dim: int | None = None,
                context: str = "document",
                **kwargs,
            ) -> np.ndarray:
                """Wrapper Ollama local compatível com LightRAG EmbeddingFunc."""
                if isinstance(texts, str):
                    texts = [texts]
                loop = asyncio.get_event_loop()
                vectors = await loop.run_in_executor(None, lambda: list(_embedder.embed(texts)))
                return np.array(vectors, dtype=np.float32)

            async def _llm_func(prompt, **kwargs):
                from core.llm_client import call_llm_structured
                from pydantic import BaseModel

                class _TextOut(BaseModel):
                    text: str

                result = call_llm_structured(
                    prompt=prompt,
                    system_prompt="",
                    response_model=_TextOut,
                )
                return result.text if hasattr(result, "text") else str(result)

            Path(_WORKING_DIR).mkdir(parents=True, exist_ok=True)
            _rag = LightRAG(
                working_dir=_WORKING_DIR,
                llm_model_func=_llm_func,
                embedding_func=_embedding_func,
            )
            _rag_ready = True
            return _rag
        except ImportError as e:
            print(f"  ⚠ LightRAG não disponível: {e}")
            return None
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ⚠ LightRAG init falhou: {e}")
            return None


async def _ensure_initialized(rag):
    """Garante storages inicializados (v1.5.4 requer chamada explícita)."""
    try:
        await rag.initialize_storages()
    except Exception as e:
        # Já inicializado ou função não-existente em versões antigas
        pass


async def index_memory(text: str, metadata: dict | None = None) -> bool:
    """Indexa texto consolidado no grafo LightRAG (best-effort, não-bloqueante)."""
    rag = get_rag()
    if rag is None:
        return False
    try:
        await _ensure_initialized(rag)
        await rag.ainsert(text)
        return True
    except Exception as e:
        print(f"  ⚠ LightRAG index falhou: {e}")
        return False


async def query_rag(question: str, mode: str = "hybrid") -> str:
    """Consulta o grafo LightRAG com modo hybrid (grafo + vetor)."""
    from lightrag import QueryParam

    rag = get_rag()
    if rag is None:
        return ""
    try:
        await _ensure_initialized(rag)
        return await rag.aquery(question, param=QueryParam(mode=mode))
    except Exception as e:
        print(f"  ⚠ LightRAG query falhou: {e}")
        return ""
    finally:
        if rag is not None:
            try:
                await rag.finalize()
            except Exception:
                pass
