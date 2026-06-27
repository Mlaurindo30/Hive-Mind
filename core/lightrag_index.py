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
_lightrag_loop = None  # event loop dedicado e persistente (ver _run_on_lightrag_loop)

_WORKING_DIR = str(
    Path(os.environ.get("SINAPSE_HOME", ".")) / "claude-mem" / "data" / "lightrag"
)

# Modelo de chat local padrão para o LightRAG (não depende de Gemini/quota remota).
# Configurável via setupbrain (role "lightrag" → HIVE_LIGHTRAG_MODEL).
# Default qwen2.5:3b: prosa multilíngue (PT/EN), extrai entidades/relações bem
# melhor que granite3-dense:2b (que alucinava), pequeno (~1.9GB) p/ coexistir na
# GPU com bge-m3 e os demais modelos locais. Download no install.sh.
_LIGHTRAG_CHAT_MODEL = os.environ.get("HIVE_LIGHTRAG_MODEL", "qwen2.5:3b")
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

            # Schema estruturado compatível com LightRAG v1.5.4. Os NOMES DE
            # CAMPO precisam casar com o parser do LightRAG (operate.py): ele lê
            # entity_data.get("name"/"type"/"description") e rel_data.get(
            # "source"/"target"/"keywords"/"description"). Usar entity_name/
            # entity_type/etc. fazia o parser ler "" → "Empty entity name after
            # sanitization" → descartava TODAS as entidades (0 persistidas).
            _EXTRACTION_JSON_SCHEMA = {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["name", "type", "description"],
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                                "keywords": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": [
                                "source",
                                "target",
                                "keywords",
                                "description",
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
                    {"role": "system", "content": "You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text. For each entity, extract: name, type (category like Technology, Organization, Concept, Person, or Other), and description. For each relationship, extract: source, target, keywords (comma-separated), and description. Use exactly these field names. Always include all fields. Only extract entities and relationships explicitly present in the input text; never invent unrelated examples."},
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
    """Garante storages + pipeline status inicializados (v1.5.4 requer ambos).

    Sem initialize_pipeline_status(), o ainsert apenas ENFILEIRA o documento e o
    pipeline de processamento não roda ("pipeline stopped") — nenhuma entidade é
    extraída e os vdb_entities/relationships ficam vazios. Esta era a causa de
    sinapse_rag_query retornar sempre [no-context].
    """
    try:
        await rag.initialize_storages()
    except Exception:
        # Já inicializado ou função não-existente em versões antigas
        pass
    try:
        from lightrag.kg.shared_storage import initialize_pipeline_status
        await initialize_pipeline_status()
    except Exception:
        pass


def _reset_rag() -> None:
    """Invalida o singleton para que o próximo get_rag reconstrua e recarregue
    o estado persistido do disco."""
    global _rag, _rag_ready
    _rag = None
    _rag_ready = False


async def index_memory(text: str, metadata: dict | None = None) -> bool:
    """Indexa texto consolidado no grafo LightRAG (best-effort, não-bloqueante)."""
    rag = get_rag()
    if rag is None:
        return False
    try:
        await _ensure_initialized(rag)
        await rag.ainsert(text)
        # Persiste em disco: o nano-vectordb mantém entidades/relações apenas em
        # memória e só grava nos vdb_*.json ao finalizar os storages. Sem isto, a
        # extração roda (LLM é chamado) mas vdb_entities/relationships ficam em
        # 49B e sinapse_rag_query retorna sempre [no-context]. Após fechar os
        # storages, invalidamos o singleton para recarregar do disco na próxima.
        await rag.finalize_storages()
        _reset_rag()
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
    # NÃO finalizar aqui: o singleton _rag é reutilizado por todo o processo no
    # loop dedicado. Finalizar por chamada destruía os storages inicializados,
    # forçando re-init e quebrando filas de concorrência entre chamadas.


def _run_on_lightrag_loop(coro_factory):
    """Roda corrotinas LightRAG num event loop dedicado e *persistente*.

    LightRAG cria filas de concorrência (asyncio) na construção/inicialização,
    presas ao loop ativo nesse momento. asyncio.run() — ou loops efêmeros —
    criam um loop novo a cada chamada, então o singleton _rag e suas filas
    passam a apontar para um loop morto → "bound to a different event loop".
    Um único loop reutilizado, definido como corrente, mantém tudo coerente.
    """
    global _lightrag_loop, _rag, _rag_ready
    if _lightrag_loop is None or _lightrag_loop.is_closed():
        _lightrag_loop = asyncio.new_event_loop()
        _rag = None
        _rag_ready = False
    asyncio.set_event_loop(_lightrag_loop)
    return _lightrag_loop.run_until_complete(coro_factory())


def index_memory_sync(text: str, metadata: dict | None = None) -> bool:
    """Wrapper síncrono de index_memory no loop dedicado (ver _run_on_lightrag_loop)."""
    return _run_on_lightrag_loop(lambda: index_memory(text, metadata))


def query_rag_sync(question: str, mode: str = "hybrid") -> str:
    """Wrapper síncrono de query_rag no loop dedicado (ver _run_on_lightrag_loop)."""
    return _run_on_lightrag_loop(lambda: query_rag(question, mode=mode))
