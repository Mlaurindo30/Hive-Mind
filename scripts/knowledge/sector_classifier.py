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

def run_classifier():
    load_env()  # carrega env só na execução (não no import)
    logger.info(f"Iniciando Sector Classifier em {TEMPORAL}")

    if not TEMPORAL.exists():
        logger.error(f"Diretório TEMPORAL não encontrado: {TEMPORAL}")
        return

    count = 0
    # Procura recursivamente por arquivos neuronio-*.md ou fact-*.md
    for filepath in TEMPORAL.rglob("*.md"):
        if filepath.name.startswith(("neuronio-", "fact-")):
            process_file(filepath)
            count += 1
    
    logger.info(f"Fim do processamento. {count} arquivos analisados.")

if __name__ == "__main__":
    run_classifier()
