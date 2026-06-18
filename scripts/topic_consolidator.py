#!/usr/bin/env python3
"""
topic_consolidator.py — Consolidação inteligente de tópicos fragmentados (§7.3).

Reduz a fragmentação do lobo temporal agrupando tópicos semanticamente similares
via embeddings (fastembed) + confirmação via LLM (topic_router).

Uso:
  python scripts/topic_consolidator.py            # DRY-RUN (mostra propostas)
  python scripts/topic_consolidator.py --apply    # executa fusões
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np

# Adiciona raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import paths as cp
from core import database as db
from core.llm_client import call_llm_with_fallback
from core.schemas.topic_models import TopicMergeProposal

# Configurações
SIMILARITY_THRESHOLD = 0.85
SAMPLE_NEURONS_LIMIT = 5

def _proj_topic_from_source(source_file: str) -> Optional[tuple]:
    """Deriva (projeto, tópico) do path anatômico do neurônio:
    .../cortex/temporal/{projeto}/{topico}/neuronio-*.md. None se não casar."""
    if not source_file:
        return None
    parts = Path(source_file).parts
    if "temporal" not in parts:
        return None
    i = parts.index("temporal")
    if i + 2 >= len(parts):
        return None
    project, topic = parts[i + 1], parts[i + 2]
    if project.startswith("_") or topic.startswith("_"):  # ignora MOCs/_global
        return None
    return project, topic


def get_topics_data() -> Dict[str, List[str]]:
    """Tópicos agrupados por projeto — derivados do source_file (a tabela neurons
    NÃO tem coluna project; o eixo anatômico vive no path)."""
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT source_file FROM neurons WHERE source_file LIKE '%cortex/temporal/%'"
        ).fetchall()
        data = defaultdict(set)
        for row in rows:
            pt = _proj_topic_from_source(row["source_file"])
            if pt:
                data[pt[0]].add(pt[1])
        return {k: sorted(v) for k, v in data.items()}
    finally:
        conn.close()

def sanitize_topic_name(name: str) -> str:
    """
    Sanitiza o nome do tópico sugerido pela LLM (§Task 4).
    Garante que seja seguro para caminhos de arquivo e consistente.
    """
    if not name:
        return "unnamed_topic"
        
    # 1. Normalizar para remover acentos
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    
    # 2. Lowercase
    name = name.lower()
    
    # 3. Substituir espaços e separadores de path por hifens
    name = re.sub(r'[\s/\\._]+', '-', name)
    
    # 4. Manter apenas alfanuméricos e hifens
    name = re.sub(r'[^a-z0-9\-]', '', name)
    
    # 5. Limpar hifens repetidos ou nas extremidades
    name = re.sub(r'-+', '-', name).strip('-')
    
    # 6. Prevenção extra contra path traversal
    name = name.replace('..', '')
    
    return name or "sanitized_topic"

def get_sample_neurons(project: str, topic: str) -> List[str]:
    """Obtém títulos de alguns neurônios de um tópico para contexto."""
    conn = db.get_connection()
    try:
        # neurons não tem project; filtra pelo path. `title` não existe → `label`.
        pattern = f"%cortex/temporal/{project}/{topic}/%"
        rows = conn.execute(
            "SELECT label FROM neurons WHERE source_file LIKE ? LIMIT ?",
            (pattern, SAMPLE_NEURONS_LIMIT)).fetchall()
        return [row['label'] for row in rows if row['label']]
    finally:
        conn.close()

def calculate_similarity(topics: List[str]) -> List[Tuple[str, str, float]]:
    """Calcula similaridade de cosseno entre pares de tópicos."""
    if len(topics) < 2:
        return []
    
    embedder = db.get_embedder()
    if not embedder:
        print("Erro: FastEmbed não disponível.")
        return []
        
    embeddings = list(embedder.embed(topics))
    # Normalizar
    embeddings = [e / (np.linalg.norm(e) + 1e-9) for e in embeddings]
    
    results = []
    for i in range(len(topics)):
        for j in range(i + 1, len(topics)):
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim >= SIMILARITY_THRESHOLD:
                results.append((topics[i], topics[j], sim))
    
    return sorted(results, key=lambda x: -x[2])

def confirm_merge(project: str, topics: List[str]) -> Optional[TopicMergeProposal]:
    """Usa LLM (topic_router) para confirmar a fusão."""
    context = ""
    for topic in topics:
        samples = get_sample_neurons(project, topic)
        context += f"\nTópico: {topic}\nExemplos de neurônios:\n"
        for s in samples:
            context += f"  - {s}\n"
            
    system_prompt = """Você é o `topic_router` do sistema Hive-Mind.
