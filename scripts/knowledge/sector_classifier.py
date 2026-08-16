#!/usr/bin/env python3
"""
scripts/sector_classifier.py — Classifica neurônios em setores canônicos.

Percorre o vault (cortex/temporal/) em busca de neurônios sem setores ou com
setores genéricos e usa a role 'sector_classifier' para classificá-los.
Permite navegação horizontal cross-project.
"""

import os
import sys
import yaml
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# Configura paths e logging
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = Path(os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent)))
sys.path.append(str(SINAPSE_HOME))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sector_classifier")

# Importações do Core
from core.paths import TEMPORAL
from core.knowledge.intake import KnowledgeCandidate, build_candidate
from core.auth import load_env
from core.llm_client import call_llm_with_fallback
from core.schemas.sector_models import SectorClassifierOutput

# NÃO carregar env no import (efeito colateral polui testes de outros módulos).
# load_env() é chamado em run_classifier() / __main__.

# Configura prompts
SCHEMAS_DIR = SINAPSE_HOME / "core" / "schemas"
PROMPTS_DIR = SCHEMAS_DIR / "prompts"
SECTOR_PROMPT_PATH = PROMPTS_DIR / "sector_classifier_prompt.yaml"

def load_prompt() -> str:
    if not SECTOR_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt não encontrado em: {SECTOR_PROMPT_PATH}")
    with open(SECTOR_PROMPT_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data["system_prompt"]

try:
    SYSTEM_PROMPT = load_prompt()
except Exception as e:
    logger.error(f"Erro ao carregar prompt: {e}")
    sys.exit(1)

def get_frontmatter_block(content: str) -> Tuple[Dict[str, Any], str, str]:
    """Extrai o bloco YAML, os dados e o restante do conteúdo."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        yaml_block = match.group(1)
        full_block = match.group(0)
        remaining = content[len(full_block):]
        try:
            data = yaml.safe_load(yaml_block)
            return data or {}, full_block, remaining
        except yaml.YAMLError:
            return {}, full_block, remaining
    return {}, "", content

def extract_neuron_info(body: str) -> Tuple[str, str]:
    """Extrai o título H1 e o conteúdo limpo do corpo do Markdown."""
    title_match = re.search(r"^# (.*)$", body, re.MULTILINE)
    title = title_match.group(1) if title_match else "Sem Título"
    # Remove o título do conteúdo para não redundar no prompt
    content_only = body.replace(f"# {title}", "", 1).strip()
    return title, content_only


def sector_update_candidate(
    filepath: Path,
    sectors: List[str],
    *,
    project: str = "default",
    workspace_id: str = "default",
) -> KnowledgeCandidate:
    """Candidate-only sector classification result for K3; no file writes."""
    safe_sectors = [str(sector) for sector in sectors if str(sector).strip()]
    title = f"Classificação setorial: {filepath.name}"
    content = f"{filepath.name} classificado nos setores: {', '.join(safe_sectors)}"
    return build_candidate(
        source_type="sector_classifier",
        source_id=str(filepath),
        knowledge_type="project_status",
        title=title,
        content=content,
        project=project,
        workspace_id=workspace_id,
        evidence={"source_uri": str(filepath), "sectors": safe_sectors},
        metadata={"promoter": "sector_classifier", "sectors": safe_sectors},
    )


def process_file(filepath: Path):
    """Lê, analisa e atualiza o arquivo com setores se necessário."""
    try:
        content = filepath.read_text(encoding="utf-8")
        data, fm_block, body = get_frontmatter_block(content)
        
        # Filtro: Sem setores ou setores == [general]
        sectors = data.get("sectors", [])
        if sectors and sectors != ["general"]:
            logger.debug(f"Ignorando {filepath.name}: já possui setores específicos ({sectors}).")
            return

        title, neuron_content = extract_neuron_info(body)
        logger.info(f"Classificando setores para: {filepath.name} ('{title}')")

        # Chama LLM
        prompt = f"TÍTULO: {title}\nCONTEÚDO: {neuron_content}"
        try:
            output: SectorClassifierOutput = call_llm_with_fallback(
                role="sector_classifier",
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                response_model=SectorClassifierOutput
            )
            new_sectors = list(output.sectors)
            logger.info(f"  [+] Setores identificados: {', '.join(new_sectors)}")

            # Otimização de IO: Só escreve se houver mudança real
            current_sectors = data.get("sectors", [])
            if set(new_sectors) == set(current_sectors):
                logger.info(f"  [-] Setores idênticos aos atuais para {filepath.name}. Pulando escrita.")
                return

            # Atualiza frontmatter
            data["sectors"] = new_sectors

            # Reconstrói o arquivo
            new_fm_block = "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"
            filepath.write_text(new_fm_block + body, encoding="utf-8")
            logger.info(f"  [v] Arquivo {filepath.name} atualizado.")

        except Exception as e:
            logger.error(f"Erro ao chamar LLM para {filepath.name}: {e}")

    except Exception as e:
        logger.error(f"Erro ao processar {filepath.name}: {e}")

def run_classifier(*, limit: Optional[int] = None, batch_size: int = 25):
    """F3-otimização (2026-08-13): classifica em LOTES (batch_size por chamada LLM).

    Antes: 1 chamada LLM por neurônio (89k chamadas). Agora: batch_size neurônios
    por chamada (89k / 25 ≈ 3.5k chamadas), com `limit` para backfill incremental
    e `--limit` para rodar em fatias sem estourar custo/tempo.

    Só classifica neurônios SEM setores (ou com [general]) — os já classificados
    são pulados (idempotência). O `limit` limita o número de neurônios NOVOS por
    execução; sem limit, processa todos (perigoso — use --limit em produção).
    """
    load_env()  # carrega env só na execução (não no import)
    logger.info(f"Iniciando Sector Classifier em {TEMPORAL} (batch_size={batch_size}, limit={limit})")

    if not TEMPORAL.exists():
        logger.error(f"Diretório TEMPORAL não encontrado: {TEMPORAL}")
        return

    # Coleta neurônios pendentes (sem setores específicos) — SEM chamar LLM ainda.
    pending: list[Path] = []
    for filepath in TEMPORAL.rglob("*.md"):
        if not filepath.name.startswith(("neuronio-", "fact-")):
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
            data, _, _ = get_frontmatter_block(content)
            sectors = data.get("sectors", [])
            if sectors and sectors != ["general"]:
                continue
            pending.append(filepath)
        except Exception:
            continue
        if limit is not None and len(pending) >= limit:
            break

    if not pending:
        logger.info("Nenhum neurônio pendente de classificação.")
        return

    logger.info(f"{len(pending)} neurônios pendentes; processando em lotes de {batch_size}.")

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        # Monta um único prompt com todos os neurônios do lote.
        items = []
        for fp in batch:
            try:
                content = fp.read_text(encoding="utf-8")
                _, _, body = get_frontmatter_block(content)
                title, neuron_content = extract_neuron_info(body)
                items.append((fp, title, neuron_content[:300]))
            except Exception:
                continue

        if not items:
            continue

        numbered = "\n\n".join(
            f"[{i}] TÍTULO: {title}\nCONTEÚDO: {nc}"
            for i, (_, title, nc) in enumerate(items)
        )
        prompt = (
            f"Classifique os seguintes {len(items)} neurônios. Para CADA [i], "
            f"retorne uma entrada com id=i e os setores (1-3).\n\n{numbered}"
        )
        try:
            from core.schemas.sector_models import SectorBatchOutput
            output = call_llm_with_fallback(
                role="sector_classifier",
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT + (
                    "\n\nMODO LOTE: a entrada tem N itens numerados [0..N-1]. "
                    "Retorne um array `results` com {id, sectors} para cada item."
                ),
                response_model=SectorBatchOutput,
            )
            by_id = {r.id: list(r.sectors) for r in output.results}
            for i, (fp, _, _) in enumerate(items):
                new_sectors = by_id.get(i)
                if not new_sectors:
                    continue
                _write_sectors(fp, new_sectors)
        except Exception as e:
            logger.error(f"Erro no lote {batch_start}: {e}")

    logger.info("Fim do processamento.")


def _write_sectors(filepath: Path, new_sectors: List[str]) -> None:
    """Atualiza o frontmatter `sectors` do arquivo (idempotente)."""
    try:
        content = filepath.read_text(encoding="utf-8")
        data, fm_block, body = get_frontmatter_block(content)
        current = data.get("sectors", [])
        if set(new_sectors) == set(current):
            return
        data["sectors"] = new_sectors
        new_fm = "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"
        filepath.write_text(new_fm + body, encoding="utf-8")
        logger.info(f"  [v] {filepath.name}: {', '.join(new_sectors)}")
    except Exception as e:
        logger.error(f"Erro ao gravar {filepath.name}: {e}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Classifica neurônios em setores canônicos (lote).")
    ap.add_argument("--limit", type=int, default=None,
                    help="limita o nº de neurônios NOVOS por execução (sem limit = todos)")
    ap.add_argument("--batch-size", type=int, default=25,
                    help="neurônios por chamada LLM (default 25)")
    args = ap.parse_args()
    run_classifier(limit=args.limit, batch_size=args.batch_size)
