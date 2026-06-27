"""
Backend Filesystem: busca direta em arquivos .md do vault.

Puro — recebe todos os parâmetros, sem globals. O cache é passado
por referência do módulo pai para que monkeypatch funcione corretamente.
"""

import os
import time
from typing import Any, Callable, Dict, List, Optional

from core.vault_excludes import filter_walk_dirs, is_excluded_vault_rel

_FS_CATEGORIES = [
    "cortex/temporal", "cortex/frontal", "cortex/parietal",
    "cortex/occipital", "cortex/insula", "cerebelo",
    "diencefalo", "tronco",
]


def fs_cache_put(
    key: str,
    value: Any,
    fs_cache: Dict[str, Any],
) -> None:
    """
    Insere no cache com poda grosseira: ao exceder 128 entradas, limpa tudo
    e reinsere apenas a atual.
    """
    fs_cache[key] = value
    if len(fs_cache) > 128:
        fs_cache.clear()
        fs_cache[key] = value


def backend_filesystem(
    query: str,
    vault_dir: str,
    fs_cache: Dict[str, Any],
    fs_cache_time_holder: List[float],
    fs_cache_ttl: int,
    max_observations: int,
    observation_chars: int,
    umc_backend_fn: Optional[Callable] = None,
    log_fn: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca direta no filesystem do vault (arquivos .md).

    Args:
        query: string de busca.
        vault_dir: caminho para o vault Obsidian.
        fs_cache: dict de cache (passado do módulo pai).
        fs_cache_time_holder: [float] — um elemento com timestamp do cache.
        fs_cache_ttl: TTL do cache em segundos.
        max_observations: limite de observações.
        observation_chars: limite de caracteres por observação.
        umc_backend_fn: função do backend UMC para delegar se disponível.
        log_fn: callable para logging.
    """
    if not query or not query.strip():
        return None

    query_lower = query.lower().strip()
    if not query_lower:
        return None

    now = time.time()
    if fs_cache and (now - fs_cache_time_holder[0]) < fs_cache_ttl:
        cached = fs_cache.get(query_lower)
        if cached is not None:
            return cached

    # Tenta UMC/FTS5 primeiro (muito mais rápido que re-walk de disco)
    if umc_backend_fn is not None:
        try:
            umc_result = umc_backend_fn(query)
            if umc_result and umc_result.get("observations"):
                return umc_result
        except Exception:
            pass  # UMC indisponível — cai para leitura de disco

    results: List[Dict[str, Any]] = []
    limit = max_observations * 2

    for cat in _FS_CATEGORIES:
        cat_dir = os.path.join(vault_dir, cat)
        if not os.path.isdir(cat_dir):
            continue

        for root, dirs, files in os.walk(cat_dir):
            filter_walk_dirs(root, dirs, vault_dir)
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, vault_dir)
                if is_excluded_vault_rel(rel):
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError):
                    continue

                if query_lower not in content.lower():
                    continue

                # Strip YAML frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    body = parts[2].strip() if len(parts) >= 3 else content
                else:
                    body = content

                # Extrair título
                title = fname[:-3]
                for line in body.split("\n"):
                    line = line.strip()
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

                results.append({
                    "title": title,
                    "content": body[:observation_chars],
                    "source_file": rel,
                    "category": cat,
                })

                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    if not results:
        fs_cache_put(query_lower, None, fs_cache)
        fs_cache_time_holder[0] = now
        return None

    # Dedup por source_file
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for r in results:
        key = r["source_file"]
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    result: Dict[str, Any] = {
        "source": "filesystem (vault fallback)",
        "observations": deduped[:max_observations],
        "query": query,
    }
    fs_cache_put(query_lower, result, fs_cache)
    fs_cache_time_holder[0] = now
    return result
