"""Alembic migration chain smoke tests (no live Apify)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_revision_chain_reaches_expected_head() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)

    heads = script.get_heads()
    assert heads == ["20260326_0003"]

    revisions = list(script.walk_revisions())
    revision_ids = [rev.revision for rev in revisions]
    assert "20260326_0001" in revision_ids
    assert "20260326_0002" in revision_ids
    assert "20260326_0003" in revision_ids

    # Ensure linear ancestry: each down_revision points to the previous migration.
    by_id = {rev.revision: rev for rev in revisions}
    current = by_id["20260326_0003"]
    assert current.down_revision == "20260326_0002"
    assert by_id["20260326_0002"].down_revision == "20260326_0001"
    assert by_id["20260326_0001"].down_revision is None
