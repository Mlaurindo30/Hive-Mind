import os
import sys
import pytest
from pathlib import Path

# Módulo importável (a lógica vive no nome underscore; o hifenizado é só shim).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.knowledge import sinapse_zettelkasten as zk


class TestSinapseZettelkasten:
    """U6: Suíte de testes unitários para a Fase 4.2 (Auto-Zettelkasten)"""

    def test_sanitize_slug_basic(self):
        """U6.1: Valida a sanitização simples do título em slug legível."""
        assert zk._sanitize_slug("Minha Nota Incrível!") == "minha-nota-incrivel"
        assert zk._sanitize_slug("Otimização de Contexto em RAG") == "otimizacao-de-contexto-em-rag"
        assert zk._sanitize_slug("  Busca Assíncrona com ThreadPool...  ") == "busca-assincrona-com-threadpool"

    def test_sanitize_slug_with_special_chars_and_emojis(self):
        """U6.2: Emojis, caracteres especiais e acentuações complexas são limpos."""
        assert zk._sanitize_slug("🚀 Busca Concorrente 100% Funcional! ✅") == "busca-concorrente-100-funcional"
        assert zk._sanitize_slug("Conceito: A/B Testing e C++") == "conceito-ab-testing-e-c"
        assert zk._sanitize_slug("") == "untitled-atom"

    def test_atomic_write_creates_file(self, tmp_path):
        """U6.3: Escrita atômica cria o arquivo com o conteúdo correto."""
        dest = tmp_path / "test-atom.md"
        content = "---\ntags: [atom]\n---\n# Test Title\nSome content."
        
        assert zk._atomic_write(dest, content) is True
        assert dest.exists() is True
        assert dest.read_text() == content

    def test_split_monolithic_file_mock_flow(self, monkeypatch, tmp_path):
        """U6.4: O split_monolithic_file lê o monolito, chama o Ollama (mockado) e gera os arquivos."""
        monolith = tmp_path / "Monolith.md"
        monolith.write_text("# Monolithic note content with patterns.")

        output_atoms_dir = tmp_path / "atoms"
        
        mock_ollama_response = """
---
tags: [atom]
aliases: []
created: "2026-05-24"
updated: "2026-05-24"
confidence: certain
---
# Primeira Nota Atômica

Esta é a explicação da primeira ideia atômica extraída.

## Related
- [[Hermes]] — orquestrador principal

---

# Segunda Nota Atômica

Explicação da segunda ideia atômica.

## Related
- [[Graphify]] — indexador
"""

        # Mock da chamada HTTP para o Ollama
        def mock_query_ollama(prompt, system_prompt):
            return mock_ollama_response

        # Mock do subprocesso do Graphify update (para evitar indexação real do vault)
        def mock_subprocess_run(*args, **kwargs):
            class DummyResult:
                returncode = 0
                stdout = "success"
                stderr = ""
            return DummyResult()

        monkeypatch.setattr(zk, "_query_ollama", mock_query_ollama)
        monkeypatch.setattr("subprocess.run", mock_subprocess_run)

        created_files = zk.split_monolithic_file(str(monolith), str(output_atoms_dir))
        
        assert len(created_files) == 2
        
        # Verificar se os arquivos foram criados com os nomes estruturados corretos
        slug1 = zk._sanitize_slug("Primeira Nota Atômica")
        slug2 = zk._sanitize_slug("Segunda Nota Atômica")
        
        file1 = output_atoms_dir / f"{zk.datetime.now().strftime('%Y-%m-%d')}-{slug1}.md"
        file2 = output_atoms_dir / f"{zk.datetime.now().strftime('%Y-%m-%d')}-{slug2}.md"
        
        assert file1.exists() is True
        assert file2.exists() is True
        assert "Primeira Nota Atômica" in file1.read_text()
        assert "Segunda Nota Atômica" in file2.read_text()
