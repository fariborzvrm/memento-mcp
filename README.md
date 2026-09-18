# Memento

Give your coding agent persistent memory.

Memento is a tiny MCP server that turns a plain folder of markdown files into
typed memory for AI coding agents: decisions, contracts (invariants), tasks,
evaluations and session logs. Your agent can search it, extend it, and update
entries by id — while the memory stays as plain, greppable, committable
markdown in your repo. Works with **OpenCode**, **Claude Code** and
**Codex CLI** — all three speak MCP over stdio, so one server covers all of
them.

## What it does

- On session start the agent loads memory with `read_all`.
- During work it records choices (`write`), checks what's known (`search`),
  and updates entries (`update`).
- At session end it leaves a summary (`log`).

No daemon, no database, no web UI. One self-contained script — no install step.

## Install

### 1. Install uv (once per machine)

[uv](https://docs.astral.sh/uv/) downloads and runs the server with its one
dependency (`mcp`) in an isolated, cached environment — no pip, no venv, no
clone. Windows:

```powershell
winget install --id=astral-sh.uv -e
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Register the server in your CLI (no download needed)

Point your CLI at the script URL, pinned to the `v1.0.0` tag so it never
changes under you. (Use `main` instead of `v1.0.0` if you want to track the
latest. Replace `<you>` with your GitHub username.)

#### OpenCode

Add to `opencode.json` (project) or `~/.config/opencode/opencode.json` (global):

```jsonc
{
  "mcp": {
    "memento": {
      "type": "local",
      "command": [
        "uv", "run",
        "https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py"
      ],
      "enabled": true
    }
  }
}
```

#### Claude Code

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

#### Codex CLI

Add to `~/.codex/config.toml` (or per-project `.codex/config.toml`):

```toml
[mcp_servers.memento]
command = "uv"
args = ["run", "https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py"]
```

#### Verify

Ask the agent: *"List your available MCP tools."* — you should see 5 memento
tools.

### 3. Add to a project

Run in the project root:

```bash
uv run https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py init
```

This creates `.memento.toml` (`memory_dir = "docs/memory"`) and writes the
memory protocol into `AGENTS.md` (both skipped if already present).

Claude Code only — add one pointer line to `CLAUDE.md`:

```markdown
See AGENTS.md for the memory protocol.
```

(A symlink also works but needs Developer Mode on Windows; duplicating the
snippet works but can drift.)

### How the memory folder is found

Resolved **per tool call**: the `MEMENTO_ROOT` env var if set → the nearest
`.memento.toml` walking up from the working directory → `docs/memory` under
the working directory. The folder and its five seed files are created on
first write.

### Offline / pip fallback

Prefer a local copy, or can't use uv?

```bash
# local copy, still no venv juggling
curl -o memento_server.py https://raw.githubusercontent.com/<you>/memento-mcp/v1.0.0/memento_server.py
# point your CLI at: ["uv", "run", "/path/to/memento_server.py"]

# or plain Python (3.11+)
pip install mcp
python memento_server.py
```

## Tools

- `read_all()` — every markdown file in the memory folder, concatenated, each
  prefixed with a `<!-- file: NAME -->` marker.
- `search(query, file=None)` — case-insensitive substring match over entry
  titles, bodies, tags and status. Returns full entry blocks with id + file.
- `write(type, title, body, tags=None)` — append a new entry with a fresh
  sequential id. `type`: `decision`, `contract`, `task`, `log`, `evaluation`
  (unknown types get their own `{TYPE}S.md`).
- `update(entry_id, status=None, title=None, body=None, tags=None)` — patch an
  entry in place; only the fields you pass change.
- `log(body, tags=None)` — append a session log entry; the first line of
  `body` becomes the title.

## Entry format

Entries are markdown sections with an id comment; anything before the first
marker (frontmatter, intros) is preserved:

```markdown
<!-- id: dec-001 -->
## Use Postgres for persistence

**Status:** active
**Tags:** db, arch

We chose Postgres over SQLite because the eval workload needs
concurrent writers and JSONB for schema hints.
```

## Limitations

- No locking — assume one agent per project.
- Linear search — fine under ~2000 entries.
- Whole-file rewrite on write.
- A broken `.memento.toml` is reported as an error, not silently ignored.

## License

MIT — see [LICENSE](LICENSE).
