# Memento v1 — Plan

**Hand to the coding agent. Build only what's listed. ~1 day of work.**

---

## 0. What v1 Is

One Python file. An MCP server that gives a coding agent typed tools to read/write a project's markdown memory folder.

Works with **OpenCode**, **Claude Code**, and **Codex CLI** — all three speak MCP over stdio, so one server covers all of them.

No daemon. No SQLite. No web UI. No git integration. Just files on disk + a small server.

---

## 1. Deliverables

```
memento/
├── memento_server.py       # the whole server (~370 lines) + `init` subcommand
├── .memento.toml.example   # config template
├── tests/test_memento.py   # 18 tests
├── README.md               # uv-first setup for all 3 CLIs
├── AGENTS.md               # snippet to paste into user's AGENTS.md
├── LICENSE                 # MIT
├── .gitignore
└── pyproject.toml          # just the `mcp>=2` dependency
```

That's the entire project. No package structure, no `src/`, no console scripts.
Distributed as a single self-contained file in a public GitHub repo
(`memento-mcp`); users run it via `uv run <raw URL>` — see §5.

---

## 2. Per-Project Layout

User adds these to their existing project:

```
<project>/
├── .memento.toml           # 1 line: memory_dir
├── AGENTS.md               # user pastes the Memento snippet here
└── docs/memory/            # their existing memory folder
    ├── DECISIONS.md
    ├── TASKS.md
    ├── CONTRACTS.md
    └── SESSION_LOG.md
```

`.memento.toml`:

```toml
memory_dir = "docs/memory"
```

Resolution happens **per tool call**, never cached at startup:

1. `MEMENTO_ROOT` env var, if set (absolute or relative to cwd).
2. Walk up from cwd looking for `.memento.toml`, use its `memory_dir`.
3. Fall back to `docs/memory` under cwd.

A broken `.memento.toml` is returned to the agent as a clear error — never a
silent fallback that writes memory to the wrong place. Tools create the memory
dir on demand. (`slug` was dropped: nothing in v1 reads it. Add it back when
v2 cross-project search exists.)

---

## 3. Entry Format

Markdown sections with an ID comment:

```markdown
<!-- id: dec-001 -->
## Use Postgres for persistence

**Status:** active
**Tags:** db, arch

We chose Postgres over SQLite because the eval workload needs
concurrent writers and JSONB for schema hints.
```

Rules:

- `<!-- id: xxx -->` marks the start of an entry.
- Entry extends to the next ID marker or EOF.
- First `#` or `##` line is the title.
- Optional `**Status:**` and `**Tags:**` lines are metadata.
- Everything else is body.
- Content before the first ID marker is preserved (frontmatter, intros).

---

## 4. The Server

Single file: `memento_server.py`. Python 3.11+ (for `tomllib`). One dependency: `mcp>=2` (installed 2.2.0 — the old FastMCP import was renamed; use `from mcp.server.mcpserver import MCPServer`; `mcp.add_tool(fn)` + `mcp.run()` are unchanged).

**Structure:**

```python
# ─── config ────────────────────────────────────────
def find_memory_dir() -> Path  # per call: MEMENTO_ROOT -> walk up -> cwd/docs/memory

# ─── parsing ───────────────────────────────────────
def split_entries(text: str) -> list[dict]
def parse_entry(eid: str, block: str) -> dict
def render_entry(e: dict) -> str

# ─── file ops ──────────────────────────────────────
def read_file(mem: Path, name: str) -> str
def write_file(mem: Path, name: str, text: str) -> None
def next_id(mem: Path, prefix: str) -> str

# ─── MCP tools (plain functions, registered at the bottom) ───
def read_all() -> str
def search(query: str, file: str | None = None) -> str
def write(type: str, title: str, body: str, tags: list[str] | None = None) -> str
def update(entry_id: str, status: str | None = None, title: str | None = None,
           body: str | None = None, tags: list[str] | None = None) -> str
def log(body: str, tags: list[str] | None = None) -> str

for fn in (read_all, search, write, update, log):
    mcp.add_tool(fn)

if __name__ == "__main__":
    mcp.run()      # stdio transport
```

**Type → file mapping** (used by `write`):

