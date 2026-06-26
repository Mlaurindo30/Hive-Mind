#!/usr/bin/env python3
"""
Hive-Mind — Ciclo de Sonho (Atlas Infinito - Corporate Grade)
Pipeline ETL determinístico: Ingestão -> Distiller -> Validator -> Router.
"""

import os
import sys
import json
import sqlite3
import yaml
import time
import re
import hashlib
import asyncio
import pydantic
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent))
sys.path.append(SINAPSE_HOME)

# Load Env
ENV_PATH = Path(SINAPSE_HOME) / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH)
except ImportError:
    pass

from core.database import get_connection, ensure_migrations, get_recent_topics
from core.schemas.dream_models import DistillerOutput, ValidatorOutput, RouterOutput
from core.schemas.vision_models import VisionAnalysis
from core.schemas.synthesis_models import SynthesisOutput, SynthesisTask

# ---------------------------------------------------------------------------
# Carregamento de Contratos e Prompts (YAML)
# ---------------------------------------------------------------------------
SCHEMAS_DIR = Path(SINAPSE_HOME) / "core" / "schemas"
PROMPTS_DIR = SCHEMAS_DIR / "prompts"

# BOUNDEDNESS (incidente 2026-06-17): tetos que impedem o ciclo de travar a
# máquina. Obs já é capada (LIMIT 30 na query); LLM já tem timeout (60/120s no
# llm_client). O gap real era a síntese sem teto → aqui ela ganha cap + deadline.
MAX_CYCLE_SECONDS = int(os.environ.get("HIVE_MAX_CYCLE_SECONDS", "600"))
MAX_AMBIGUITIES = int(os.environ.get("HIVE_MAX_AMBIGUITIES", "50"))
MAX_OBS_PER_CYCLE = int(os.environ.get("HIVE_MAX_OBS_PER_CYCLE", "30"))


