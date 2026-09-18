# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=2",
# ]
# ///
"""Memento — an MCP server that gives coding agents typed tools over a
project's markdown memory folder. Run with `python memento_server.py`
(speaks MCP over stdio). Memory lives in plain markdown files the agent
reads and writes through the five tools below; config is a one-line
`.memento.toml` (`memory_dir = "docs/memory"`) resolved per tool call.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    "memento",
    instructions="Persistent project memory as markdown. read_all at session start, "
    "search before asking, write decisions/contracts/tasks, log at session end.",
)

# ─── config ────────────────────────────────────────
CONFIG_NAME = ".memento.toml"
DEFAULT_MEMORY_DIR = "docs/memory"
SEED_FILES = (
    "DECISIONS.md",
    "TASKS.md",
    "CONTRACTS.md",
    "SESSION_LOG.md",
    "EVALUATION.md",
)
TYPE_MAP = {
    "decision": ("DECISIONS.md", "dec"),
    "contract": ("CONTRACTS.md", "con"),
    "task": ("TASKS.md", "task"),
    "log": ("SESSION_LOG.md", "log"),
    "evaluation": ("EVALUATION.md", "ev"),
}


class MementoError(Exception):
    """Config/lookup problem; tools report it back as an `error: ...` string."""


def find_memory_dir() -> Path:
    """Resolve the memory dir per call: MEMENTO_ROOT env -> .memento.toml
    walk-up -> default `docs/memory` under cwd."""
    env = os.environ.get("MEMENTO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    for d in (Path.cwd(), *Path.cwd().parents):
        cfg = d / CONFIG_NAME
        if cfg.is_file():
            try:
                data = tomllib.loads(cfg.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
                raise MementoError(f"cannot read {cfg}: {exc}") from exc
            mdir = data.get("memory_dir", DEFAULT_MEMORY_DIR)
            if not isinstance(mdir, str) or not mdir.strip():
                raise MementoError(f"{cfg}: memory_dir must be a non-empty string")
            return (d / mdir).resolve()
    return (Path.cwd() / DEFAULT_MEMORY_DIR).resolve()


# ─── parsing ───────────────────────────────────────
ID_RE = re.compile(r"<!--\s*id:\s*(\S+?)\s*-->")
TITLE_RE = re.compile(r"^#{1,2}\s+(.+?)\s*$")
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$")
TAGS_RE = re.compile(r"^\*\*Tags:\*\*\s*(.+?)\s*$")


def split_entries(text: str) -> list[dict]:
    """Split file text into {"id": str | None, "block": str} chunks in order;
    the preamble (before the first id marker) has id None."""
    matches = list(ID_RE.finditer(text))
    if not matches:
        return [{"id": None, "block": text}] if text.strip() else []
    entries: list[dict] = []
    pre = text[: matches[0].start()]
    if pre.strip():
        entries.append({"id": None, "block": pre})
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append({"id": m.group(1), "block": text[m.start() : end]})
    return entries


def parse_entry(eid: str | None, block: str) -> dict:
    """Parse one entry block into {id, title, status, tags, body}."""
    lines = block.split("\n")
    if eid is not None and lines and ID_RE.search(lines[0]):
        lines = lines[1:]
    title: str | None = None
    status: str | None = None
    tags: list[str] = []
    rest: list[str] = []
    for ln in lines:
        if title is None and (m := TITLE_RE.match(ln)):
            title = m.group(1)
        elif status is None and (m := STATUS_RE.match(ln)):
            status = m.group(1)
        elif not tags and (m := TAGS_RE.match(ln)):
            tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
        else:
            rest.append(ln)
    return {
        "id": eid,
        "title": title,
        "status": status,
        "tags": tags,
        "body": "\n".join(rest).strip("\n"),
    }


def render_entry(e: dict) -> str:
    """Render an entry dict back to canonical markdown."""
    out = [f"<!-- id: {e['id']} -->"]
    if e["title"]:
        out.append(f"## {e['title']}")
    meta = []
    if e["status"]:
        meta.append(f"**Status:** {e['status']}")
    if e["tags"]:
        meta.append("**Tags:** " + ", ".join(e["tags"]))
    if meta:
        out.append("")
        out.extend(meta)
    body = e["body"].strip("\n")
    if body:
        out.append("")
        out.append(body)
    return "\n".join(out) + "\n"


# ─── file ops ──────────────────────────────────────
def _safe_name(name: str) -> str:
    if not name.endswith(".md") or "/" in name or "\\" in name or name != name.strip():
        raise MementoError(f"invalid file name: {name!r}")
    return name


def read_file(mem: Path, name: str) -> str:
    p = mem / _safe_name(name)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def write_file(mem: Path, name: str, text: str) -> None:
    mem.mkdir(parents=True, exist_ok=True)
    (mem / _safe_name(name)).write_text(text, encoding="utf-8")


def seed_files(mem: Path) -> None:
    for name in SEED_FILES:
        if not (mem / name).exists():
            write_file(mem, name, "")


def next_id(mem: Path, prefix: str) -> str:
    nums = [0]
    if mem.is_dir():
        for f in mem.glob("*.md"):
            for m in ID_RE.finditer(f.read_text(encoding="utf-8")):
                eid = m.group(1)
                if eid.startswith(prefix + "-") and eid[len(prefix) + 1 :].isdigit():
                    nums.append(int(eid[len(prefix) + 1 :]))
    return f"{prefix}-{max(nums) + 1:03d}"


def append_entry(mem: Path, name: str, entry: dict) -> str:
    text = read_file(mem, name)
    text = text.rstrip("\n") + "\n\n" if text.strip() else ""
    write_file(mem, name, text + render_entry(entry))
    return entry["id"]


def update_entry(
    mem: Path,
    entry_id: str,
    status: str | None = None,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
) -> str:
    if mem.is_dir():
        for f in sorted(mem.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            for ent in split_entries(text):
                if ent["id"] != entry_id:
                    continue
                e = parse_entry(ent["id"], ent["block"])
                if status is not None:
                    e["status"] = status
                if title is not None:
                    e["title"] = title
                if body is not None:
                    e["body"] = body.strip("\n")
                if tags is not None:
                    e["tags"] = list(tags)
                f.write_text(text.replace(ent["block"], render_entry(e), 1), encoding="utf-8")
                return f"updated {entry_id} in {f.name}"
    raise MementoError(f"entry not found: {entry_id}")


# ─── MCP tools ─────────────────────────────────────
def read_all() -> str:
    """Load the whole project memory: every markdown file in the memory
    folder, concatenated, each prefixed with a <!-- file: NAME --> marker."""
    try:
        mem = find_memory_dir()
        parts = []
        if mem.is_dir():
            for f in sorted(mem.glob("*.md")):
                text = f.read_text(encoding="utf-8").strip("\n")
                if text.strip():
                    parts.append(f"<!-- file: {f.name} -->\n\n{text}")
        return "\n\n".join(parts) if parts else "memory is empty"
    except MementoError as exc:
        return f"error: {exc}"


def search(query: str, file: str | None = None) -> str:
    """Case-insensitive substring search over entry titles, bodies, tags and
    status. Optional `file` (e.g. "DECISIONS.md") to scope. Returns full
    matching entry blocks with id + file, ready to feed update."""
    try:
        q = query.lower().strip()
        if not q:
            return "error: empty query"
        mem = find_memory_dir()
        only = _safe_name(file) if file else None
        hits = []
        if mem.is_dir():
            for f in sorted(mem.glob("*.md")):
                if only and f.name != only:
                    continue
                for ent in split_entries(f.read_text(encoding="utf-8")):
                    if ent["id"] is None:
                        continue
                    e = parse_entry(ent["id"], ent["block"])
                    hay = " ".join(
                        x
                        for x in (e["title"], e["status"], " ".join(e["tags"]), e["body"])
                        if x
                    ).lower()
                    if q in hay:
                        hits.append(f"<!-- file: {f.name} -->\n{ent['block'].strip()}")
        return "\n\n---\n\n".join(hits) if hits else f"no matches for {query!r}"
    except MementoError as exc:
        return f"error: {exc}"


def write(type: str, title: str, body: str, tags: list[str] | None = None) -> str:
    """Write a new memory entry. type: decision | contract | task | log |
    evaluation (unknown types get their own {TYPE}S.md file). Appends to the
    matching file with a fresh sequential id and Status: active."""
    try:
        t = (type or "").strip().lower()
        if not t:
            return "error: type is required"
        if not title.strip():
            return "error: title is required"
        name, prefix = TYPE_MAP.get(t, (f"{t.upper()}S.md", t[:3]))
        mem = find_memory_dir()
        seed_files(mem)
        eid = next_id(mem, prefix)
        status = None if t == "log" else "active"
        append_entry(
            mem,
            name,
            {
                "id": eid,
                "title": title.strip(),
                "status": status,
                "tags": tags or [],
                "body": body.strip("\n"),
            },
        )
        return f"created {eid} in {name}"
    except MementoError as exc:
        return f"error: {exc}"


def update(
    entry_id: str,
    status: str | None = None,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update an existing entry by id (e.g. "dec-001"). Only the fields you
    pass are changed; the rest of the file is preserved byte-for-byte."""
    try:
        if not entry_id.strip():
            return "error: entry_id is required"
        return update_entry(
            find_memory_dir(), entry_id.strip(), status, title, body, tags
        )
    except MementoError as exc:
        return f"error: {exc}"


