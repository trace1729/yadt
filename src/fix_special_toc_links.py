from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


LINK_RE = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+)$")
CONTENTS_MARKERS = {"CONTENTS"}
MAX_SPECIAL_TITLE_LENGTH = 48


def normalize_heading_key(text: str) -> str:
    return re.sub(r"[\s_]+", "", text).upper()


def anchor_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.upper())
    return "_".join(words) if words else title.strip().replace(" ", "_")


def anchor_for_link(title: str, target: str) -> str:
    return target[1:] if target.startswith("#") else anchor_from_title(title)


def is_special_caps_title(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_SPECIAL_TITLE_LENGTH:
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    return stripped == stripped.upper()


def collect_contents_targets(lines: Sequence[str]) -> tuple[dict[str, str], set[int]]:
    target_map: dict[str, str] = {}
    toc_line_indexes: set[int] = set()
    in_contents = False
    seen_link = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in CONTENTS_MARKERS:
            in_contents = True
            seen_link = False
            continue

        if not in_contents:
            continue

        if not stripped:
            if seen_link:
                continue
            continue

        match = LINK_RE.fullmatch(stripped)
        if match:
            seen_link = True
            title = match.group("title").strip()
            anchor = anchor_for_link(title, match.group("target").strip())
            target_map[normalize_heading_key(title)] = anchor
            target_map[normalize_heading_key(anchor)] = anchor
            toc_line_indexes.add(index)
            continue

        if seen_link:
            break

    if target_map:
        return target_map, toc_line_indexes

    for index, line in enumerate(lines):
        stripped = line.strip()
        match = LINK_RE.fullmatch(stripped)
        if not match:
            continue
        target = match.group("target").strip()
        if not target.startswith("#"):
            continue
        title = match.group("title").strip()
        anchor = anchor_for_link(title, target)
        target_map[normalize_heading_key(title)] = anchor
        target_map[normalize_heading_key(anchor)] = anchor
        toc_line_indexes.add(index)

    return target_map, toc_line_indexes


def is_promotable_title_line(lines: Sequence[str], index: int) -> bool:
    current = lines[index].strip()
    if not current:
        return False

    previous = lines[index - 1].strip() if index > 0 else ""
    following = lines[index + 1].strip() if index + 1 < len(lines) else ""
    return not previous and (not following or not following.startswith("["))


def fix_special_toc_headings(markdown: str) -> str:
    trailing_newline = markdown.endswith("\n")
    lines = markdown.splitlines()
    target_map, toc_line_indexes = collect_contents_targets(lines)
    if not target_map:
        return markdown

    updated = list(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if index in toc_line_indexes:
            match = LINK_RE.fullmatch(stripped)
            if match:
                title = match.group("title").strip()
                if not is_special_caps_title(title):
                    continue
                anchor = anchor_for_link(title, match.group("target").strip())
                updated[index] = f"[{title}](#{anchor})"
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            if heading_match.group(1) == "#":
                continue
            heading_title = heading_match.group("title").strip()
            if not is_special_caps_title(heading_title):
                continue
            anchor = target_map.get(normalize_heading_key(heading_title))
            if anchor and stripped != f"## {anchor}":
                updated[index] = f"## {anchor}"
            continue

        anchor = target_map.get(normalize_heading_key(stripped))
        if anchor and is_special_caps_title(stripped) and is_promotable_title_line(lines, index):
            updated[index] = f"## {anchor}"

    output = "\n".join(updated)
    if trailing_newline:
        return output + "\n"
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix special internal TOC heading edge cases in Markdown.")
    parser.add_argument("input_path", help="Path to the Markdown file.")
    parser.add_argument("-o", "--output", dest="output_path", help="Optional output path. Defaults to overwriting the input file.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path) if args.output_path else input_path
    markdown = input_path.read_text(encoding="utf-8")
    output_path.write_text(fix_special_toc_headings(markdown), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