def fetch_balanced_observations(conn, limit: int = MAX_OBS_PER_CYCLE) -> list:
    """Janela BALANCEADA por projeto (round-robin), em vez de só 'mais antigas'.

    Antes: `ORDER BY created_at LIMIT 30` → com backlog de milhares, o ciclo
    consumia UM projeto por vez (cronológico) e projetos recentes demoravam dias.

    Agora: rankeia cada observação dentro do seu projeto (ROW_NUMBER por created_at)
    e ordena por rank — assim pega a mais antiga de CADA projeto primeiro, depois a
    2ª de cada, etc. Resultado: todos os projetos pendentes avançam a cada ciclo,
    mantendo o teto de boundedness (LIMIT). Empata por created_at (determinístico)."""
    return conn.execute(
        """
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(project, '_sem_projeto')
                ORDER BY created_at ASC, id ASC
            ) AS _rk
            FROM observations WHERE archived = 0
        )
        ORDER BY _rk ASC, created_at ASC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

guardrails = load_yaml(SCHEMAS_DIR / "guardrails.yaml")["dream_cycle"]
distiller_prompt = load_yaml(PROMPTS_DIR / "distiller_prompt.yaml")["system_prompt"]
validator_prompt = load_yaml(PROMPTS_DIR / "validator_prompt.yaml")["system_prompt"]
router_prompt = load_yaml(PROMPTS_DIR / "router_prompt.yaml")["system_prompt"]
synthesis_prompt = load_yaml(PROMPTS_DIR / "synthesis_prompt.yaml")["system_prompt"]
vision_prompt = load_yaml(PROMPTS_DIR / "vision_prompt.yaml")["system_prompt"]

# ---------------------------------------------------------------------------
# Chamada Segura a LLM — config por papel (core.auth) + cliente (core.llm_client)
# ---------------------------------------------------------------------------
from core.auth import get_role_config, load_env
from core.llm_client import (
    call_llm_structured as _call_llm_structured,
    call_llm_with_fallback,
    classify_llm_error,
)

# Garante que o .env está no os.environ antes de qualquer leitura de config.
# O try/except dotenv acima falha silenciosamente quando python-dotenv não está
# instalado, portanto usamos o load_env() nativo do core.auth como garantia.
load_env()

# Cérebro ativo do pipeline principal (papel "dreamer"). As globais existem
# para que o fallback possa ser ativado em runtime (_activate_dreamer_fallback).
_dreamer_cfg = get_role_config("dreamer") or {}
LLM_PROVIDER = _dreamer_cfg.get("provider")
LLM_MODEL = _dreamer_cfg.get("model")

def call_llm_structured(prompt: str, system_prompt: str, response_model: Any,
                        image_path: Optional[str] = None,
                        provider: Optional[str] = None,
                        model: Optional[str] = None) -> Any:
    """Wrapper fino: usa o cérebro ativo do Dreamer (globais) como padrão."""
    return _call_llm_structured(prompt, system_prompt, response_model, image_path=image_path,
                                provider=provider or LLM_PROVIDER, model=model or LLM_MODEL)

def _activate_dreamer_fallback(reason: str) -> bool:
    """Alterna o cérebro ativo do Dreamer para o fallback. True se alternou."""
    global LLM_PROVIDER, LLM_MODEL
    cfg = get_role_config("dreamer") or {}
    fb_p, fb_m = cfg.get("fallback_provider"), cfg.get("fallback_model")
    if not fb_p or not fb_m or (LLM_PROVIDER, LLM_MODEL) == (fb_p, fb_m):
        return False
    print(f"  [Fallback] Papel 'dreamer': alternando de {LLM_PROVIDER}/{LLM_MODEL} "
          f"para {fb_p}/{fb_m} ({reason})")
    LLM_PROVIDER, LLM_MODEL = fb_p, fb_m
    return True

# ---------------------------------------------------------------------------
# Pipeline ETL Multi-Agente
# ---------------------------------------------------------------------------

def agent_distill_and_validate(logs_context: str) -> tuple:
    """
    Loop de Extração + Validação com suporte a Retry.
    Retorna uma tupla (output, status), onde status é:
    - "ok": fatos extraídos e validados com sucesso
    - "empty": sem fatos relevantes (não é falha)
    - "failed": falha de pipeline após max_retries (candidato a quarentena)
    """
    max_retries = guardrails["validation"]["max_retries"]
    attempt = 0
    feedback = ""

    while attempt < max_retries:
        attempt += 1
        print(f"  [Distiller] Extraindo fatos (Tentativa {attempt}/{max_retries})...")

        prompt = f"LOGS BRUTOS:\n{logs_context}\n"
        if feedback:
            prompt += f"\nCRÍTICA DA TENTATIVA ANTERIOR DO VALIDATOR. CORRIJA OS ERROS:\n{feedback}"

        try:
            # 1. Distiller Agent
            distiller_output: DistillerOutput = call_llm_structured(prompt, distiller_prompt, DistillerOutput)

            if not distiller_output.facts:
                return None, "empty" # Sem fatos relevantes

            # Calcula hashes de integridade e atualiza IDs para serem determinísticos
            for fact in distiller_output.facts:
                content_hash = hashlib.sha256(fact.content.encode('utf-8')).hexdigest()[:16]
                fact.integrity_hash = content_hash
                fact.id = f"fact-{content_hash}"
                
            # 2. Validator Agent (Verifica Alucinação e Aterramento)
            print(f"  [Validator] Inspecionando {len(distiller_output.facts)} fatos contra os logs originais...")
            val_prompt = f"LOGS ORIGINAIS:\n{logs_context}\n\nFATOS EXTRAÍDOS PARA VALIDAÇÃO:\n{distiller_output.model_dump_json(indent=2)}"
            
            val_output: ValidatorOutput = call_llm_structured(val_prompt, validator_prompt, ValidatorOutput)
            
            if val_output.global_status == "pass":
                print(f"  [Validator] Aprovado! Fatos aterrados com sucesso.")
                # Filtra apenas os que passaram perfeitamente ou tem warning aceitável
                valid_facts = [f for f, v in zip(distiller_output.facts, val_output.validations) if v.status in ["pass", "warning"]]
                distiller_output.facts = valid_facts
                return distiller_output, "ok"
            else:
                # Falhou na validação. Gera feedback para o Distiller tentar novamente
                failures = [v for v in val_output.validations if v.status == "fail"]
                print(f"  [Validator] Falha! {len(failures)} alucinações ou fatos não aterrados detectados.")
                feedback = json.dumps([f.model_dump() for f in failures], indent=2)
                
        except pydantic.ValidationError as e:
            print(f"  [Error] ValidationError em modelo Pydantic (Distiller/Validator): {e.errors()}")
            time.sleep(2)
            continue
        except Exception as e:
            kind = classify_llm_error(e)
            if kind == "auth":
                # Permanente (401/402/403, saldo/quota): sem retry — fallback direto
                print(f"  [Error] Falha de auth/saldo no pipeline LLM: {e}")
                if _activate_dreamer_fallback("auth/saldo"):
                    attempt -= 1  # fallback direto não consome tentativa
                    continue
                print("  [Aviso] Sem fallback configurado para o papel 'dreamer' — quarentena.")
                return None, "failed"
            if kind == "validation":
                # Qualidade, não disponibilidade: retry no MESMO modelo, nunca fallback
                print(f"  [Error] Falha de validação no pipeline LLM (retry no mesmo modelo): {e}")
                time.sleep(2)
                continue
            # Transitória (timeout/conexão/429/5xx): backoff; esgotou → fallback
            print(f"  [Error] Falha transitória no pipeline LLM: {e}")
            if attempt >= max_retries and _activate_dreamer_fallback("falha transitória persistente"):
                attempt = 0
                continue
            time.sleep(min(2 ** attempt, 8))

    print(f"  [Pipeline] Falha crítica após {max_retries} tentativas. Enviando para quarentena.")
    return None, "failed"

def agent_route(facts: List[Any]) -> Optional[RouterOutput]:
    """Decide onde os fatos vão morar na taxonomia do Atlas."""
    print(f"  [Router] Classificando os fatos extraídos...")
    
    # Anatômico: tópicos vivem em cortex/temporal/{projeto}/{topico}/ — lista os
    # tópicos existentes em todos os projetos como dica anti-fragmentação do Router.
    from core import paths as cp
    existing_topics = sorted({
        topic_dir.name
        for proj_dir in (cp.TEMPORAL.iterdir() if cp.TEMPORAL.exists() else [])
        if proj_dir.is_dir()
        for topic_dir in proj_dir.iterdir()
        if topic_dir.is_dir() and not topic_dir.name.startswith("_")
    })

    # SLIDING WINDOW (Task 3): tópicos mais recentes do banco de dados
    recent_topics = get_recent_topics(limit=20)

    prompt = f"TÓPICOS EXISTENTES NO ATLAS:\n{existing_topics}\n\n"
    prompt += f"TÓPICOS RECENTES (SLIDING WINDOW - PREFERIR ESTES SE MATCH >= 0.7):\n{recent_topics}\n\n"
    prompt += f"FATOS A SEREM ROTEADOS:\n{json.dumps([f.model_dump() for f in facts], indent=2)}"

    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            return call_llm_structured(prompt, router_prompt, RouterOutput)
        except pydantic.ValidationError as e:
            print(f"  [Error] ValidationError em RouterOutput: {e.errors()}")
            time.sleep(2)
            continue
        except Exception as e:
            kind = classify_llm_error(e)
            print(f"  [Error] Falha no Roteador ({kind}): {e}")
            if kind == "auth":
                if _activate_dreamer_fallback("auth/saldo no Roteador"):
                    attempt -= 1  # fallback direto não consome tentativa
                    continue
                return None
            if kind == "transient" and attempt >= max_attempts and \
                    _activate_dreamer_fallback("falha transitória no Roteador"):
                attempt = 0
                continue
            time.sleep(min(2 ** attempt, 8))
    return None

# ---------------------------------------------------------------------------
# Estágio de Síntese Dialética (Autonomous Synthesizer)
# ---------------------------------------------------------------------------

def run_synthesis_cycle(deadline: Optional[float] = None):
    """Busca ambiguidades pendentes e resolve-as via Síntese Dialética.

    BOUNDEDNESS (incidente 2026-06-17): o loop processava TODAS as ambiguidades
    pendentes sem teto — cada uma é 1 chamada LLM, então N grande = horas/freeze.
    Agora: cap de MAX_AMBIGUITIES por ciclo + deadline wall-clock (resto fica p/ o
    próximo ciclo; sai limpo, não trava)."""
    from scripts.dream.semantic_diff import run_semantic_diff
    import time as _t
    if deadline is None:
        deadline = _t.monotonic() + MAX_CYCLE_SECONDS

    print("\n=== Estágio de Síntese Dialética (Hive-Mind Brain) ===")
    conn = get_connection()
    ambiguities = conn.execute(
        "SELECT * FROM ambiguities WHERE status = 'pending' "
        "ORDER BY detected_at LIMIT ?", (MAX_AMBIGUITIES,)).fetchall()

    if not ambiguities:
        print("  Nenhuma ambiguidade pendente para síntese.")
        conn.close()
        return

    for amb in ambiguities:
        if _t.monotonic() > deadline:
            print(f"  [BUDGET_EXHAUSTED] teto de {MAX_CYCLE_SECONDS}s atingido na síntese — "
                  f"resto fica p/ o próximo ciclo.")
            break
        neuron_id = amb['neuron_id']
        print(f"  [Synthesis] Resolvendo ambiguidade para o neurônio: {neuron_id}")
        
        # 1. Obter classificação do Diff Semântico
        diff_result = run_semantic_diff(amb['content_a'], amb['content_b'])
        
        # 2. Chamar LLM para Síntese
        prompt = f"TÓPICO: {neuron_id}\nVERSÃO A (Tese):\n{amb['content_a']}\n\nVERSÃO B (Antítese):\n{amb['content_b']}\n\nCATEGORIA DIFF: {diff_result.category}\nRACIOCÍNIO DIFF: {diff_result.reasoning}"
        
        try:
            # Papel "synthesis": herda do Dreamer se não houver HIVE_SYNTHESIS_*
            synthesis: SynthesisOutput = call_llm_with_fallback(
                "synthesis", prompt, synthesis_prompt, SynthesisOutput
            )
            
            if synthesis.conflict_resolved:
                # 3. Atualizar Atlas (Markdown)
                neuron = conn.execute("SELECT * FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
                if neuron and neuron['source_file']:
                    # Convenção: source_file relativo a SINAPSE_HOME (ex. "cerebro/atlas/topico/fato.md")
                    sf = Path(neuron['source_file'])
                    atlas_path = sf if sf.is_absolute() else Path(SINAPSE_HOME) / sf

                    if not atlas_path.exists():
                        print(f"  [!] Arquivo do Atlas não encontrado: {atlas_path} — pulando escrita em Markdown.")
                    else:
                        # Preserva histórico no Markdown
                        now = datetime.now()
                        history_entry = f"\n\n---\n### Histórico de Síntese ({now.strftime('%Y-%m-%d %H:%M')})\n"
                        history_entry += f"**Lógica:** {synthesis.logic_applied}\n"
                        history_entry += f"**Proveniência:** {synthesis.provenance_summary}\n"
                        history_entry += f"**Hashes Fundidos:** {', '.join(synthesis.parent_hashes)}\n"

                        # Preserva o frontmatter original, atualizando apenas last_updated e source
                        existing = atlas_path.read_text()
                        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", existing, re.DOTALL)
                        if fm_match:
                            fm_lines = []
                            seen_keys = set()
                            for line in fm_match.group(1).split("\n"):
                                key = line.split(":", 1)[0].strip()
                                if key == "last_updated":
                                    fm_lines.append(f"last_updated: {now.strftime('%Y-%m-%d %H:%M')}")
                                    seen_keys.add(key)
                                elif key == "source":
                                    fm_lines.append("source: hive-synthesizer")
                                    seen_keys.add(key)
                                else:
                                    fm_lines.append(line)
                            if "last_updated" not in seen_keys:
                                fm_lines.append(f"last_updated: {now.strftime('%Y-%m-%d %H:%M')}")
                            if "source" not in seen_keys:
                                fm_lines.append("source: hive-synthesizer")
                            frontmatter_block = "---\n" + "\n".join(fm_lines) + "\n---\n"
                        else:
                            frontmatter_block = f"---\nlast_updated: {now.strftime('%Y-%m-%d %H:%M')}\nsource: hive-synthesizer\n---\n"

                        with open(atlas_path, "w") as f:
                            # Re-escreve o arquivo com o frontmatter preservado, o novo conteúdo e o histórico
                            f.write(frontmatter_block)
                            f.write(synthesis.final_content)
                            f.write(history_entry)

                        print(f"  [+] Atlas atualizado: {neuron['source_file']}")

                # 4. Atualizar Tabela neurons
                new_hash = hashlib.sha256(synthesis.final_content.encode('utf-8')).hexdigest()[:16]
                conn.execute("""
                    UPDATE neurons 
                    SET content = ?, hash = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (synthesis.final_content, new_hash, neuron_id))
                
                # 5. Marcar ambiguidade como sintetizada
                conn.execute("UPDATE ambiguities SET status = 'synthesized' WHERE id = ?", (amb['id'],))
                conn.commit()
                # P2: push synthesized neuron to Graphiti temporal graph (best-effort).
                # Graphiti é um orgão do lobulo temporal do cerebro (mora em
                # integrations/graphiti/, antes em core/graphiti_client.py).
                try:
                    from integrations.graphiti import push_neuron
                    push_neuron(neuron_id, synthesis.final_content, source="dream")
                except ImportError:
                    pass
                # P4: index synthesized neuron into LightRAG knowledge graph (best-effort).
                # Alimenta o sinapse_rag_query via MCP. Falha nunca aborta a síntese.
                try:
                    from core.lightrag_index import index_memory
                    asyncio.run(index_memory(
                        synthesis.final_content,
                        metadata={"neuron_id": neuron_id, "source": "dream_cycle"},
                    ))
                except ImportError:
                    pass
                except Exception as e:
                    print(f"  [LightRAG] index ignorado (best-effort): {e}")
                print(f"  [v] Síntese concluída: {synthesis.logic_applied}")
            else:
                print(f"  [!] Conflito não resolvido pela LLM: {synthesis.logic_applied}")
                
        except pydantic.ValidationError as e:
            print(f"  [Error] ValidationError em SynthesisOutput para {neuron_id}: {e.errors()}")
        except Exception as e:
            print(f"  [Error] Falha na síntese de {neuron_id}: {e}")

    conn.close()

