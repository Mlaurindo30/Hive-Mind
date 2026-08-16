"""Testes do typed decay (OmniRoute TV6, 2026-08-12) e anti-loop de feedback."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.knowledge.intake import (
    MemoryReadEcho,
    StructuralIntakeError,
    normalize_observation,
)
from core.knowledge.typed_decay import (
    DURABLE_TYPES,
    EPHEMERAL_TYPES,
    access_immunity_threshold,
    is_access_immune,
    is_durable_type,
    is_ephemeral_type,
    should_apply_staleness,
)


class TypedDecayTests(unittest.TestCase):
    def test_durable_types_are_immune_by_type(self):
        for t in ("fact", "decision", "learning", "preference", "rationale",
                  "code_symbol", "document_chunk"):
            self.assertTrue(is_durable_type(t), f"{t} deveria ser durável")
            self.assertFalse(should_apply_staleness(knowledge_type=t))

    def test_ephemeral_types_decay(self):
        for t in ("operational_fact", "project_status", "visual_observation",
                  "next_step", "summary", "observation"):
            self.assertTrue(is_ephemeral_type(t), f"{t} deveria ser efêmero")
            self.assertTrue(should_apply_staleness(knowledge_type=t, access_count=0))

    def test_unknown_type_is_conservative_ephemeral(self):
        # Tipo não classificado decai por padrão (não persiste indefinidamente).
        self.assertFalse(is_durable_type("tipo_desconhecido"))
        self.assertFalse(is_ephemeral_type("tipo_desconhecido"))
        self.assertTrue(should_apply_staleness(knowledge_type="tipo_desconhecido", access_count=0))

    def test_access_immunity_protects_ephemeral(self):
        # Ephemeral com access_count >= threshold fica imune.
        with mock.patch.dict(os.environ, {"HIVE_STALENESS_ACCESS_IMMUNITY": "3"}):
            self.assertTrue(is_access_immune(3))
            self.assertTrue(is_access_immune(5))
            self.assertFalse(is_access_immune(2))
            self.assertFalse(should_apply_staleness(
                knowledge_type="operational_fact", access_count=3,
            ))

    def test_access_immunity_disabled_at_zero(self):
        with mock.patch.dict(os.environ, {"HIVE_STALENESS_ACCESS_IMMUNITY": "0"}):
            self.assertFalse(is_access_immune(100))
            # Sem imunidade por acesso, ephemeral decai.
            self.assertTrue(should_apply_staleness(
                knowledge_type="operational_fact", access_count=100,
            ))

    def test_durable_never_decays_even_without_access(self):
        self.assertFalse(should_apply_staleness(knowledge_type="fact", access_count=0))
        self.assertFalse(should_apply_staleness(knowledge_type="decision", access_count=None))

    def test_default_threshold_is_three(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HIVE_STALENESS_ACCESS_IMMUNITY", None)
            self.assertEqual(access_immunity_threshold(), 3)


class AntiLoopFeedbackTests(unittest.TestCase):
    """Anti-loop de feedback (Lya Core5): eco de leitura não vira neurônio."""

    def test_memory_read_source_type_is_echo(self):
        row = {
            "id": "obs-echo",
            "type": "sinapse_query",
            "title": "sinapse_query result",
            "content": json_dump({"facts": ["the background process ID is 90772"]}),
            "metadata": "{}",
            "project": "Hive-Mind",
            "workspace_id": "default",
            "created_at": "2026-08-12T00:00:00+00:00",
        }
        with self.assertRaises(MemoryReadEcho):
            normalize_observation(row)

    def test_metadata_origin_retrieval_is_echo(self):
        row = {
            "id": "obs-echo2",
            "type": "discovery",
            "title": "algum título",
            "content": json_dump({"facts": ["conteudo qualquer"]}),
            "metadata": json_dump({"origin": "memory_read"}),
            "project": "Hive-Mind",
            "workspace_id": "default",
            "created_at": "2026-08-12T00:00:00+00:00",
        }
        with self.assertRaises(MemoryReadEcho):
            normalize_observation(row)

    def test_normal_discovery_is_not_echo(self):
        row = {
            "id": "obs-normal",
            "type": "discovery",
            "title": "descoberta real",
            "content": json_dump({"facts": ["um fato novo do agente"]}),
            "metadata": "{}",
            "project": "Hive-Mind",
            "workspace_id": "default",
            "created_at": "2026-08-12T00:00:00+00:00",
        }
        candidates = normalize_observation(row)
        self.assertTrue(len(candidates) >= 1)

    def test_memory_read_echo_is_not_structural_error(self):
        # MemoryReadEcho é distinta de StructuralIntakeError: a primeira é skip,
        # a segunda é quarentena. Subclasses diferentes garantem tratamento
        # distinto no promote_pending_observations.
        self.assertTrue(issubclass(MemoryReadEcho, ValueError))
        self.assertTrue(issubclass(StructuralIntakeError, ValueError))
        self.assertNotEqual(MemoryReadEcho, StructuralIntakeError)


class SecurityTypeMappingTests(unittest.TestCase):
    """Tipos de segurança do claude-mem v13.15.0 agora são canônicos (P1-3)."""

    def _row(self, obs_type: str):
        return {
            "id": f"obs-{obs_type}",
            "type": obs_type,
            "title": f"título {obs_type}",
            "content": json_dump({"facts": ["conteúdo de teste"]}),
            "metadata": "{}",
            "project": "Hive-Mind",
            "workspace_id": "default",
            "created_at": "2026-08-12T00:00:00+00:00",
        }

    def test_sensitive_maps_to_sensitive(self):
        from core.knowledge.intake import CANONICAL_TYPES
        self.assertIn("sensitive", CANONICAL_TYPES)
        self.assertIn("security_alert", CANONICAL_TYPES)
        self.assertIn("security_note", CANONICAL_TYPES)

    def test_security_types_promote_without_quarantine(self):
        for t in ("security_alert", "security_note", "sensitive"):
            candidates = normalize_observation(self._row(t))
            self.assertTrue(len(candidates) >= 1, f"{t} deveria gerar candidato")
            self.assertEqual(candidates[0].knowledge_type, t)


def json_dump(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
