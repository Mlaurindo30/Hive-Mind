#!/usr/bin/env python3
"""
Hive-Mind — Motor de Diferença Semântica (Semantic Diff Engine)
Compara dois textos usando Embeddings (deduplicação) e LLM (contradição).
"""

import os
import sys
import json
import argparse
import numpy as np
from pathlib import Path
from typing import Optional

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent))
sys.path.append(SINAPSE_HOME)

from core.database import get_embedder
from core.schemas.diff_models import SemanticDiffResult, DiffCategory
from scripts.dream.dream_cycle import call_llm_structured, load_yaml

# Carrega Prompt
PROMPTS_DIR = Path(SINAPSE_HOME) / "core" / "schemas" / "prompts"
diff_prompt_yaml = load_yaml(PROMPTS_DIR / "semantic_diff_prompt.yaml")
SEMANTIC_DIFF_SYSTEM_PROMPT = diff_prompt_yaml["system_prompt"]

def cosine_similarity(v1, v2):
    """Calcula a similaridade de cosseno entre dois vetores."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

def get_vector_similarity(text1: str, text2: str) -> float:
    """Retorna a similaridade vetorial entre dois textos."""
    embedder = get_embedder()
    if not embedder:
        return 0.0
    
    try:
        embeddings = list(embedder.embed([text1, text2]))
        v1 = embeddings[0]
        v2 = embeddings[1]
        return float(cosine_similarity(v1, v2))
    except Exception as e:
        print(f"[Diff] Erro ao gerar embeddings: {e}", file=sys.stderr)
        return 0.0

def run_semantic_diff(text1: str, text2: str, threshold: Optional[float] = None) -> SemanticDiffResult:
    """Executa a lógica de diff semântico com base nos thresholds definidos na especificação."""
    threshold_identical = threshold if threshold is not None else 0.92
    threshold_complementary = 0.70

    # 1. Check de Similaridade Vetorial (Deduplicação rápida)
    sim = get_vector_similarity(text1, text2)
    
    if sim > threshold_identical:
        return SemanticDiffResult(
            contradiction_score=0.0,
            category=DiffCategory.ADDITIVE,
            reasoning=f"Similaridade vetorial alta ({sim:.4f} > {threshold_identical}). Textos considerados semanticamente idênticos ou duplicados.",
            suggested_resolution=text1
        )
    
    if sim >= threshold_complementary:
        return SemanticDiffResult(
            contradiction_score=0.2,
            category=DiffCategory.ADDITIVE,
            reasoning=f"Similaridade vetorial média ({sim:.4f} entre {threshold_complementary} e {threshold_identical}). Textos complementares (merge candidato).",
            suggested_resolution=f"{text1}\n\n{text2}"
        )
    
    # 2. Análise Profunda via LLM (sim < 0.70)
    prompt = f"VERSÃO A:\n{text1}\n\nVERSÃO B:\n{text2}"
    
    try:
        return call_llm_structured(prompt, SEMANTIC_DIFF_SYSTEM_PROMPT, SemanticDiffResult)
    except Exception as e:
        # Fallback básico em caso de erro crítico da LLM
        print(f"[Diff] Erro na chamada da LLM: {e}", file=sys.stderr)
        return SemanticDiffResult(
            contradiction_score=0.5,
            category=DiffCategory.SUBSTITUTIVE,
            reasoning=f"Falha na análise da LLM. Erro: {str(e)}",
            suggested_resolution=text2
        )

def main():
    parser = argparse.ArgumentParser(description="Hive-Mind Semantic Diff Engine")
    parser.add_argument("text1", help="Primeiro texto (Versão A)")
    parser.add_argument("text2", help="Segundo texto (Versão B)")
    parser.add_argument("--threshold", type=float, default=0.98, help="Threshold de similaridade vetorial (default: 0.98)")
    parser.add_argument("--json", action="store_true", help="Saída em formato JSON")
    
    args = parser.parse_args()
    
    result = run_semantic_diff(args.text1, args.text2, args.threshold)
    
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print("\n=== RESULTADO DO DIFF SEMÂNTICO ===")
        print(f"Categoria: {result.category}")
        print(f"Score de Contradição: {result.contradiction_score}")
        print(f"Raciocínio: {result.reasoning}")
        if result.suggested_resolution:
            print(f"Resolução Sugerida: {result.suggested_resolution}")
        print("===================================\n")

if __name__ == "__main__":
    main()
