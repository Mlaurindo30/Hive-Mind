"""F4.1 — Testes do helper with_sqlite_retry (K8 harden)."""
import sqlite3
import unittest

from core.database import with_sqlite_retry


class WithSqliteRetryTests(unittest.TestCase):
    def test_passes_through_on_success(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return "ok"

        self.assertEqual(with_sqlite_retry(fn, op_label="t"), "ok")
        self.assertEqual(calls["n"], 1)

    def test_retries_on_lock_and_succeeds(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return 42

        result = with_sqlite_retry(
            fn,
            retries=5,
            initial_delay=0.001,
            max_delay=0.01,
            op_label="t",
        )
        self.assertEqual(result, 42)
        self.assertEqual(attempts["n"], 3)

    def test_raises_other_operational_errors_immediately(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise sqlite3.OperationalError("no such column: bogus")

        with self.assertRaises(sqlite3.OperationalError) as ctx:
            with_sqlite_retry(fn, op_label="t")
        self.assertIn("no such column", str(ctx.exception))
        self.assertEqual(calls["n"], 1, "should not retry on non-lock errors")

    def test_gives_up_after_max_retries(self):
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError) as ctx:
            with_sqlite_retry(
                fn,
                retries=3,
                initial_delay=0.001,
                max_delay=0.01,
                op_label="backfill",
            )
        self.assertEqual(calls["n"], 3)
        # The final error message is enriched with the op label
        self.assertIn("backfill", str(ctx.exception))
        self.assertIn("3 tentativas", str(ctx.exception))

    def test_matches_busy_keyword_too(self):
        # "database is busy" appears in some builds/situations; should also retry
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise sqlite3.OperationalError("database is busy")
            return "done"

        self.assertEqual(
            with_sqlite_retry(fn, retries=3, initial_delay=0.001, max_delay=0.01, op_label="t"),
            "done",
        )
        self.assertEqual(attempts["n"], 2)


if __name__ == "__main__":
    unittest.main()