Sua tarefa é analisar se um grupo de tópicos em um projeto deve ser fundido em um único tópico consolidado.
Analise a semântica dos nomes e os exemplos de neurônios contidos em cada um.
Se a fusão fizer sentido, sugira um nome representativo (lowercase, snake_case).
Evite nomes genéricos demais. Prefira nomes que já existam se um deles for o mais abrangente.
"""

    prompt = f"""Projeto: {project}
Tópicos candidatos à fusão: {', '.join(topics)}

Contexto do conteúdo:
{context}

Decida se a fusão é apropriada.
"""

    try:
        proposal = call_llm_with_fallback(
            role="topic_router",
            prompt=prompt,
            system_prompt=system_prompt,
            response_model=TopicMergeProposal
        )
        return proposal
    except Exception as e:
        print(f"Erro ao consultar LLM para {topics}: {e}")
        return None

def create_redirect_note(old_path: Path, new_path: Path):
    """Cria uma nota de redirecionamento no caminho antigo."""
    rel_new = str(new_path.relative_to(cp.VAULT_ROOT))
    # Remove a extensão .md para o link do Obsidian
    link_target = rel_new[:-3] if rel_new.endswith(".md") else rel_new
    
    content = f"""---
type: redirect
redirects_to: "[[{link_target}]]"
---
# Redirecionamento

Esta nota foi movida para: [[{link_target}]]
Atualize seus links se necessário.
"""
    old_path.write_text(content)

def execute_merge(project: str, old_topics: List[str], new_topic: str):
    """Executa a fusão física e no banco de dados."""
    print(f"  [Merge] {project}: {', '.join(old_topics)} -> {new_topic}")
    
    conn = db.get_connection()
    try:
        # 1. Identificar neurônios dos tópicos antigos via path (sem coluna project).
        like_clauses = " OR ".join(["source_file LIKE ?"] * len(old_topics))
        patterns = [f"%cortex/temporal/{project}/{t}/%" for t in old_topics]
        neurons = conn.execute(
            f"SELECT id, source_file FROM neurons WHERE {like_clauses}", patterns
        ).fetchall()
        
        target_dir = cp.TEMPORAL / project / new_topic
        target_dir.mkdir(parents=True, exist_ok=True)
        
        for n in neurons:
            old_rel_path = n['source_file']
            if not old_rel_path:
                continue
            
            old_abs_path = cp.SINAPSE_HOME / old_rel_path
            if not old_abs_path.exists():
                print(f"    [Aviso] Arquivo não encontrado: {old_abs_path}")
                continue
                
            new_abs_path = target_dir / old_abs_path.name
            new_rel_path = str(new_abs_path.relative_to(cp.SINAPSE_HOME))
            
            # Move arquivo
            shutil.move(str(old_abs_path), str(new_abs_path))
            
            # Cria redirecionamento
            create_redirect_note(old_abs_path, new_abs_path)
            
            # Atualiza DB
            conn.execute(
                "UPDATE neurons SET topic = ?, source_file = ? WHERE id = ?",
                (new_topic, new_rel_path, n['id'])
            )
            
        # 2. Remover pastas antigas se vazias (exceto se for a mesma do novo tópico)
        for ot in old_topics:
            if ot == new_topic:
                continue
            old_dir = cp.TEMPORAL / project / ot
            if old_dir.exists() and not any(old_dir.iterdir()):
                old_dir.rmdir()
                
        # 3. Registrar a fusão em log
        log_file = cp.CONFLICTS_ROOT / f"topic-merge-{project}-{new_topic}.md"
        log_content = f"""# Log de Fusão de Tópicos

