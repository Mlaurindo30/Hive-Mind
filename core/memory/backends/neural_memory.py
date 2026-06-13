"""
Backend NeuralMemory: busca associativa via `nmem recall`.

Puro — recebe todos os parâmetros, sem acessar globals de outros módulos.
"""

import json
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional


def backend_neural_memory(
    query: str,
    nmem_bin: str,
    nmem_timeout: int,
    max_observations: int,
    log_fn: Optional[Callable] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca associativa via NeuralMemory (spreading activation).
    Chama `nmem recall <query>` e parseia o output.
    Tenta formato --json primeiro, fallback para parser de texto.

    Args:
        query: string de busca.
        nmem_bin: caminho para o binário nmem.
        nmem_timeout: timeout em segundos.
        max_observations: limite de observações retornadas.
        log_fn: callable para logging (não usado — compatibilidade futura).
    """
    if not os.path.isfile(nmem_bin) or not os.access(nmem_bin, os.X_OK):
        return None

    # Tenta formato JSON primeiro (versão mais recente do nmem)
    try:
        result = subprocess.run(
            [nmem_bin, "recall", "--json", query],
            capture_output=True,
            text=True,
            timeout=nmem_timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                memories = data if isinstance(data, list) else data.get("memories", [])
                if memories:
                    return {
                        "source": "neural-memory (associative)",
                        "observations": [
                            {
                                "content": m.get("content", str(m)),
                                "confidence": m.get("confidence", 0.5),
                            }
                            for m in memories[:max_observations]
                        ],
                        "count": len(memories),
                        "query": query,
                    }
            except json.JSONDecodeError:
                pass  # fallback para parser de texto
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: parser de texto (formato atual)
    return _parse_text_output(query, nmem_bin, nmem_timeout, max_observations)


def _parse_text_output(
    query: str,
    nmem_bin: str,
    nmem_timeout: int,
    max_observations: int,
) -> Optional[Dict[str, Any]]:
    """Parseia output textual do nmem recall."""
    try:
        result = subprocess.run(
            [nmem_bin, "recall", query],
            capture_output=True,
            text=True,
            timeout=nmem_timeout,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        lines = result.stdout.strip().split("\n")
        memories: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for line in lines:
            line = line.strip()
            if line.startswith("- ") and not line.startswith("- ["):
                if current:
                    memories.append(current)
                current = {"content": line[2:].strip()}
            elif line.startswith("  [") and current:
                meta = line.strip()
                if "conf=" in meta:
                    try:
                        conf_str = meta.split("conf=")[1].split("]")[0]
                        current["confidence"] = float(conf_str)
                    except (ValueError, IndexError):
                        pass
                if "src=" in meta:
                    try:
                        current["source"] = meta.split("src=")[1].split("·")[0].strip().rstrip("]")
                    except IndexError:
                        pass
        if current:
            memories.append(current)

        # Fallback para formato "## Relevant Memories"
        if not memories:
            in_section = False
            for line in lines:
                if "## Relevant Memories" in line:
                    in_section = True
                    continue
                if in_section and line.startswith("- ") and line.strip() != "-":
                    memories.append({"content": line.strip()[2:]})
                elif in_section and line.startswith("##"):
                    break

        if not memories:
            return None

        return {
            "source": "neural-memory (associative)",
            "observations": [
                {
                    "content": m.get("content", str(m)),
                    "confidence": m.get("confidence", 0.5),
                }
                for m in memories[:max_observations]
            ],
            "count": len(memories),
            "query": query,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
