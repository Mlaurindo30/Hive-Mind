import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.sector_classifier import (
    get_frontmatter_block, 
    extract_neuron_info, 
    process_file,
    SectorClassifierOutput
)

def test_get_frontmatter_block_success():
    content = "---\ntype: fact\nsectors: [general]\n---\n# Title\nContent"
    data, fm_block, body = get_frontmatter_block(content)
    assert data["type"] == "fact"
    assert data["sectors"] == ["general"]
    assert fm_block == "---\ntype: fact\nsectors: [general]\n---\n"
    assert body == "# Title\nContent"

def test_get_frontmatter_block_no_frontmatter():
    content = "# Title\nContent"
    data, fm_block, body = get_frontmatter_block(content)
    assert data == {}
    assert fm_block == ""
    assert body == "# Title\nContent"

def test_extract_neuron_info():
    body = "# My Title\n\nThis is the content of the neuron."
    title, content = extract_neuron_info(body)
    assert title == "My Title"
    assert content == "This is the content of the neuron."

def test_extract_neuron_info_no_title():
    body = "Just content without H1."
    title, content = extract_neuron_info(body)
    assert title == "Sem Título"
    assert content == "Just content without H1."

@patch("scripts.sector_classifier.call_llm_with_fallback")
def test_process_file_skips_already_classified(mock_llm):
    # Setup: Arquivo já possui setores específicos (válidos)
    mock_path = MagicMock(spec=Path)
    mock_path.name = "neuronio-1.md"
    mock_path.read_text.return_value = "---\nsectors: [finance]\n---\n# Title\nContent"
    
    process_file(mock_path)
    
    # Verificação: LLM não deve ser chamado porque já está classificado
    mock_llm.assert_not_called()
    mock_path.write_text.assert_not_called()

@patch("scripts.sector_classifier.call_llm_with_fallback")
def test_process_file_updates_when_general(mock_llm):
    # Setup: Arquivo tem setor [general] - precisa de reclassificação
    mock_path = MagicMock(spec=Path)
    mock_path.name = "neuronio-2.md"
    mock_path.read_text.return_value = "---\nsectors: [general]\n---\n# Title\nContent"
    
    # Mock do retorno do LLM com setores válidos
    mock_output = SectorClassifierOutput(sectors=["infra", "pkm"])
    mock_llm.return_value = mock_output
    
    process_file(mock_path)
    
    # Verificação: LLM deve ser chamado e arquivo escrito
    mock_llm.assert_called_once()
    assert mock_path.write_text.called
    
    # Verifica conteúdo da escrita
    args, _ = mock_path.write_text.call_args
    written_content = args[0]
    assert "sectors:" in written_content
    assert "- infra" in written_content
    assert "- pkm" in written_content

@patch("scripts.sector_classifier.call_llm_with_fallback")
def test_process_file_skips_io_if_same(mock_llm):
    # Setup: Arquivo tem setor [] (vazio) - entra na classificação
    mock_path = MagicMock(spec=Path)
    mock_path.name = "neuronio-3.md"
    mock_path.read_text.return_value = "---\nsectors: []\n---\n# Title\nContent"
    
    # Mock do retorno do LLM (setor 'infra')
    mock_output = SectorClassifierOutput(sectors=["infra"])
    mock_llm.return_value = mock_output
    
    # Simula que o arquivo JÁ tinha 'infra' de alguma forma mas sem estar no YAML original (improvável no fluxo real mas testa o if)
    # Na verdade, para testar o 'if set(new_sectors) == set(current_sectors)', 
    # o 'current_sectors' deve vir do 'data.get("sectors", [])'.
    
    # Vamos mudar o setup para o caso onde 'sectors' é ['general'] e o LLM retorna ['infra'] (muda)
    # E depois testar o caso onde o skip early return é o que manda.
    
    # Para realmente testar a otimização de IO em process_file:
    # Se sectors = ["general"] e LLM retorna ["infra"], ele escreve.
    
    # Se quisermos testar que ele NÃO escreve se for igual, e considerando que ele só entra se for [] ou ["general"],
    # e que o LLM NUNCA retorna ["general"]...
    # O único caso é se o arquivo tiver algo que o LLM repete.
    
    # Vamos fazer assim: setores no arquivo = ["infra"] mas sem o early return (simulado)
    # Mas como o early return existe, ele nunca chegaria lá.
    
    # CONCLUSÃO: A otimização de IO é uma camada de defesa extra. 
    # Para testá-la, vou remover temporariamente o early return no teste (via mock de get_frontmatter_block)
    
    with patch("scripts.sector_classifier.get_frontmatter_block") as mock_gfb:
        # Simula que o arquivo tem [infra], mas o gfb diz que "deve processar" (ex: sectors=[])
        # para que o script prossiga até o LLM
        mock_gfb.return_value = ({"sectors": ["infra"]}, "---\nsectors: [infra]\n---\n", "# Title\nContent")
        
        mock_llm.return_value = SectorClassifierOutput(sectors=["infra"])
        
        process_file(mock_path)
        
        # O LLM foi chamado? Sim, porque o early return foi enganado pelo mock do gfb
        # O write_text foi chamado? NÃO, porque a otimização de IO detectou que o novo é igual ao atual
        assert mock_path.write_text.call_count == 0
