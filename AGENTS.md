<!-- Memento snippet — copy everything below into your project's AGENTS.md. -->

## Memory Protocol (Memento)

You have a Memento MCP server for project memory.

- **Session start:** call `read_all` to load memory.
- **Before asking a question:** call `search` first.
- **Architectural choice:** `write` with type=decision. Include the why.
- **New invariant:** `write` with type=contract.
- **Task finished:** `update` its status to `done`.
- **End of session:** `log` a 3–5 line summary.
- **Never edit `docs/memory/*.md` by hand.** Use the tools.
