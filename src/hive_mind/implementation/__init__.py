"""Validation of the living implementation documents (D001-R2).

The living docs drift: a HEAD is updated in one place and not another, a
counter is typed by hand and stops matching its own table, an aggregate line
survives after the detail it summarised was corrected. This package makes
that drift a test failure instead of something a reader has to notice.
"""

from hive_mind.implementation.validate import Finding, validate_documents

__all__ = ["Finding", "validate_documents"]
