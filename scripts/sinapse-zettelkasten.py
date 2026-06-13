#!/usr/bin/env python3
"""
Sinapse Agent — Auto-Zettelkasten Generator (Fase 4.2)
Particiona notas monolíticas complexas em notas conceituais atômicas (atoms)
utilizando LLM local via Ollama (qwen2.5-coder:3b) com escrita atômica e WikiLinks.

Uso:
  python3 scripts/sinapse-zettelkasten.py split <source_file> [target_dir]
"""

import json
import os
import re
import sys
import time
import unicodedata
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5-coder:3b"
OLLAMA_TIMEOUT = 120  # 2 minutos limite para geração densa

def _log(level: str, msg: str, **kwargs):
    """Exibe log estruturado simples."""
    meta = " ".join(f"{k}={v}" for k, v in kwargs.items())
    print(f"[sinapse-zettel] {level.upper()}: {msg} {meta}".strip(), file=sys.stderr)


def _sanitize_slug(title: str) -> str:
    """Converte o título em um slug de arquivo legível e limpo."""
    # Remover emojis/unicode especiais
    text = title.strip()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    # Remover caracteres especiais, manter letras, números e espaços
    text = re.sub(r"[^\w\s-]", "", text)
    # Substituir espaços/underscores por hífens
    text = re.sub(r"[_\s]+", "-", text)
    # Limpar hífens duplicados e converter para lowercase
    text = re.sub(r"-+", "-", text).strip("-")
    slug = text.lower()
    return slug[:80] if slug else "untitled-atom"


def _atomic_write(filepath: Path, content: str) -> bool:
    """Escreve o conteúdo de forma atômica e crash-safe no disco."""
    try:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        # Criar arquivo temporário no mesmo diretório
        fd, tmp_path = tempfile.mkstemp(dir=str(filepath.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            # Substituição atômica (replace)
            os.replace(tmp_path, str(filepath))
            return True
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise e
    except Exception as e:
        _log("error", "atomic_write_failed", path=str(filepath), error=str(e))
        return False


def _query_ollama(prompt: str, system_prompt: str) -> Optional[str]:
    """Chama a API local do Ollama para geração de texto sem stream."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "options": {
            "temperature": 0.2,  # Baixa temperatura para manter a formatação estrita
            "top_p": 0.9,
        },
        "stream": False,
    }

    try:
        req = Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except URLError as e:
        _log("error", "ollama_connection_failed", url=OLLAMA_URL, error=str(e.reason))
    except Exception as e:
        _log("error", "ollama_query_failed", error=str(e))
    return None


def split_monolithic_file(source_file: str, target_dir: str = "cerebro/atoms") -> List[str]:
    """Lê a nota monolítica, consulta o Ollama e extrai notas atômicas."""
    source_path = Path(source_file)
    target_path = Path(target_dir)

    if not source_path.exists():
        _log("error", "source_file_missing", path=str(source_path))
        return []

    _log("info", "reading_monolith", path=str(source_path))
    with open(source_path, "r") as f:
        monolith_content = f.read()

    current_date = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = f"""
Você é um especialista em Zettelkasten e gestão de conhecimento no Obsidian (Vault Cerebro).
Sua tarefa é ler o arquivo monolítico anotado enviado pelo usuário (contendo padrões, observações, aprendizados ou logs) e extrair conceitos atômicos individuais (uma única ideia clara por nota).

Para CADA ideia ou padrão conceitual atômico extraído, você DEVE gerar um bloco Markdown completo seguindo exatamente a estrutura abaixo:

---
tags: [atom]
aliases: []
created: "{current_date}"
updated: "{current_date}"
confidence: certain
---
# <Título da Nota: Frase muito curta, declarativa e autoexplicativa em Português BR>

<Explicação densa, técnica e objetiva do conceito (máximo 1 a 3 parágrafos focados em Português BR)>

## Related
- [[<Nome de outro conceito ou nota relacionada se houver>]] — como se conecta
- [[<Nome de outro conceito ou nota relacionada se houver>]] — como se conecta

--- (Separador de três traços obrigatório entre as notas)

Diretrizes Críticas:
1. Cada nota gerada deve focar em APENAS UMA ideia atômica. Nunca aglomere múltiplos assuntos na mesma nota.
2. O conteúdo deve ser em Português (BR) e de alta densidade informativa.
3. O título deve ser declarativo e ideal para ser linkado como WikiLink (ex: "ThreadPoolExecutor otimiza latencia RAG"). Evite títulos genéricos como "Busca Paralela" ou "Otimização".
4. Use o delimitador de três traços `---` em uma linha isolada apenas para separar os blocos markdown de notas diferentes.
5. Retorne APENAS os blocos markdown gerados. Não adicione saudações, explicações ou notas de introdução na sua resposta.
"""

    prompt = f"Aqui está o conteúdo do arquivo monolítico para ser particionado em notas conceituais atômicas:\n\n{monolith_content}"

    _log("info", "querying_ollama", model=OLLAMA_MODEL)
    response_text = _query_ollama(prompt, system_prompt)
    if not response_text:
        _log("error", "ollama_returned_empty")
        return []

    # Parsear a resposta do Ollama dividindo pelo separador --- que separa as notas
    # Como o frontmatter YAML também usa ---, precisamos de regex esperto
    # O Ollama separa notas com `---` isolado ou com o separador explícito `--- (Separador...)`
    raw_blocks = re.split(r"\n---\s*(?:\(Separador.*?\))?\n", response_text)
    
    created_files = []
    
    for raw_block in raw_blocks:
        block = raw_block.strip()
        if not block:
            continue
            
        # Validar se o bloco tem título em formato Markdown (# Título)
        title_match = re.search(r"^#\s+(.+)$", block, re.MULTILINE)
        if not title_match:
            continue
            
        title = title_match.group(1).strip()
        slug = _sanitize_slug(title)
        filename = f"{current_date}-{slug}.md"
        filepath = target_path / filename

        # Se o bloco não tiver o frontmatter no início (por quebra do delimitador), nós reconstituímos
        if not block.startswith("---"):
            block = f"---\ntags: [atom]\naliases: []\ncreated: \"{current_date}\"\nupdated: \"{current_date}\"\nconfidence: certain\n---\n" + block

        _log("info", "writing_atom_file", file=filename, title=title)
        if _atomic_write(filepath, block):
            created_files.append(str(filepath))

    # Atualizar o knowledge graph se existirem novos arquivos criados
    if created_files:
        _log("info", "updating_knowledge_graph")
        try:
            # Sobe até a raiz do projeto (onde está scripts/) e executa o update
            project_root = Path(__file__).resolve().parent.parent
            subprocess.run(
                ["graphify", "update", "cerebro/"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=True
            )
            _log("info", "knowledge_graph_updated", new_atoms=len(created_files))
        except Exception as e:
            _log("error", "graphify_update_failed", error=str(e))

    return created_files


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "split":
        print("Uso: python3 scripts/sinapse-zettelkasten.py split <source_file> [target_dir]")
        sys.exit(1)

    source = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "cerebro/atoms"

    files = split_monolithic_file(source, out_dir)
    print(json.dumps({"atoms_created": len(files), "files": files}, indent=2))
