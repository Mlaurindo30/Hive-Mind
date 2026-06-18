import pytest
from pathlib import Path
from scripts.alias_miner import get_frontmatter_block, extract_neuron_info

def test_get_frontmatter_block_success():
    content = "---\ntype: fact\naliases: []\n---\n# Title\nContent"
    data, fm_block, body = get_frontmatter_block(content)
    assert data["type"] == "fact"
    assert data["aliases"] == []
    assert fm_block == "---\ntype: fact\naliases: []\n---\n"
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
