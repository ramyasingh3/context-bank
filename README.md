# context-bank

CLI for a file-based agent memory layout (`memory/*.md`) plus `CLAUDE.md` / `AGENTS.md`.

Also reports an approximate token budget and can pack memory into one file.

## Usage

```bash
pip install -e .
# or: PYTHONPATH=. python3 -m context_bank ...

context-bank init --root .
context-bank status --root .
context-bank budget --root . --limit 8000
context-bank decide --root . "Use Redis for rate limits" --reason "shared across instances"
context-bank pack --root . -o memory/PACKED.md --max-tokens 4000
```

## Layout

```
memory/
  projectbrief.md
  productContext.md
  systemPatterns.md
  techContext.md
  activeContext.md
  progress.md
  decisions.md
CLAUDE.md
AGENTS.md
```

Sample project: `examples/demo-project/`.

```bash
PYTHONPATH=. python3 -m context_bank status --root examples/demo-project
PYTHONPATH=. python3 -m context_bank budget --root examples/demo-project
```

## License

MIT