def run_visual_dream_stage():
    """Processa imagens na inbox visual e as transforma em memórias estruturadas."""
    print("\n=== Estágio de Sonho Visual (Visual Dreamer) ===")
    from core.database import add_visual_memory
    
    from core import paths as cp
    inbox_visual = cp.INBOX_VISUAL                 # cortex/parietal/inbox/visual
    atlas_visual = cp.CAPTURAS_VISUAIS             # cortex/occipital/capturas-visuais
    atlas_visual.mkdir(parents=True, exist_ok=True)
    
    if not inbox_visual.exists():
        print("  Pasta de inbox visual não encontrada.")
        return

    # 1. Escanear imagens não processadas
    images = list(inbox_visual.glob("*.png"))
    if not images:
        print("  Nenhuma imagem pendente na inbox visual.")
        return

    conn = get_connection()
    processed_count = 0
    skipped_placeholder = 0

    for img_path in images:
        # Verifica se já está no banco
        exists = conn.execute("SELECT 1 FROM visual_memories WHERE image_path = ?", (str(img_path),)).fetchone()
        if exists:
            continue

        # F9 GATING: pula placeholders de teste (< 1 KB) e arquivos vazios.
        # O LLM Vision gasta ~35s por imagem mesmo quando ela é placeholder
        # (timeout + retry + parsing), o que estoura o budget do ciclo
        # (visual_dream_ms=544s = 66% do total). O ciclo de 23/06 terminou
        # com BUDGET_EXHAUSTED por causa disso. Corrigido em 2026-06-23.
        try:
            if img_path.stat().st_size < 1024:
                print(f"  [Vision] Pulando {img_path.name} (placeholder < 1KB)")
                skipped_placeholder += 1
                continue
        except OSError as e:
            print(f"  [Vision] Erro ao inspecionar {img_path.name}: {e}. Pulando.")
            continue

        print(f"  [Vision] Processando: {img_path.name}...")
        
        try:
            # 2. Chamar LLM Vision — papel "vision" (herda do Dreamer se ausente)
            analysis: VisionAnalysis = call_llm_with_fallback(
                "vision",
                "Analise esta imagem capturada.",
                vision_prompt,
                VisionAnalysis,
                image_path=str(img_path)
            )
            
            # 3. Salvar no Banco
            metadata = {
                "inferred_topics": analysis.inferred_topics,
                "importance_score": analysis.importance_score,
                "source": "visual_dreamer"
            }
            add_visual_memory(
                image_path=str(img_path),
                description=analysis.description,
                ocr_text=analysis.ocr,
                metadata=metadata
            )
            
            # 4. Criar Nota Markdown no Atlas
            safe_name = img_path.stem.lower().replace(" ", "_")
            note_file = atlas_visual / f"{safe_name}.md"
            
            content = f"""---
type: visual_memory
importance: {analysis.importance_score}
topics: {', '.join(analysis.inferred_topics)}
last_updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
source_image: {img_path.name}
---
# Memória Visual: {img_path.stem}

## Descrição
{analysis.description}

## OCR (Texto Extraído)
```text
{analysis.ocr}
```

## Tópicos Inferidos
{', '.join([f"#{t}" for t in analysis.inferred_topics])}

---
![[../../inbox/visual/{img_path.name}]]
"""
            with open(note_file, "w") as f:
                f.write(content)
                
            processed_count += 1
            print(f"  [+] Memória visual indexada: {note_file.name}")
            
        except pydantic.ValidationError as e:
            print(f"  [Error] ValidationError em VisionAnalysis para {img_path.name}: {e.errors()}")
        except Exception as e:
            print(f"  [Error] Falha ao processar {img_path.name}: {e}")

    conn.close()
    suffix = f" ({skipped_placeholder} placeholders pulados)" if skipped_placeholder else ""
    print(f"=== Estágio Visual Concluído ({processed_count} imagens processadas{suffix}) ===")