def log(body: str, tags: list[str] | None = None) -> str:
    """Append a session log entry. The first line of body becomes the title."""
    try:
        lines = body.strip("\n").split("\n", 1)
        title = lines[0].strip()
        if not title:
            return "error: empty body"
        rest = lines[1].strip("\n") if len(lines) > 1 else ""
        mem = find_memory_dir()
        seed_files(mem)
        eid = next_id(mem, "log")
        append_entry(
            mem,
            "SESSION_LOG.md",
            {"id": eid, "title": title, "status": None, "tags": tags or [], "body": rest},
        )
        return f"created {eid} in SESSION_LOG.md"
    except MementoError as exc:
        return f"error: {exc}"


# ─── init ──────────────────────────────────────────
SNIPPET_HEADING = "## Memory Protocol (Memento)"
SNIPPET = """\
## Memory Protocol (Memento)

You have a Memento MCP server for project memory.

- **Session start:** call `read_all` to load memory.
- **Before asking a question:** call `search` first.
- **Architectural choice:** `write` with type=decision. Include the why.
- **New invariant:** `write` with type=contract.
- **Task finished:** `update` its status to `done`.
- **End of session:** `log` a 3–5 line summary.
- **Never edit `docs/memory/*.md` by hand.** Use the tools.
"""


