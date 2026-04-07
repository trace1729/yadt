from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ebooklib import epub

from convert_pdf_to_markdown import convert_pdf_to_markdown, load_mineru_api_key
from convert_epub_to_markdown import convert_epub_to_markdown, primary_metadata_value
from convert_markdown_to_epub import write_epub
from cleanup_bilingual_markdown import postprocess_markdown
from fix_special_toc_links import fix_special_toc_headings
from output_paths import book_output_dir, canonical_book_name, sanitize_book_dir_name
from translate_markdown_book import create_client, load_api_key, run_translation_pipeline


DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MAX_CHARS_PER_CHUNK = 6000
DEFAULT_AUTHOR = "Unknown Author"


@dataclass(frozen=True)
class PipelinePaths:
    markdown_path: Path
    cache_path: Path
    bilingual_markdown_path: Path
    bilingual_epub_path: Path


@dataclass(frozen=True)
class BookMetadata:
    title: str
    author: str
    bilingual_title: str


@dataclass(frozen=True)
class PipelineResult:
    paths: PipelinePaths
    metadata: BookMetadata


def derive_output_paths(input_path: Path, output_prefix: Path | None = None) -> PipelinePaths:
    prefix = output_prefix if output_prefix is not None else book_output_dir(input_path) / sanitize_book_dir_name(canonical_book_name(input_path))
    return PipelinePaths(
        markdown_path=prefix.with_suffix(".md"),
        cache_path=prefix.with_name(f"{prefix.name}.translation_cache.json"),
        bilingual_markdown_path=prefix.with_name(f"{prefix.name}.bilingual.md"),
        bilingual_epub_path=prefix.with_name(f"{prefix.name}.bilingual.epub"),
    )


def build_bilingual_title(title: str) -> str:
    return title if title.endswith("(Bilingual)") else f"{title} (Bilingual)"


def read_epub_metadata(input_path: Path) -> BookMetadata:
    book = epub.read_epub(str(input_path))
    title = primary_metadata_value(book.get_metadata("DC", "title")) or input_path.stem
    author = primary_metadata_value(book.get_metadata("DC", "creator")) or DEFAULT_AUTHOR
    return BookMetadata(title=title, author=author, bilingual_title=build_bilingual_title(title))


def read_input_metadata(input_path: Path) -> BookMetadata:
    if input_path.suffix.lower() == ".epub":
        return read_epub_metadata(input_path)
    title = input_path.stem
    return BookMetadata(title=title, author=DEFAULT_AUTHOR, bilingual_title=build_bilingual_title(title))


def convert_source_to_markdown(input_path: Path, output_path: Path | None = None) -> Path:
    target_path = output_path or derive_output_paths(input_path).markdown_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".pdf":
        mineru_api_key = load_mineru_api_key()
        if not mineru_api_key:
            raise SystemExit("Missing MINERU_API_KEY; set the env var or add it to .env")
        convert_pdf_to_markdown(input_path, target_path, api_key=mineru_api_key)
        return target_path

    convert_epub_to_markdown(input_path, target_path)
    fixed_markdown = fix_special_toc_headings(target_path.read_text(encoding="utf-8"))
    target_path.write_text(fixed_markdown, encoding="utf-8")
    return target_path


def translate_markdown_file(
    input_path: Path,
    output_path: Path,
    cache_path: Path,
    *,
    model: str = DEFAULT_MODEL,
    max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    max_workers: int = 3,
    resume: bool = True,
    output_mode: str = "bilingual",
) -> Path:
    api_key = load_api_key()
    if not api_key:
        raise SystemExit("Missing DEEPSEEK_API_KEY; set the env var or add it to .env")

    client = create_client(api_key)
    run_translation_pipeline(
        input_path=input_path,
        output_path=output_path,
        client=client,
        model=model,
        max_chars_per_chunk=max_chars_per_chunk,
        cache_path=cache_path,
        resume=resume,
        max_workers=max_workers,
        output_mode=output_mode,
    )
    return output_path


def cleanup_markdown_file(path: Path) -> Path:
    processed_markdown = postprocess_markdown(path.read_text(encoding="utf-8"))
    path.write_text(processed_markdown, encoding="utf-8")
    return path


def export_markdown_to_epub(
    input_path: Path,
    output_path: Path,
    *,
    title: str,
    author: str,
) -> Path:
    write_epub(input_path, output_path, title=title, author=author)
    return output_path


def run_pipeline(
    input_path: Path,
    *,
    output_prefix: Path | None = None,
    title: str | None = None,
    author: str | None = None,
    model: str = DEFAULT_MODEL,
    max_chars_per_chunk: int = DEFAULT_MAX_CHARS_PER_CHUNK,
    max_workers: int = 3,
    resume: bool = True,
) -> PipelineResult:
    paths = derive_output_paths(input_path, output_prefix=output_prefix)
    for directory in {
        paths.markdown_path.parent,
        paths.cache_path.parent,
        paths.bilingual_markdown_path.parent,
        paths.bilingual_epub_path.parent,
    }:
        directory.mkdir(parents=True, exist_ok=True)
    source_metadata = read_input_metadata(input_path)
    metadata = BookMetadata(
        title=title or source_metadata.title,
        author=author or source_metadata.author,
        bilingual_title=build_bilingual_title(title or source_metadata.title),
    )

    convert_source_to_markdown(input_path, paths.markdown_path)
    translate_markdown_file(
        paths.markdown_path,
        paths.bilingual_markdown_path,
        paths.cache_path,
        model=model,
        max_chars_per_chunk=max_chars_per_chunk,
        max_workers=max_workers,
        resume=resume,
        output_mode="bilingual",
    )
    cleanup_markdown_file(paths.bilingual_markdown_path)
    export_markdown_to_epub(
        paths.bilingual_markdown_path,
        paths.bilingual_epub_path,
        title=metadata.bilingual_title,
        author=metadata.author,
    )

    return PipelineResult(paths=paths, metadata=metadata)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full EPUB -> bilingual Markdown -> EPUB pipeline.")
    parser.add_argument("input_path", help="Path to the source EPUB file.")
    parser.add_argument(
        "--output-prefix",
        help="Optional output prefix path. Defaults to output/<source_stem> beside the source EPUB.",
    )
    parser.add_argument("--title", help="Override the source title metadata.")
    parser.add_argument("--author", help="Override the source author metadata.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek model name.")
    parser.add_argument("--max-chars-per-chunk", type=int, default=DEFAULT_MAX_CHARS_PER_CHUNK)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_pipeline(
        Path(args.input_path),
        output_prefix=Path(args.output_prefix) if args.output_prefix else None,
        title=args.title,
        author=args.author,
        model=args.model,
        max_chars_per_chunk=args.max_chars_per_chunk,
        max_workers=args.max_workers,
        resume=args.resume,
    )

    print(f"Markdown: {result.paths.markdown_path}")
    print(f"Cache: {result.paths.cache_path}")
    print(f"Bilingual Markdown: {result.paths.bilingual_markdown_path}")
    print(f"Bilingual EPUB: {result.paths.bilingual_epub_path}")
    print(f"Title: {result.metadata.bilingual_title}")
    print(f"Author: {result.metadata.author}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