# ---------------------------------------------------------------------------
# Fluxo Principal (Main Loop)
# ---------------------------------------------------------------------------

def _route_and_persist_project(conn, now, proj, distilled, proj_obs_ids, mark_obs) -> int:
    """Roteia + persiste os fatos de UM projeto (neurônios .md + tabela neurons).

    Extraído do loop principal p/ a resiliência F4.0: o chamador envolve em try/except,
    isolando a falha de um projeto sem abortar o ciclo. Erros (LLM/DB) sobem; quem
    isola decide preservar as obs p/ reprocessar. Retorna nº de neurônios persistidos."""
    from core import paths as cp
    routed = agent_route(distilled.facts)
    if not routed or not routed.routed_facts:
        mark_obs(2, proj_obs_ids)
        print(f"  [Pipeline] Projeto '{proj}': {len(proj_obs_ids)} obs em quarentena (roteador falhou).")
        return 0

    persisted = 0
    first_nid: str | None = None
    fact_map = {f.id: f for f in distilled.facts}
    for r in routed.routed_facts:
        fact = fact_map.get(r.fact_id)
        if not fact:
            continue

        safe_topic = re.sub(r'[^a-z0-9_]', '', r.topic.lower().replace(" ", "_")) or "general"
        # F6 PREVENTION: nome semântico = slug do label + 8 chars do hash para unicidade.
        # Garante legibilidade no grafo Obsidian sem sacrificar determinismo.
        _label_slug = re.sub(r'[^a-z0-9]+', '-', fact.label.lower())[:40].strip('-')
        _hash_short = fact.id.replace("fact-", "")[:8] if fact.id.startswith("fact-") else fact.id[:8]
        nid = f"neuronio-{_label_slug}-{_hash_short}" if _label_slug else f"neuronio-{_hash_short}"
        note_file = cp.TEMPORAL / proj / safe_topic / f"{nid}.md"
        note_file.parent.mkdir(parents=True, exist_ok=True)
        aliases_val = json.dumps([fact.alias] if fact.alias else [])

        content = f"""---
type: {fact.type}
project: {proj}
topic: {safe_topic}
integrity_hash: {fact.integrity_hash}
aliases: {aliases_val}
last_updated: {now.strftime('%Y-%m-%d %H:%M')}
source: hive-dreamer
---
# {fact.label}

{fact.content}

## Evidência (Groundedness)
> {fact.source_quotes[0] if fact.source_quotes else 'N/A'}

## Sinapses
- projeto:: [[{proj}]]
- tópico:: [[{safe_topic}]]
- lobo:: [[cortex-temporal]]
- córtex:: [[cortex]]
"""

        source_rel = str(note_file.relative_to(SINAPSE_HOME))
        conn.execute("""
            INSERT INTO neurons (id, label, type, content, hash, source_file, topic, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                label=excluded.label,
                hash=excluded.hash,
                source_file=excluded.source_file,
                topic=excluded.topic,
                updated_at=CURRENT_TIMESTAMP
        """, (nid, fact.label, fact.type, fact.content, fact.integrity_hash, source_rel, safe_topic))
        conn.commit()

        mode = "a" if r.action in ["append", "merge"] and note_file.exists() else "w"
        if mode == "a":
            content = f"\n\n---\n## Atualização de {now.strftime('%Y-%m-%d')}\n{fact.content}\n"
        with open(note_file, mode) as f:
            f.write(content)

        print(f"  [+] Neurônio {r.action}: {proj}/{safe_topic}/{nid}.md")
        persisted += 1
        if first_nid is None:
            first_nid = nid

    # Liga as observações ao primeiro neurônio criado no lote (FK §13.2).
    # Não sobrescreve ligações já existentes de ciclos anteriores.
    if first_nid:
        for oid in proj_obs_ids:
            conn.execute(
                "UPDATE observations SET neuron_id = ? WHERE id = ? AND neuron_id IS NULL",
                (first_nid, oid),
            )
        conn.commit()

    # Obs do projeto consolidadas só após persistência bem-sucedida.
    mark_obs(1, proj_obs_ids)
    return persisted