| type | file | id prefix |
|---|---|---|
| decision | DECISIONS.md | dec |
| contract | CONTRACTS.md | con |
| task | TASKS.md | task |
| log | SESSION_LOG.md | log |
| evaluation | EVALUATION.md | ev |

Unknown types → `{TYPE}S.md` with a 3-letter prefix.

**Key behaviors:**

- `read_all` returns every `.md` in `memory_dir` concatenated, each prefixed with `<!-- file: NAME -->` so the agent knows the source file.
- `search` does case-insensitive substring match on title + body (+ tags/status). Optional `file` to scope. Returns full entry blocks with id + file, ready to feed `update`.
- `write` allocates the next ID for that type, appends to the right file. New entries get `Status: active` (logs have no status).
- `update` scans all files for the ID, patches in place, preserves everything else in the file byte-for-byte.
- `log` is `write(type="log", title=first_line, body=rest)` — the title line is not repeated in the body.
- `write`/`log` create `memory_dir` on demand and seed the five files (incl. `EVALUATION.md`).
- Config/name errors return a clear `error: ...` string to the agent — never a traceback, never a silent wrong-dir fallback.

**Deliberately omitted:**

- No locking (assumes single agent per project).
- No index (linear scan; fine under ~2000 entries).
- No git commands (user commits their own repo).
- No cross-project anything.

---

## 5. CLI Compatibility

The MCP server itself is identical for all three CLIs — same stdio transport, same tools. Only the *registration* differs.

**Install model:** `memento_server.py` carries PEP 723 inline metadata
(`dependencies = ["mcp>=2"]`), so `uv run <url>` downloads it, builds an
ephemeral cached env, and runs it — no pip, no venv, no clone, no local path.
URLs are pinned to the `v1.0.0` tag; `main` tracks the latest. Fallback:
`pip install mcp` + `python memento_server.py` (or a local copy under
`uv run /path/to/memento_server.py`).

### OpenCode

Add to `opencode.json` (project) or `~/.config/opencode/opencode.json` (global):

```jsonc
{
  "mcp": {
    "memento": {
      "type": "local",
      "command": ["uv", "run", "https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py"],
      "enabled": true
    }
  }
}
```

### Claude Code

```bash
claude mcp add memento -- uv run https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py
```

Or manually in `~/.claude.json`:

```jsonc
{
  "mcpServers": {
    "memento": {
      "command": "uv",
      "args": ["run", "https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py"]
    }
  }
}
```

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.memento]
command = "uv"
args = ["run", "https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py"]
```

Or per-project in `.codex/config.toml`.

### Per-project setup

`memento_server.py init` (from inside the project) creates `.memento.toml`
and writes the AGENTS.md snippet — both idempotent. So: `uv run <url> init`.

### Verification for each

After registering, run in the CLI:

- "List your available MCP tools." → should show 5 memento tools.
- "Use memento to write a test decision." → should create `DECISIONS.md` in the project's memory folder.

**No server-side changes needed for any of them.** Same script, three config snippets.

---

## 6. AGENTS.md Snippet

The user pastes this into their project's `AGENTS.md`. All three CLIs read `AGENTS.md` (OpenCode and Codex natively; Claude Code via its own file — see below).

```markdown
## Memory Protocol (Memento)

You have a Memento MCP server for project memory.

