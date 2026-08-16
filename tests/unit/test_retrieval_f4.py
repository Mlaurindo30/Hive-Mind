"""Testes do F4 (retrieval): chunking header, citação com span, hybrid search."""
import unittest

from core.retrieval.router import (
    CHUNK_CHAR_THRESHOLD,
    _chunk_neuron_content,
    _citation_from_context,
)


class ChunkNeuronContentTests(unittest.TestCase):
    def test_short_content_not_chunked(self):
        self.assertIsNone(_chunk_neuron_content("conteúdo curto"))

    def test_long_content_chunks_first_substantive_section(self):
        content = (
            "# Título\n\n"
            "Introdução curta.\n\n"
            "## O Mecanismo\n"
            "O recall melhora quando a recuperação é difícil.\n\n"
            "## Sinapses\n"
            "- projeto:: [[x]]\n"
        )
        heading, start, end, chunk = _chunk_neuron_content(content)
        self.assertEqual(heading, "O Mecanismo")
        self.assertIn("recall melhora", chunk)
        self.assertNotIn("Sinapses", chunk)

    def test_skips_metadata_sections(self):
        content = (
            "# Título\n\n"
            "## Sinapses\n- x\n\n"
            "## Related\n- y\n\n"
            "## O Fato\n"
            "conteúdo substantivo real.\n"
        )
        heading, start, end, chunk = _chunk_neuron_content(content)
        self.assertEqual(heading, "O Fato")
        self.assertIn("substantivo real", chunk)


class CitationSpanTests(unittest.TestCase):
    def test_citation_reads_span_fields(self):
        item = {
            "id": "n1",
            "title": "t",
            "source_uri": "uri",
            "offset_start": 10,
            "offset_end": 50,
            "parent_id": "n1",
            "parent_type": "neuron",
        }
        c = _citation_from_context(item)
        self.assertEqual(c["offset_start"], 10)
        self.assertEqual(c["offset_end"], 50)
        self.assertEqual(c["parent_id"], "n1")
        self.assertEqual(c["parent_type"], "neuron")


if __name__ == "__main__":
    unittest.main()