def init_project(root: Path) -> None:
    """Scaffold .memento.toml + the AGENTS.md snippet into `root` (idempotent)."""
    cfg = root / CONFIG_NAME
    if cfg.exists():
        print(f"{CONFIG_NAME} already exists, leaving it alone")
    else:
        cfg.write_text('memory_dir = "docs/memory"\n', encoding="utf-8")
        print(f"created {CONFIG_NAME} (memory_dir = docs/memory)")

    agents = root / "AGENTS.md"
    if agents.exists():
        text = agents.read_text(encoding="utf-8")
        if SNIPPET_HEADING in text:
            print("AGENTS.md already contains the Memento snippet")
        else:
            agents.write_text(
                text.rstrip("\n") + "\n\n" + SNIPPET, encoding="utf-8"
            )
            print("appended the Memento snippet to AGENTS.md")
    else:
        agents.write_text(SNIPPET, encoding="utf-8")
        print("created AGENTS.md with the Memento snippet")

    print(
        "\nNext steps:\n"
        "1. Register the MCP server once, pointing uv at memento_server.py (see README).\n"
        "2. Claude Code only: add 'See AGENTS.md for the memory protocol.' to CLAUDE.md."
    )


for fn in (read_all, search, write, update, log):
    mcp.add_tool(fn)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_project(Path.cwd())
    else:
        mcp.run()
