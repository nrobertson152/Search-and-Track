"""Mirror the in-game manual (data/manual/*.md) into docs/manual for reading on GitHub.

    python tools/sync_manual.py          # write docs/manual
    python tools/sync_manual.py --check  # exit 1 if docs/manual is out of date
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "manual"
DST = ROOT / "docs" / "manual"


def expected() -> dict[str, str]:
    files = sorted(SRC.glob("*.md"))
    out = {p.name: p.read_text(encoding="utf-8") for p in files}
    lines = ["# Search and Track — Operator's Manual", "",
             "The same manual is in the game: OPERATOR'S MANUAL on the title screen, or Esc → OPERATOR'S MANUAL "
             "during a watch. Edit the chapters in `data/manual/`, then run `python tools/sync_manual.py`.", ""]
    for i, p in enumerate(files, 1):
        text = out[p.name].splitlines()
        title = next((ln[2:].strip() for ln in text if ln.startswith("# ")), p.stem)
        sub = next((ln[2:].strip() for ln in text if ln.startswith("> ")), "")
        lines.append(f"{i}. [{title}]({p.name})" + (f" — {sub}" if sub else ""))
    out["README.md"] = "\n".join(lines) + "\n"
    return out


def main() -> int:
    want = expected()
    if "--check" in sys.argv:
        have = {p.name: p.read_text(encoding="utf-8") for p in DST.glob("*.md")} if DST.exists() else {}
        if have != want:
            print("docs/manual is out of date: run python tools/sync_manual.py")
            return 1
        return 0
    DST.mkdir(parents=True, exist_ok=True)
    for p in DST.glob("*.md"):
        if p.name not in want:
            p.unlink()
    for name, text in want.items():
        (DST / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(want)} files to {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
