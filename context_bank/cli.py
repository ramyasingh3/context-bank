"""CLI for file-based project memory and CLAUDE.md / AGENTS.md helpers."""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MEMORY_FILES = [
    "projectbrief.md",
    "productContext.md",
    "systemPatterns.md",
    "techContext.md",
    "activeContext.md",
    "progress.md",
    "decisions.md",
]


TEMPLATES = {
    "projectbrief.md": "# Project Brief\n\n- Name:\n- Goal:\n- Non-goals:\n",
    "productContext.md": "# Product Context\n\n- Users:\n- Problems:\n- Success metrics:\n",
    "systemPatterns.md": "# System Patterns\n\n- Architecture:\n- Key invariants:\n- Conventions:\n",
    "techContext.md": "# Tech Context\n\n- Languages:\n- Frameworks:\n- Infra:\n",
    "activeContext.md": "# Active Context\n\n## Current focus\n\n- \n\n## Open questions\n\n- \n",
    "progress.md": "# Progress\n\n## Done\n\n- \n\n## Next\n\n- \n",
    "decisions.md": "# Decisions\n\n<!-- Append entries with: context-bank decide -->\n",
}

CLAUDE_MD = """# CLAUDE.md

Read these before larger changes:

1. `memory/activeContext.md`
2. `memory/progress.md`
3. `memory/decisions.md`
4. `memory/systemPatterns.md`

Keep diffs small. Don't contradict `memory/techContext.md`.
Update `progress.md` when a task lands; add non-obvious calls to `decisions.md`.
"""

AGENTS_MD = """# AGENTS.md

Project memory lives in `./memory/`. Prefer those files over guessing.
"""


def estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 chars/token for English/code mix.
    return max(1, (len(text) + 3) // 4)


@dataclass
class BudgetRow:
    path: str
    bytes: int
    tokens: int
    pct: float


def memory_dir(root: Path) -> Path:
    return root / "memory"


def init_project(root: Path, force: bool = False) -> None:
    mem = memory_dir(root)
    mem.mkdir(parents=True, exist_ok=True)
    for name in MEMORY_FILES:
        path = mem / name
        if path.exists() and not force:
            continue
        path.write_text(TEMPLATES[name], encoding="utf-8")
    for name, content in [("CLAUDE.md", CLAUDE_MD), ("AGENTS.md", AGENTS_MD)]:
        path = root / name
        if path.exists() and not force:
            continue
        path.write_text(content, encoding="utf-8")
    print(f"Initialized context-bank in {root}")
    print("  memory/*.md, CLAUDE.md, AGENTS.md")


def status(root: Path) -> None:
    mem = memory_dir(root)
    if not mem.exists():
        print("No memory/ found. Run: context-bank init")
        return
    print(f"Context bank @ {root}")
    for name in MEMORY_FILES:
        path = mem / name
        if not path.exists():
            print(f"  [missing] {name}")
            continue
        tokens = estimate_tokens(path.read_text(encoding="utf-8"))
        print(f"  {name:20} ~{tokens} tokens")
    active = mem / "activeContext.md"
    if active.exists():
        focus = _extract_section(active.read_text(encoding="utf-8"), "Current focus")
        if focus:
            print("\nCurrent focus:")
            print(textwrap.indent(focus.strip(), "  "))


def budget(root: Path, limit: int = 8000) -> None:
    mem = memory_dir(root)
    rows: list[BudgetRow] = []
    total = 0
    files = list(mem.glob("*.md")) if mem.exists() else []
    for extra in [root / "CLAUDE.md", root / "AGENTS.md"]:
        if extra.exists():
            files.append(extra)
    for path in files:
        text = path.read_text(encoding="utf-8")
        tok = estimate_tokens(text)
        total += tok
        rows.append(BudgetRow(str(path.relative_to(root)), len(text.encode()), tok, 0))
    for row in rows:
        row.pct = (row.tokens / total * 100) if total else 0
    rows.sort(key=lambda r: r.tokens, reverse=True)

    print(f"Context budget (approx) — limit {limit} tokens")
    print(f"{'file':40} {'tokens':>8} {'%':>7}")
    for row in rows:
        print(f"{row.path:40} {row.tokens:8d} {row.pct:6.1f}%")
    print("-" * 58)
    print(f"{'TOTAL':40} {total:8d}")
    if total > limit:
        print(f"OVER BUDGET by {total - limit} tokens — trim activeContext/progress or summarize decisions.")
    else:
        print(f"OK — {limit - total} tokens remaining under soft limit.")


def decide(root: Path, decision: str, reason: str = "") -> None:
    mem = memory_dir(root)
    mem.mkdir(parents=True, exist_ok=True)
    path = mem / "decisions.md"
    if not path.exists():
        path.write_text(TEMPLATES["decisions.md"], encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = f"\n## {stamp}\n\n**Decision:** {decision}\n"
    if reason:
        block += f"**Reason:** {reason}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    print(f"Recorded decision → {path}")


def pack(root: Path, out: Path, max_tokens: int = 4000) -> None:
    """Pack highest-signal memory into a single prompt blob under a token budget."""
    priority = [
        "activeContext.md",
        "progress.md",
        "decisions.md",
        "systemPatterns.md",
        "techContext.md",
        "projectbrief.md",
        "productContext.md",
    ]
    parts: list[str] = []
    used = 0
    mem = memory_dir(root)
    for name in priority:
        path = mem / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        tok = estimate_tokens(text)
        if used + tok > max_tokens and parts:
            break
        parts.append(f"<!-- {name} -->\n{text}")
        used += tok
    out.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote packed context ({used} tokens) → {out}")


def _extract_section(text: str, heading: str) -> str:
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s+|\Z)"
    m = re.search(pattern, text, re.S | re.I)
    return m.group(1) if m else ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="context-bank", description="File-based agent memory bank")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--root", type=Path, default=Path("."), help="project root")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", parents=[parent], help="create memory/ + CLAUDE.md + AGENTS.md")
    s.add_argument("--force", action="store_true")

    sub.add_parser("status", parents=[parent], help="show memory files and focus")
    b = sub.add_parser("budget", parents=[parent], help="token budget report")
    b.add_argument("--limit", type=int, default=8000)

    d = sub.add_parser("decide", parents=[parent], help="append an architecture decision")
    d.add_argument("decision")
    d.add_argument("--reason", default="")

    pk = sub.add_parser("pack", parents=[parent], help="pack memory into one file under a token budget")
    pk.add_argument("-o", "--out", type=Path, default=Path("memory/PACKED.md"))
    pk.add_argument("--max-tokens", type=int, default=4000)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.cmd == "init":
        init_project(root, force=args.force)
    elif args.cmd == "status":
        status(root)
    elif args.cmd == "budget":
        budget(root, limit=args.limit)
    elif args.cmd == "decide":
        decide(root, args.decision, args.reason)
    elif args.cmd == "pack":
        pack(root, (root / args.out).resolve() if not args.out.is_absolute() else args.out, args.max_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
