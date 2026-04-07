from __future__ import annotations

import re
from pathlib import Path


DEFAULT_OUTPUT_DIR_NAME = "output"


def canonical_book_name(path: Path) -> str:
    name = path.name
    for suffix in (
        ".translation_cache.json",
        ".bilingual.epub",
        ".bilingual.md",
        ".epub",
        ".md",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def sanitize_book_dir_name(name: str) -> str:
    cleaned = re.sub(r"[\s_]+", "_", name.strip())
    return cleaned or "book"


def book_output_dir(input_path: Path) -> Path:
    book_name = canonical_book_name(input_path)
    directory_name = sanitize_book_dir_name(book_name)
    if input_path.parent.name == directory_name and input_path.parent.parent.name == DEFAULT_OUTPUT_DIR_NAME:
        return input_path.parent
    return input_path.parent / DEFAULT_OUTPUT_DIR_NAME / directory_name