def _run_dream_cycle_inner() -> Dict[str, int]:
    """Corpo do ciclo. Retorna contadores p/ a telemetria M9 (ver run_dream_cycle)."""
    from core.telemetry import span
    print(f"=== Hive-Mind: Ciclo de Sonho V2 (Corporate Grade) ===")
    cycle_t0 = time.perf_counter()
    stage_metrics: Dict[str, float] = {}

    def mark_stage(stage_name: str, started_at: float) -> None:
        stage_metrics[stage_name] = round((time.perf_counter() - started_at) * 1000.0, 3)

    # --- ESTÁGIO DE DOCUMENTOS (PDF/DOCX) ---
    doc_t0 = time.perf_counter()
    with span("dream.document_ingest", {}):
        try:
            from scripts.knowledge.document_ingest import run_ingestion
            run_ingestion()
        except Exception as e:
            print(f"  [Error] Falha no estágio de documentos: {e}")
        finally:
            mark_stage("document_ingest_ms", doc_t0)

    # --- ESTÁGIO VISUAL ---
    visual_t0 = time.perf_counter()
    with span("dream.visual", {}):
        run_visual_dream_stage()
    mark_stage("visual_dream_ms", visual_t0)
    
    # --- INGESTÃO ---
    conn = get_connection()
    ensure_migrations(conn)
    obs = fetch_balanced_observations(conn)

    if not obs:
        print("  Cérebro descansado. Sem novas observações na fila.")
        conn.close()
        return {"observations": 0, "persisted": 0}

    # Arquiva os logs brutos para a Inbox sensorial (cortex/parietal/inbox)
    from core import paths as cp
    now = datetime.now()
    inbox_dir = cp.INBOX_ROOT / now.strftime("%Y/%m/%d")
    inbox_dir.mkdir(parents=True, exist_ok=True)
    session_file = inbox_dir / f"{now.strftime('%H%M')}-session.md"

    logs_context = ""
    with open(session_file, "w") as f:
        f.write(f"# Sessão Episódica: {now.strftime('%Y-%m-%d %H:%M')}\n\n")
        for o in obs:
            entry = f"[{o['type']}] {o['title']}: {o['content']}"
            f.write(f"## {entry}\n\n")
            logs_context += f"- {entry}\n"

    print(f"  [Inbox] Logs brutos garantidos em: {session_file.relative_to(SINAPSE_HOME)}")

    obs_ids = [o['id'] for o in obs]

    def _mark_observations(status: int, ids: Optional[List[str]] = None):
        """Marca observações como consolidadas/quarentena. Restringe a `ids` se passado."""
        target_ids = ids if ids is not None else obs_ids
        for oid in target_ids:
            conn.execute("UPDATE observations SET archived = ? WHERE id = ?", (status, oid))
        conn.commit()

    # --- SEGREGAÇÃO POR PROJETO (Phase HM: project plumbing) ---
    # A coluna `observations.project` é a fonte da verdade: cada neurônio novo
    # deve aterrissar em cortex/temporal/{projeto_origem}/{topico}/.
    # Quando a janela de 30 obs mistura projetos, rodamos um pipeline
    # Distiller→Validator→Router POR PROJETO para não contaminar o córtex de um
    # projeto com fatos de outro. Obs sem project caem no default.
    DEFAULT_PROJECT = os.environ.get("HIVE_DEFAULT_PROJECT", "Hive-Mind")

    def _resolve_project(o) -> str:
        p = (o["project"] or "").strip() if "project" in o.keys() else ""
        return p or DEFAULT_PROJECT

    project_buckets: Dict[str, List[Any]] = {}
    for o in obs:
        proj = _resolve_project(o)
        project_buckets.setdefault(proj, []).append(o)

    if len(project_buckets) > 1:
        projects_summary = ", ".join(
            f"{p}={len(v)}" for p, v in sorted(project_buckets.items())
        )
        print(f"  [Plumbing] Janela multi-projeto detectada ({len(project_buckets)} projetos: {projects_summary}). Segregando pipeline por projeto.")

    # --- PIPELINE DE INTELIGÊNCIA (segregado por projeto) ---
    distill_t0 = time.perf_counter()
    distilled_by_project: Dict[str, DistillerOutput] = {}
    distill_failures: List[str] = []
    distill_empties: List[str] = []
    project_errors: List[str] = []   # F4.0: projetos que ERRARAM (LLM/DB) — isolados

    with span("dream.distill", {"obs_count": len(obs), "projects": len(project_buckets)}):
        for proj, proj_obs in project_buckets.items():
            proj_ids = [o["id"] for o in proj_obs]
            try:
                proj_logs = "\n".join(f"- [{o['type']}] {o['title']}: {o['content']}" for o in proj_obs)
                print(f"  [Distiller] Projeto '{proj}': processando {len(proj_obs)} observações...")
                distilled, distill_status = agent_distill_and_validate(proj_logs)
                if distill_status == "failed":
                    _mark_observations(2, proj_ids)
                    distill_failures.append(proj)
                    print(f"  [Pipeline] Projeto '{proj}': {len(proj_ids)} obs em quarentena.")
                elif distill_status == "empty" or not distilled or not distilled.facts:
                    _mark_observations(1, proj_ids)
                    distill_empties.append(proj)
                    print(f"  [Distiller] Projeto '{proj}': sem fatos extraídos.")
                else:
                    distilled_by_project[proj] = distilled
            except Exception as e:
                # F4.0 resiliência: erro (LLM/`database is locked`/etc.) num projeto NÃO
                # aborta o ciclo. Obs ficam archived=0 (reprocessa no próximo ciclo) —
                # não quarentena, pois é erro transitório, não dado ruim.
                project_errors.append(proj)
                print(f"  [Resiliência] Projeto '{proj}' falhou no distill: {e}. Obs preservadas p/ reprocessar.")
                continue
    mark_stage("distill_validate_ms", distill_t0)

    if not distilled_by_project:
        # Nenhum projeto produziu fatos: nada a rotear/persistir.
        # P9 review: mesmo em ciclo empty, geramos spans `dream.persist` (zero
        # projects) e `dream.synthesis` (skipped) para rastreabilidade no Langfuse.
        with span("dream.persist", {"projects": 0}) as _persist_span:
            if _persist_span is not None:
                _persist_span.set_attribute("persisted", "0")
        _budget_left = MAX_CYCLE_SECONDS - (time.perf_counter() - cycle_t0)
        with span("dream.synthesis", {"budget_left": _budget_left, "skipped": "empty"}):
            pass  # ciclo empty: nada a sintetizar
        stage_metrics["total_cycle_ms"] = round((time.perf_counter() - cycle_t0) * 1000.0, 3)
        if distill_failures and not distill_empties:
            _persist_cycle_metrics(stage_metrics, status="failed")
        else:
            _persist_cycle_metrics(stage_metrics, status="empty")
        conn.close()
        return

    # --- ROTEAMENTO + PERSISTÊNCIA ANATÔMICA (por projeto) ---
    route_t0 = time.perf_counter()
    storage_t0 = time.perf_counter()  # só vai ser usado se a fase de persistência rodar
    total_persisted = 0
    print("  [Storage] Persistindo neurônios no córtex temporal...")
    with span("dream.persist", {"projects": len(distilled_by_project)}) as _persist_span:
        for proj, distilled in distilled_by_project.items():
            proj_obs_ids = [o["id"] for o in project_buckets[proj]]
            try:
                total_persisted += _route_and_persist_project(
                    conn, now, proj, distilled, proj_obs_ids, _mark_observations)
            except Exception as e:
                # F4.0: erro num projeto (LLM/`database is locked`/IO) não aborta o ciclo.
                # Obs ficam archived=0 p/ reprocessar (não quarentena — erro transitório).
                project_errors.append(proj)
                print(f"  [Resiliência] Projeto '{proj}' falhou na persistência: {e}. Obs preservadas p/ reprocessar.")
                continue
        if _persist_span is not None:
            _persist_span.set_attribute("persisted", str(total_persisted))
    # route_ms = duração do bloco inteiro (roteamento + persistência).
    # Para deitar decomposto, teríamos que medir `agent_route` e o loop
    # interno separadamente; por ora, mede-se o agregado.
    mark_stage("route_and_persist_ms", route_t0)

    # --- SÍNTESE AUTÔNOMA (Fase 9) ---
    synth_t0 = time.perf_counter()
    # deadline = orçamento restante do ciclo (teto total MAX_CYCLE_SECONDS)
    _budget_left = MAX_CYCLE_SECONDS - (time.perf_counter() - cycle_t0)
    with span("dream.synthesis", {"budget_left": _budget_left}):
        run_synthesis_cycle(deadline=time.monotonic() + max(0.0, _budget_left))
    mark_stage("synthesis_ms", synth_t0)

    # --- CAMADA DE NAVEGAÇÃO (MOCs) — §7.6 ---
    try:
        # O módulo generate_mocs está em scripts/knowledge/, mas o sys.path
        # do systemd unit contém só o project root (não scripts/knowledge/).
        # Import via path completo para evitar "No module named 'generate_mocs'".
        # Corrigido em 2026-06-23.
        from scripts.knowledge.generate_mocs import build_mocs
        moc_t0 = time.perf_counter()
        build_mocs(verbose=True)
        mark_stage("mocs_ms", moc_t0)
    except Exception as e:
        print(f"  [!] Geração de MOCs falhou (não-fatal): {e}")

    stage_metrics["total_cycle_ms"] = round((time.perf_counter() - cycle_t0) * 1000.0, 3)
    status_final = "ok" if total_persisted > 0 else "failed"
    _persist_cycle_metrics(stage_metrics, status=status_final)

    if project_errors:
        print(f"  [Resiliência] {len(project_errors)} projeto(s) falharam e serão reprocessados: {', '.join(project_errors)}")
    print(f"=== Ciclo de Sonho Concluído ({total_persisted} neurônios persistidos em {len(distilled_by_project)} projeto(s)) ===")
    conn.close()
    return {"observations": len(obs), "persisted": total_persisted,
            "errors": len(project_errors)}


