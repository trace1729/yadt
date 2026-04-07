from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


HEADING_RE = re.compile(r"^(#{1,6}) (.+)$")
IMAGE_RE = re.compile(r"^!\[[^\]]*\]\((?:[^()\n]|\([^()\n]*\))+\)$")
LINK_RE = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<target>[^)]+)\)")
REFERENCE_LINK_RE = re.compile(r"\[(?P<title>[^\]]+)\]\[(?P<target>[^\]]+)\]")
SEPARATOR_RE = re.compile(r"^∞+$")
NUMERIC_PREFIX_RE = re.compile(r"^(§?\d+(?:[-.]\d+)*\.?\s*)")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def split_blocks(markdown: str) -> list[str]:
    stripped = markdown.strip()
    if not stripped:
        return []
    return [block.strip() for block in re.split(r"\n\s*\n", stripped) if block.strip()]


def is_separator_block(block: str) -> bool:
    return bool(SEPARATOR_RE.fullmatch(block.strip()))


def is_image_block(block: str) -> bool:
    return bool(IMAGE_RE.fullmatch(block.strip()))


def parse_heading_block(block: str) -> tuple[str, str] | None:
    if "\n" in block:
        return None
    match = HEADING_RE.fullmatch(block.strip())
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def has_latin(text: str) -> bool:
    return bool(LATIN_RE.search(text))


def extract_numeric_prefix(text: str) -> str | None:
    match = NUMERIC_PREFIX_RE.match(text)
    if not match:
        return None
    return match.group(1)


def normalize_prefix(prefix: str) -> str:
    return re.sub(r"\s+", "", prefix)


def merge_heading_titles(english_title: str, chinese_title: str) -> str:
    chinese_suffix = chinese_title
    english_prefix = extract_numeric_prefix(english_title)
    chinese_prefix = extract_numeric_prefix(chinese_title)

    if english_prefix and chinese_prefix and normalize_prefix(english_prefix) == normalize_prefix(chinese_prefix):
        chinese_suffix = chinese_title[len(chinese_prefix) :].lstrip()

    if not chinese_suffix:
        return english_title
    return f"{english_title} ({chinese_suffix})"


def can_merge_headings(current_block: str, next_block: str) -> bool:
    current_heading = parse_heading_block(current_block)
    next_heading = parse_heading_block(next_block)
    if current_heading is None or next_heading is None:
        return False
    current_level, current_title = current_heading
    next_level, next_title = next_heading
    return current_level == next_level and has_latin(current_title) and has_cjk(next_title)


def collect_merged_heading_titles(blocks: Sequence[str]) -> dict[str, str]:
    merged_titles: dict[str, str] = {}
    index = 0

    while index < len(blocks):
        block = blocks[index]
        if can_merge_headings(block, blocks[index + 1]) if index + 1 < len(blocks) else False:
            _, english_title = parse_heading_block(block) or ("", "")
            _, chinese_title = parse_heading_block(blocks[index + 1]) or ("", "")
            merged_titles[english_title] = merge_heading_titles(english_title, chinese_title)
            index += 2
            continue
        index += 1

    return merged_titles


def update_link_titles(block: str, merged_heading_titles: dict[str, str]) -> str:
    def replace_inline_link(match: re.Match[str]) -> str:
        title = match.group("title")
        target = match.group("target")
        merged_title = merged_heading_titles.get(title, title)
        return f"[{merged_title}]({target})"

    def replace_reference_link(match: re.Match[str]) -> str:
        title = match.group("title")
        target = match.group("target")
        merged_title = merged_heading_titles.get(title, title)
        return f"[{merged_title}][{target}]"

    updated_block = LINK_RE.sub(replace_inline_link, block)
    return REFERENCE_LINK_RE.sub(replace_reference_link, updated_block)


def postprocess_markdown(markdown: str) -> str:
    blocks = split_blocks(markdown)
    merged_heading_titles = collect_merged_heading_titles(blocks)
    processed: list[str] = []
    index = 0

    while index < len(blocks):
        block = blocks[index]

        if is_separator_block(block):
            index += 1
            continue

        if can_merge_headings(block, blocks[index + 1]) if index + 1 < len(blocks) else False:
            level, english_title = parse_heading_block(block) or ("", "")
            _, chinese_title = parse_heading_block(blocks[index + 1]) or ("", "")
            processed.append(f"{level} {merge_heading_titles(english_title, chinese_title)}")
            index += 2
            continue

        if is_image_block(block):
            processed.append(block)
            index += 1
            while index < len(blocks) and blocks[index] == block:
                index += 1
            continue

        processed.append(update_link_titles(block, merged_heading_titles))
        index += 1

    if not processed:
        return ""
    return "\n\n".join(processed) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post-process bilingual markdown by merging headings and removing noise.")
    parser.add_argument("input_path", help="Path to the bilingual markdown file.")
    parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        help="Optional output path. Defaults to overwriting the input file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path) if args.output_path else input_path

    markdown = input_path.read_text(encoding="utf-8")
    output_path.write_text(postprocess_markdown(markdown), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
