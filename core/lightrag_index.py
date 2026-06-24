"""LightRAG: indexação de entidades/relações pós Dream Cycle (Fase P4)."""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

import numpy as np
import requests

from core.auth import PROVIDERS_CONFIG, get_role_config

_rag = None
_rag_lock = threading.Lock()
_rag_ready = False
_rag_ready_lock = threading.Lock()

_WORKING_DIR = str(
    Path(os.environ.get("SINAPSE_HOME", ".")) / "claude-mem" / "data" / "lightrag"
)

# Modelo de chat local padrão para o LightRAG (não depende de Gemini/quota remota).
# Pode ser sobrescrito por HIVE_LIGHTRAG_MODEL no .env.
# Modelo de chat do LightRAG. Fixo em granite3-dense:2b por design:
# roda em qualquer máquina (≤2GB RAM) e é especializado em RAG/extração de
# entidades. Não há fallback nem UI para trocar —.env continua sobrescrevendo
# apenas para debug/dev. O download está no install.sh.
_LIGHTRAG_CHAT_MODEL = os.environ.get("HIVE_LIGHTRAG_MODEL", "granite3-dense:2b")
_LIGHTRAG_CHAT_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1/chat/completions")


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

            # Schema estruturado compatível com LightRAG v1.5.4.
            # Modelos locais menores via Ollama OpenAI endpoint.
            _EXTRACTION_JSON_SCHEMA = {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_name": {"type": "string"},
                                "entity_type": {"type": "string"},
                                "entity_description": {"type": "string"},
                            },
                            "required": ["entity_name", "entity_type", "entity_description"],
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_entity": {"type": "string"},
                                "target_entity": {"type": "string"},
                                "relationship_keywords": {"type": "string"},
                                "relationship_description": {"type": "string"},
                            },
                            "required": [
                                "source_entity",
                                "target_entity",
                                "relationship_keywords",
                                "relationship_description",
                            ],
                        },
                    },
                },
                "required": ["entities", "relationships"],
            }

            def _ollama_chat(prompt: str) -> str:
                """Chama modelo de chat local do Ollama (sem depender de Gemini/quota).

                Força JSON schema em modo extração para garantir que modelos menores
                preencham `description` em entidades e relações.
                """
                import json as _json
                messages = [
                    {"role": "system", "content": "You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text. For each entity, extract: entity_name, entity_type (category like Technology, Organization, Concept, Person, or Other), and entity_description. For each relationship, extract: source_entity, target_entity, relationship_keywords (comma-separated), and relationship_description. Always include all fields."},
                    {"role": "user", "content": prompt},
                ]
                payload: dict = {
                    "model": _LIGHTRAG_CHAT_MODEL,
                    "messages": messages,
                    "max_tokens": 4096,
                    "temperature": 0.1,
                }
                # Força schema JSON estruturado quando o prompt solicita extração
                extract_keywords = ("entity", "relation", "description", "extract", "JSON")
                use_schema = any(kw in prompt for kw in extract_keywords)
                if use_schema:
                    payload["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "extraction", "schema": _EXTRACTION_JSON_SCHEMA},
                    }
                resp = requests.post(_LIGHTRAG_CHAT_URL, json=payload, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                # Debug logging
                debug_path = os.environ.get("LIGHTRAG_DEBUG_LOG")
                if debug_path:
                    with open(debug_path, "a") as f:
                        entry = {"prompt_preview": prompt[:500], "use_schema": use_schema, "response_preview": content[:500]}
                        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
                return content

            async def _llm_func(prompt, **kwargs):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, _ollama_chat, prompt)

            Path(_WORKING_DIR).mkdir(parents=True, exist_ok=True)
            _rag = LightRAG(
                working_dir=_WORKING_DIR,
                llm_model_func=_llm_func,
                embedding_func=_embedding_func,
                entity_extraction_use_json=True,
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