- **Session start:** call `read_all` to load memory.
- **Before asking a question:** call `search` first.
- **Architectural choice:** `write` with type=decision. Include the why.
- **New invariant:** `write` with type=contract.
- **Task finished:** `update` its status to `done`.
- **End of session:** `log` a 3–5 line summary.
- **Never edit `docs/memory/*.md` by hand.** Use the tools.
```

**File name per CLI:**

| CLI | Reads which file |
|---|---|
| OpenCode | `AGENTS.md` |
| Codex CLI | `AGENTS.md` |
| Claude Code | `CLAUDE.md` (or `.claude/CLAUDE.md`) |

For Claude Code, recommended: add one pointer line to `CLAUDE.md`:

```markdown
See AGENTS.md for the memory protocol.
```

(Symlinking `ln -s AGENTS.md CLAUDE.md` also works but needs Developer Mode on
Windows; duplicating the snippet into both files works but can drift.)

The README should document this.

---

## 7. Tests

`tests/test_memento.py` — pytest, `tmp_path` fixtures, no mocks.

**Parser/renderer:**

1. `test_parse_empty_file`
2. `test_parse_single_entry`
3. `test_parse_multiple_entries`
4. `test_parse_preserves_preamble`
5. `test_parse_status_and_tags`
6. `test_parse_missing_metadata_defaults`
7. `test_render_roundtrip` — parse → render → parse == same

**File ops:**

8. `test_write_creates_file`
9. `test_write_appends_entry`
10. `test_write_allocates_sequential_ids`
11. `test_update_changes_status`
12. `test_update_preserves_other_entries`

**Tools (call the underlying functions directly, no MCP harness):**

13. `test_search_finds_title_and_body`
14. `test_search_is_case_insensitive`
15. `test_log_uses_first_line_as_title`

**Init:**

16. `test_init_creates_files`
17. `test_init_is_idempotent`
18. `test_init_appends_to_existing_agents_md`

All tests import from `memento_server` directly. The five tools are plain
functions registered via `mcp.add_tool` at the bottom of the file, so tests
call them with no MCP involvement (the tool wrapper only converts
`MementoError` to an `error: ...` string).

---

## 8. Build Order

1. Write `memento_server.py` with config + parser + renderer.
2. Write parser tests. Confirm round-trip.
3. Add file ops (`read_file`, `write_file`, `upsert`, `next_id`) + tests.
4. Add the 5 MCP tools as thin wrappers.
5. Manual smoke: run `python memento_server.py`, register in each CLI, call `write`, verify file.
6. Write `README.md` with the three setup sections + AGENTS.md snippet.
7. Write `AGENTS.md` snippet file.

Estimate: **1 day**.

---

## 9. Acceptance Criteria

- [ ] `memento_server.py` runs with `python memento_server.py` and speaks MCP stdio.
- [ ] `uv run memento_server.py` works (PEP 723 env auto-built) — and `uv run memento_server.py init` scaffolds `.memento.toml` + AGENTS.md snippet in a scratch dir.
- [ ] All 18 tests pass: `pytest -q`.
- [ ] Registered successfully in **OpenCode** — `write` tool creates `DECISIONS.md`.
- [ ] Registered successfully in **Claude Code** — same test.
- [ ] Registered successfully in **Codex CLI** — same test.
- [ ] (After GitHub push) `uv run https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py` works end-to-end; README placeholders replaced with the real username.
- [ ] `README.md` documents all three setups in under 2 pages.
- [ ] `AGENTS.md` snippet works verbatim in OpenCode and Codex; Claude Code section explains the `CLAUDE.md` pointer line.
- [ ] Dependencies: `mcp` and Python 3.11+ stdlib only (uv handles the env).
- [ ] Repo has LICENSE (MIT), .gitignore, git history, tag `v1.0.0`.

**Do not add anything else.** No daemon, no DB, no web UI, no git integration.

---

## 10. README Outline (for the agent)

```markdown
# Memento

Give your coding agent persistent memory.

## What it does
(2 paragraphs — plain language)

## Install
1. Install uv (once per machine): winget / curl one-liners
2. Register in your CLI — no download:
   uv run https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py
   (OpenCode / Claude Code / Codex CLI snippets + verification step)
3. Per project: uv run <url> init  (writes .memento.toml + AGENTS.md snippet)
   (Claude Code only: pointer line in CLAUDE.md)
### How the memory folder is found
(MEMENTO_ROOT -> .memento.toml walk-up -> docs/memory, per tool call)

### Offline / pip fallback
(local copy via uv run /path, or pip install mcp + python memento_server.py)

## Tools
- `read_all` — ...
- `search` — ...
- `write` — ...
- `update` — ...
- `log` — ...

## Entry format
(markdown block example)

## Limitations
- No locking (one agent per project)
- Linear search
- Whole-file rewrite on write
```

---

## 11. What v2 Could Add (do not build now)

- SQLite + FTS5 index for search
- Auto-commit per write
- Cross-project search
- Compaction for old entries
- A `stats` tool

Only after v1 has been used for a week and something hurts.

---

**End of plan. Start with `memento_server.py` and its parser.**