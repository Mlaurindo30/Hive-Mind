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
import pydantic
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configura paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

# Load Env
ENV_PATH = Path(SINAPSE_HOME) / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH)
except ImportError:
    pass

from core.database import get_connection, ensure_migrations
from core.schemas.dream_models import DistillerOutput, ValidatorOutput, RouterOutput
from core.schemas.vision_models import VisionAnalysis
from core.schemas.synthesis_models import SynthesisOutput, SynthesisTask

# ---------------------------------------------------------------------------
# Carregamento de Contratos e Prompts (YAML)
# ---------------------------------------------------------------------------
SCHEMAS_DIR = Path(SINAPSE_HOME) / "core" / "schemas"
PROMPTS_DIR = SCHEMAS_DIR / "prompts"

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
    
    atlas_root = Path(SINAPSE_HOME) / "cerebro" / "atlas"
    existing_topics = [d.name for d in atlas_root.iterdir() if d.is_dir()] if atlas_root.exists() else []
    
    prompt = f"TÓPICOS EXISTENTES NO ATLAS:\n{existing_topics}\n\nFATOS A SEREM ROTEADOS:\n{json.dumps([f.model_dump() for f in facts], indent=2)}"

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

def run_synthesis_cycle():
    """Busca ambiguidades pendentes e resolve-as via Síntese Dialética."""
    from scripts.semantic_diff import run_semantic_diff
    
    print("\n=== Estágio de Síntese Dialética (Hive-Mind Brain) ===")
    conn = get_connection()
    ambiguities = conn.execute("SELECT * FROM ambiguities WHERE status = 'pending'").fetchall()
    
    if not ambiguities:
        print("  Nenhuma ambiguidade pendente para síntese.")
        conn.close()
        return

    for amb in ambiguities:
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
    
    inbox_visual = Path(SINAPSE_HOME) / "cerebro" / "inbox" / "visual"
    atlas_visual = Path(SINAPSE_HOME) / "cerebro" / "atlas" / "visual"
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
    
    for img_path in images:
        # Verifica se já está no banco
        exists = conn.execute("SELECT 1 FROM visual_memories WHERE image_path = ?", (str(img_path),)).fetchone()
        if exists:
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
    print(f"=== Estágio Visual Concluído ({processed_count} imagens processadas) ===")

# ---------------------------------------------------------------------------
# Fluxo Principal (Main Loop)
# ---------------------------------------------------------------------------

def run_dream_cycle():
    print(f"=== Hive-Mind: Ciclo de Sonho V2 (Corporate Grade) ===")
    
    # --- ESTÁGIO DE DOCUMENTOS (PDF/DOCX) ---
    try:
        from scripts.document_ingest import run_ingestion
        run_ingestion()
    except Exception as e:
        print(f"  [Error] Falha no estágio de documentos: {e}")

    # --- ESTÁGIO VISUAL ---
    run_visual_dream_stage()
    
    # --- INGESTÃO ---
    conn = get_connection()
    ensure_migrations(conn)
    obs = conn.execute("SELECT * FROM observations WHERE archived = 0 ORDER BY created_at LIMIT 30").fetchall()

    if not obs:
        print("  Cérebro descansado. Sem novas observações na fila.")
        conn.close()
        return

    # Arquiva os logs brutos para a Inbox (Rastro Temporal Completo)
    now = datetime.now()
    inbox_dir = Path(SINAPSE_HOME) / "cerebro" / "inbox" / now.strftime("%Y/%m/%d")
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

    def _mark_observations(status: int):
        """Marca as observações desta sessão (0=pendente, 1=consolidado, 2=quarentena)."""
        for oid in obs_ids:
            conn.execute("UPDATE observations SET archived = ? WHERE id = ?", (status, oid))
        conn.commit()

    # --- PIPELINE DE INTELIGÊNCIA ---
    distilled, distill_status = agent_distill_and_validate(logs_context)

    if distill_status == "failed":
        # Falha de pipeline (exceções após max_retries): quarentena para reprocessamento posterior
        _mark_observations(2)
        print(f"  [Pipeline] {len(obs_ids)} observações enviadas para quarentena (archived=2)")
        conn.close()
        return

    if not distilled or not distilled.facts:
        # Sem fatos relevantes não é falha: marca como consolidado para não reprocessar
        _mark_observations(1)
        print("  [Final] Nenhum fato de longo prazo extraído desta sessão.")
        conn.close()
        return

    routed = agent_route(distilled.facts)
    if not routed or not routed.routed_facts:
        # Falha no roteador: quarentena (podem ser reprocessadas depois)
        _mark_observations(2)
        print(f"  [Pipeline] {len(obs_ids)} observações enviadas para quarentena (archived=2)")
        print("  [Final] Falha no roteamento semântico.")
        conn.close()
        return

    # --- PERSISTÊNCIA NO ATLAS ---
    print("  [Storage] Persistindo no Atlas Infinito...")
    atlas_root = Path(SINAPSE_HOME) / "cerebro" / "atlas"
    
    # Dicionário mapeando fact_id -> fact Pydantic object
    fact_map = {f.id: f for f in distilled.facts}
    
    for r in routed.routed_facts:
        fact = fact_map.get(r.fact_id)
        if not fact: continue
        
        # Cria ou atualiza a pasta do tópico
        safe_topic = r.topic.lower().replace(" ", "_")
        topic_dir = atlas_root / safe_topic
        topic_dir.mkdir(parents=True, exist_ok=True)
        
        note_file = topic_dir / f"{fact.id}.md"
        
        # Formato da nota ancorada
        content = f"""---
type: {fact.type}
topic: {safe_topic}
integrity_hash: {fact.integrity_hash}
last_updated: {now.strftime('%Y-%m-%d %H:%M')}
source: hive-dreamer
---
# {fact.label}

{fact.content}

## Evidência (Groundedness)
> {fact.source_quotes[0] if fact.source_quotes else 'N/A'}

#consolidated #{safe_topic}
"""
        # Se for append ou merge, adiciona no fim do arquivo (poderia ter lógica de read/write mais complexa)
        mode = "a" if r.action in ["append", "merge"] and note_file.exists() else "w"
        if mode == "a":
            content = f"\n\n---\n## Atualização de {now.strftime('%Y-%m-%d')}\n{fact.content}\n"
            
        with open(note_file, mode) as f:
            f.write(content)
            
        print(f"  [+] Nota {r.action}: {safe_topic}/{fact.id}.md")

    # Roteamento bem-sucedido: marca observações como consolidadas (archived=1)
    _mark_observations(1)

    # --- SÍNTESE AUTÔNOMA (Fase 9) ---
    run_synthesis_cycle()

    print("=== Ciclo de Sonho Concluído com Sucesso ===")
    conn.close()

if __name__ == "__main__":
    if not LLM_PROVIDER or not LLM_MODEL:
        print("ERRO: Hive-Dreamer não configurado.")
        sys.exit(1)
    run_dream_cycle()
