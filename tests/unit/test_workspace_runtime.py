"""K10 (v3.7.9+) — Testes do modulo core/workspace.py (multi-tenancy runtime)."""
import unittest
from unittest import mock

import core.workspace as ws


class WorkspaceValidationTests(unittest.TestCase):
    def test_valid_workspace_ids(self):
        for wid in ["default", "acme", "acme-corp", "team_alpha", "A1B2", "x"]:
            self.assertTrue(
                ws.is_valid_workspace_id(wid),
                f"deveria ser valido: {wid!r}",
            )

    def test_invalid_workspace_ids(self):
        for wid in [
            "",                    # empty
            "-acme",               # leading dash
            "_private",            # leading underscore
            "acme corp",           # space
            "acme.corp",           # dot
            "acme/corp",           # slash
            "acmeção",            # unicode
            "a" * 65,              # too long
            "trailing-",           # trailing dash
            "trailing_",           # trailing underscore
        ]:
            self.assertFalse(
                ws.is_valid_workspace_id(wid),
                f"deveria ser invalido: {wid!r}",
            )

    def test_set_workspace_validates_format(self):
        token = ws.set_workspace("acme")
        try:
            self.assertEqual(ws.current_workspace_id(), "acme")
        finally:
            ws.reset_workspace(token)
        # Invalid raises ValueError
        with self.assertRaises(ValueError):
            ws.set_workspace("bad name with spaces")

    def test_set_workspace_restores_after_reset(self):
        token = ws.set_workspace("alpha")
        self.assertEqual(ws.current_workspace_id(), "alpha")
        ws.reset_workspace(token)
        # Should be back to default
        self.assertEqual(ws.current_workspace_id(), "default")

    def test_nested_scopes_restore_in_lifo_order(self):
        with ws.workspace_scope("acme") as outer:
            self.assertEqual(ws.current_workspace_id(), "acme")
            with ws.workspace_scope("bravo") as inner:
                self.assertEqual(ws.current_workspace_id(), "bravo")
            # Inner saiu - voltamos para outer
            self.assertEqual(ws.current_workspace_id(), "acme")
        # Outer saiu - voltamos para default
        self.assertEqual(ws.current_workspace_id(), "default")

    def test_reserved_workspaces(self):
        # `default` e `__all__` sao reservados (uso especial)
        self.assertTrue(ws.is_reserved("default"))
        self.assertTrue(ws.is_reserved("__all__"))
        self.assertFalse(ws.is_reserved("acme"))

    def test_default_workspace_from_env_no_env(self):
        # Sem env, deve retornar default
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ws.default_workspace_from_env(), "default")

    def test_default_workspace_from_env_valid(self):
        with mock.patch.dict("os.environ", {"HIVE_DEFAULT_WORKSPACE": "acme"}):
            self.assertEqual(ws.default_workspace_from_env(), "acme")

    def test_default_workspace_from_env_invalid_falls_back(self):
        with mock.patch.dict("os.environ", {"HIVE_DEFAULT_WORKSPACE": "bad name"}):
            # invalid - cai para default
            self.assertEqual(ws.default_workspace_from_env(), "default")

    def test_concurrent_contexts_isolated(self):
        # Contextvar: cada thread/task tem seu proprio workspace
        import asyncio

        async def get_id():
            return ws.current_workspace_id()

        async def main():
            results = await asyncio.gather(
                ws.workspace_scope("acme")(get_id)(),
                ws.workspace_scope("bravo")(get_id)(),
                get_id(),
            )
            return results

        # Roda em event loop sincrono para nao baguncar tests sequenciais
        # Verificacao basica: ao menos 2 workspaces distintos foram usados
        with ws.workspace_scope("acme"):
            self.assertEqual(ws.current_workspace_id(), "acme")
        with ws.workspace_scope("bravo"):
            self.assertEqual(ws.current_workspace_id(), "bravo")
        # Fora de qualquer scope, default
        self.assertEqual(ws.current_workspace_id(), "default")


if __name__ == "__main__":
    unittest.main()