- **Projeto:** {project}
- **Tópico Consolidado:** {new_topic}
- **Tópicos Originais:** {', '.join(old_topics)}
- **Data:** {time.strftime('%Y-%m-%d %H:%M:%S')}

## Neurônios Movidos
"""
        for n in neurons:
            log_content += f"- {n['id']} ({n['source_file']})\n"
            
        try:
            cp.CONFLICTS_ROOT.mkdir(parents=True, exist_ok=True)
            log_file.write_text(log_content)
            print(f"    [Log] Registrado em {log_file}")
        except Exception as e:
            print(f"    [Aviso] Falha ao gravar log em {log_file}: {e}")

        conn.commit()
    except Exception as e:
        print(f"Erro ao executar merge: {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    global SIMILARITY_THRESHOLD  # deve vir ANTES de qualquer uso da variável
    parser = argparse.ArgumentParser(description="Consolidador de tópicos Hive-Mind.")
    parser.add_argument("--apply", action="store_true", help="Executa as fusões propostas.")
    parser.add_argument("--project", help="Filtra por um projeto específico.")
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD, help="Limite de similaridade (0.0 a 1.0).")
    args = parser.parse_args()

    SIMILARITY_THRESHOLD = args.threshold

    topics_data = get_topics_data()
    if args.project:
        if args.project in topics_data:
            topics_data = {args.project: topics_data[args.project]}
        else:
            print(f"Projeto '{args.project}' não encontrado no DB.")
            return

    all_proposals = []

    for project, topics in topics_data.items():
        print(f"Analisando projeto: {project} ({len(topics)} tópicos)")
        pairs = calculate_similarity(topics)
        
        # Agrupar pares em cadeias de fusão (clusters simples)
        clusters = []
        for ta, tb, sim in pairs:
            matching_clusters = [c for c in clusters if ta in c or tb in c]
            if not matching_clusters:
                clusters.append({ta, tb})
            else:
                # Funde todos os clusters que coincidem em um só
                new_cluster = {ta, tb}
                for mc in matching_clusters:
                    new_cluster.update(mc)
                    clusters.remove(mc)
                clusters.append(new_cluster)
        
        for cluster in clusters:
            topic_list = sorted(list(cluster))
            print(f"  Candidatos: {', '.join(topic_list)}")
            proposal = confirm_merge(project, topic_list)
            if proposal and proposal.should_merge:
                sanitized_name = sanitize_topic_name(proposal.new_topic_name)
                print(f"    [LLM] Fusão confirmada -> {sanitized_name}")
                if sanitized_name != proposal.new_topic_name:
                    print(f"    [Sanitização] De '{proposal.new_topic_name}' para '{sanitized_name}'")
                print(f"    [LLM] Razão: {proposal.rationale}")
                all_proposals.append((project, topic_list, sanitized_name))
            else:
                if proposal:
                    print(f"    [LLM] Fusão rejeitada. Razão: {proposal.rationale}")
                else:
                    print(f"    [Erro] LLM não retornou resposta válida.")

    if not all_proposals:
        print("\nNenhuma proposta de fusão encontrada.")
        return

    print(f"\nTotal de {len(all_proposals)} propostas de fusão.")

    if args.apply:
        print("\nExecutando fusões...")
        for project, old_topics, new_topic in all_proposals:
            execute_merge(project, old_topics, new_topic)
        
        # Opcional: Regenerar MOCs e Sinapses
        print("\nRegenerando MOCs...")
        try:
            from scripts.generate_mocs import build_mocs
            build_mocs()
        except ImportError:
            print("Aviso: scripts.generate_mocs não encontrado para regeneração.")
    else:
        print("\nModo DRY-RUN. Use --apply para executar as fusões.")

if __name__ == "__main__":
    main()
