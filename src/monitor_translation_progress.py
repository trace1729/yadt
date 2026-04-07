from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from translate_markdown_book import block_cache_key, parse_blocks


@dataclass(frozen=True)
class Progress:
    total_blocks: int
    completed_blocks: int
    remaining_blocks: int
    percent: float


def compute_progress(source_path: Path, cache_path: Path, model: str) -> Progress:
    source = source_path.read_text(encoding="utf-8")
    blocks = [block for block in parse_blocks(source) if block.translatable]

    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache = {}

    completed_blocks = sum(1 for block in blocks if block_cache_key(block, model) in cache)
    total_blocks = len(blocks)
    remaining_blocks = max(total_blocks - completed_blocks, 0)
    percent = (completed_blocks / total_blocks * 100.0) if total_blocks else 100.0
    return Progress(
        total_blocks=total_blocks,
        completed_blocks=completed_blocks,
        remaining_blocks=remaining_blocks,
        percent=percent,
    )


def estimate_eta_seconds(samples: Sequence[tuple[float, int]], remaining_blocks: int) -> int | None:
    if len(samples) < 2 or remaining_blocks <= 0:
        return 0 if remaining_blocks <= 0 else None

    start_time, start_completed = samples[0]
    end_time, end_completed = samples[-1]
    elapsed = end_time - start_time
    progressed = end_completed - start_completed
    if elapsed <= 0 or progressed <= 0:
        return None

    rate = progressed / elapsed
    return int(remaining_blocks / rate)


def _format_eta(eta_seconds: int | None) -> str:
    if eta_seconds is None:
        return "--:--:--"
    hours, remainder = divmod(max(eta_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def render_progress_line(completed: int, total: int, width: int = 20, eta_seconds: int | None = None) -> str:
    if total <= 0:
        percent = 100.0
        filled = width
    else:
        percent = completed / total * 100.0
        filled = min(width, int(width * completed / total))
    bar = "█" * filled + "░" * (width - filled)
    return f"Progress: [{bar}] {percent:5.1f}% ({completed}/{total}) ETA={_format_eta(eta_seconds)}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show translation progress based on the cache file.")
    parser.add_argument("source_path", nargs="?", default="The_society_of_mind.md")
    parser.add_argument("--cache-path", default=".translation_cache.json")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--width", type=int, default=24)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = Path(args.source_path)
    cache_path = Path(args.cache_path)
    samples: list[tuple[float, int]] = []

    while True:
        progress = compute_progress(source_path, cache_path, model=args.model)
        samples.append((time.time(), progress.completed_blocks))
        samples = samples[-10:]
        eta_seconds = estimate_eta_seconds(samples, progress.remaining_blocks)
        line = render_progress_line(
            progress.completed_blocks,
            progress.total_blocks,
            width=args.width,
            eta_seconds=eta_seconds,
        )
        suffix = f" remaining={progress.remaining_blocks} cache={cache_path.stat().st_size if cache_path.exists() else 0}B"
        print(f"\r{line}{suffix}", end="", flush=True)
        if args.once or progress.completed_blocks >= progress.total_blocks:
            print()
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
