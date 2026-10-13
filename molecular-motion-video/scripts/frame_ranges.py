#!/usr/bin/env python3
"""Plan, resume and audit chunked renders.

  split  N chunks of the whole animation          -> prints "a-b" ranges
  missing frames not yet on disk (or 0-byte)      -> prints "a-b" ranges to re-render
  check  exit 1 unless every frame 1..total exists, is non-empty and has the same size class

Frames are expected as <dir>/####.png (Blender default with '####').
Combine with the scene script's --frames a-b to resume after a crash, or to spread
ranges over several machines/nodes, then merge into one folder.

Examples:
  python3 frame_ranges.py split --total 735 --chunks 4
  python3 frame_ranges.py missing --dir render/final --total 735
  python3 frame_ranges.py check --dir render/final --total 735
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path


def ranges(frames: list[int]) -> list[str]:
    out, start, prev = [], None, None
    for f in frames:
        if start is None:
            start = prev = f
        elif f == prev + 1:
            prev = f
        else:
            out.append(f"{start}-{prev}")
            start = prev = f
    if start is not None:
        out.append(f"{start}-{prev}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["split", "missing", "check"])
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--chunks", type=int, default=2)
    ap.add_argument("--dir")
    args = ap.parse_args()
    if args.cmd == "split":
        size = -(-args.total // args.chunks)
        print("\n".join(f"{a}-{min(a + size - 1, args.total)}" for a in range(1, args.total + 1, size)))
        return
    d = Path(args.dir)
    sizes = {f: (d / f"{f:04d}.png").stat().st_size if (d / f"{f:04d}.png").exists() else 0 for f in range(1, args.total + 1)}
    missing = [f for f, s in sizes.items() if s == 0]
    if args.cmd == "missing":
        print("\n".join(ranges(missing)) or "none")
        return
    present = [s for s in sizes.values() if s]
    med = statistics.median(present) if present else 0
    suspicious = [f for f, s in sizes.items() if s and s < 0.3 * med]  # truncated / blank renders
    print(f"present {len(present)}/{args.total}; missing {ranges(missing) or 'none'}; suspicious(small) {ranges(suspicious) or 'none'}")
    sys.exit(1 if missing or suspicious else 0)


if __name__ == "__main__":
    main()
