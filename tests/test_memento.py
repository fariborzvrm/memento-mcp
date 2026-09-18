"""Tests for memento_server. Tools are called directly (no MCP harness);
each tool test runs with cwd in tmp_path so find_memory_dir() resolves there."""

import pytest

import memento_server as ms

SAMPLE = """\
Project memory intro.

<!-- id: dec-001 -->
## Use Postgres for persistence

**Status:** active
**Tags:** db, arch

We chose Postgres over SQLite because the eval workload needs
concurrent writers and JSONB for schema hints.

<!-- id: task-001 -->
## Add eval harness

**Status:** open

TODO: build the eval runner.
"""


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path / "docs" / "memory"


# ─── parser/renderer ───────────────────────────────


def test_parse_empty_file():
    assert ms.split_entries("") == []
    assert ms.split_entries("\n \n") == []


def test_parse_single_entry():
    entries = ms.split_entries("<!-- id: dec-001 -->\n## Title here\n\nBody line.\n")
    assert [e["id"] for e in entries] == ["dec-001"]
    e = ms.parse_entry("dec-001", entries[0]["block"])
    assert e["title"] == "Title here"
    assert e["body"] == "Body line."


def test_parse_multiple_entries():
    entries = ms.split_entries(SAMPLE)
    assert [e["id"] for e in entries] == [None, "dec-001", "task-001"]
    dec = ms.parse_entry("dec-001", entries[1]["block"])
    assert "concurrent writers" in dec["body"]
    task = ms.parse_entry("task-001", entries[2]["block"])
    assert task["title"] == "Add eval harness"


def test_parse_preserves_preamble():
    pre = ms.split_entries(SAMPLE)[0]
    assert pre["id"] is None
    assert pre["block"].strip() == "Project memory intro."


def test_parse_status_and_tags():
    dec = ms.parse_entry("dec-001", ms.split_entries(SAMPLE)[1]["block"])
    assert dec["status"] == "active"
    assert dec["tags"] == ["db", "arch"]


def test_parse_missing_metadata_defaults():
    task = ms.parse_entry("task-001", ms.split_entries(SAMPLE)[2]["block"])
    assert task["tags"] == []
    e = ms.parse_entry("x-001", "<!-- id: x-001 -->\n## T\n\njust body\n")
    assert e["status"] is None
    assert e["tags"] == []
    assert e["body"] == "just body"


def test_render_roundtrip():
    for ent in ms.split_entries(SAMPLE):
        if ent["id"] is None:
            continue
        e = ms.parse_entry(ent["id"], ent["block"])
        assert ms.parse_entry(e["id"], ms.render_entry(e)) == e


# ─── file ops / write / update ─────────────────────


def test_write_creates_file(mem):
    assert ms.write("decision", "Use Postgres", "because JSONB", tags=["db"]) == (
        "created dec-001 in DECISIONS.md"
    )
    text = ms.read_file(mem, "DECISIONS.md")
    assert "<!-- id: dec-001 -->" in text
    assert "**Status:** active" in text
    for name in ms.SEED_FILES:
        assert (mem / name).exists()


def test_write_appends_entry(mem):
    ms.write("decision", "First", "a")
    ms.write("decision", "Second", "b")
    text = ms.read_file(mem, "DECISIONS.md")
    assert text.index("First") < text.index("Second")


def test_write_allocates_sequential_ids(mem):
    assert ms.write("decision", "A", "a").startswith("created dec-001")
    assert ms.write("decision", "B", "b").startswith("created dec-002")
    assert ms.write("task", "T", "t").startswith("created task-001")


def test_update_changes_status(mem):
    ms.write("decision", "Use Postgres", "why")
    assert ms.update("dec-001", status="done") == "updated dec-001 in DECISIONS.md"
    text = ms.read_file(mem, "DECISIONS.md")
    assert "**Status:** done" in text
    assert "## Use Postgres" in text


def test_update_preserves_other_entries(mem):
    ms.write("decision", "First", "first body")
    ms.write("decision", "Second", "second body")
    before = ms.read_file(mem, "DECISIONS.md")
    first_block = ms.split_entries(before)[0]["block"]
    ms.update("dec-002", status="done")
    after = ms.read_file(mem, "DECISIONS.md")
    assert first_block in after
    assert "**Status:** done" in after


# ─── tools ─────────────────────────────────────────


def test_search_finds_title_and_body(mem):
    ms.write("decision", "Use Postgres", "JSONB for schema hints")
    ms.write("decision", "Keep it simple", "nothing fancy")
    assert "dec-001" in ms.search("Postgres")
    assert "dec-001" in ms.search("JSONB")
    assert "dec-002" not in ms.search("JSONB")


def test_search_is_case_insensitive(mem):
    ms.write("decision", "Use Postgres", "JSONB for schema hints")
    assert "dec-001" in ms.search("postgres")
    assert "dec-001" in ms.search("jsonb")


def test_log_uses_first_line_as_title(mem):
    result = ms.log("Fixed the parser\nSecond line of notes")
    assert result.startswith("created log-001")
    text = ms.read_file(mem, "SESSION_LOG.md")
    entry = ms.parse_entry("log-001", ms.split_entries(text)[-1]["block"])
    assert entry["title"] == "Fixed the parser"
    assert entry["status"] is None
    assert entry["body"] == "Second line of notes"


# ─── init ──────────────────────────────────────────


def test_init_creates_files(tmp_path):
    ms.init_project(tmp_path)
    assert (tmp_path / ".memento.toml").read_text(encoding="utf-8") == (
        'memory_dir = "docs/memory"\n'
    )
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ms.SNIPPET_HEADING in agents


def test_init_is_idempotent(tmp_path):
    ms.init_project(tmp_path)
    cfg_before = (tmp_path / ".memento.toml").read_text(encoding="utf-8")
    agents_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    ms.init_project(tmp_path)
    assert (tmp_path / ".memento.toml").read_text(encoding="utf-8") == cfg_before
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_init_appends_to_existing_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# My project\n\nBe nice.\n", encoding="utf-8")
    ms.init_project(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# My project")
    assert ms.SNIPPET_HEADING in text