def _log_dream_cycle(started_iso: str, t0: float, obs_count: int, reason: str) -> None:
    """Grava 1 linha em dream_cycle_log (métrica M9, doc 08 §14.4-P2). Não-fatal."""
    try:
        duration = round(time.perf_counter() - t0, 3)
        conn = get_connection()
        ensure_migrations(conn)
        conn.execute(
            """INSERT INTO dream_cycle_log
               (started_at, ended_at, duration_s, observations_processed,
                ambiguities_processed, ended_reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (started_iso, datetime.now().isoformat(), duration, obs_count, 0, reason),
        )
        conn.commit()
        conn.close()
        print(f"  [M9] dream_cycle_log: {reason} em {duration}s ({obs_count} obs)")
    except Exception as e:  # telemetria nunca derruba o ciclo
        print(f"  [M9] falha ao registrar dream_cycle_log (não-fatal): {e}")


def run_dream_cycle() -> Dict[str, int]:
    """Wrapper de telemetria M9: cronometra o ciclo e registra o desfecho
    (ok / failed / empty / BUDGET_EXHAUSTED / error) em dream_cycle_log.

    Mantém a assinatura pública usada pelos timers/__main__ — o corpo real é
    `_run_dream_cycle_inner`. O `finally` garante 1 linha por ciclo mesmo se o
    inner levantar exceção (registrada como 'error')."""
    from core.telemetry import init_telemetry, flush_telemetry
    init_telemetry()
    started_iso = datetime.now().isoformat()
    t0 = time.perf_counter()
    obs_count = 0
    reason = "error"
    result: Dict[str, int] = {"observations": 0, "persisted": 0}
    try:
        result = _run_dream_cycle_inner() or result
        obs_count = result.get("observations", 0)
        elapsed = time.perf_counter() - t0
        if obs_count == 0:
            reason = "empty"
        elif elapsed >= MAX_CYCLE_SECONDS:
            reason = "BUDGET_EXHAUSTED"
        elif result.get("errors", 0) > 0:
            # F4.0: o ciclo concluiu, mas ≥1 projeto falhou (e será reprocessado).
            reason = "partial"
        else:
            reason = "ok" if result.get("persisted", 0) > 0 else "failed"
        return result
    except Exception:
        reason = "error"
        raise
    finally:
        flush_telemetry()
        _log_dream_cycle(started_iso, t0, obs_count, reason)


def _persist_cycle_metrics(metrics: Dict[str, float], status: str) -> None:
    """Persiste métricas de latência do ciclo para observabilidade operacional."""
    metrics_dir = Path(SINAPSE_HOME) / "logs" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "captured_at": datetime.now().isoformat(),
        "stages_ms": metrics,
    }
    latest = metrics_dir / "dream_cycle_latest.json"
    history = metrics_dir / f"dream_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(history, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  [Metrics] Dream Cycle: {metrics}")


if __name__ == "__main__":
    # SIGTERM handler: systemd oneshot envia SIGTERM (não SIGINT) no stop manual.
    # Default Python termina sem rodar `finally`/`atexit` — perderíamos o flush
    # de spans e o log do ciclo. Convertemos SIGTERM em SystemExit para cair no
    # `finally: flush_telemetry()` em run_dream_cycle().
    import signal
    try:
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    except (ValueError, OSError):
        pass  # SIGTERM só pode ser tratado no main thread
    if not LLM_PROVIDER or not LLM_MODEL:
        print("ERRO: Hive-Dreamer não configurado.")
        sys.exit(1)
    run_dream_cycle()
