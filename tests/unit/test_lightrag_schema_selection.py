from core.lightrag_index import lightrag_system_prompt, should_use_extraction_schema


def test_keyword_prompt_is_not_routed_to_entity_extraction_schema():
    prompt = """
    You are an expert keyword extractor. Extract high_level_keywords and
    low_level_keywords for a RAG query about an entity relation.
    """

    assert should_use_extraction_schema(prompt) is False


def test_entity_relationship_prompt_uses_extraction_schema():
    prompt = """
    Extract entities and relationships from the input text. Return a JSON
    object with entities and relationships arrays.
    """

    assert should_use_extraction_schema(prompt) is True


def test_query_prompt_uses_answering_system_prompt():
    prompt = "Using the indexed graph, state the exact two-hop path from Asteria to Cirios."

    assert "answer" in lightrag_system_prompt(prompt).lower()
    assert "extracting entities" not in lightrag_system_prompt(prompt).lower()


def test_lightrag_supplied_system_prompt_is_preserved_for_query_context():
    supplied_context = "---Data---\nAsteria administers Boreal."

    assert lightrag_system_prompt("What connects Asteria to Boreal?", supplied_context) == supplied_context
