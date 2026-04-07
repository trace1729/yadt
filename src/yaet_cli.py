from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import run_book_pipeline as pipeline
import translate_text_cli as text_cli


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Run YAET staged pipeline and translation commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    markdown_commands = {
        "pdf2markdown": "Convert a PDF to Markdown, optionally translating it.",
        "epub2markdown": "Convert an EPUB to Markdown, optionally translating it.",
    }
    for name, description in markdown_commands.items():
        subparser = subparsers.add_parser(name, description=description)
        subparser.add_argument("input_path")
        subparser.add_argument("-o", "--output", dest="output_path")
        subparser.add_argument("--translate", action="store_true")
        subparser.add_argument("--bilingual", action="store_true")
        _add_shared_translate_args(subparser)

    epub_subparser = subparsers.add_parser("pdf2epub", description="Convert a PDF to EPUB, optionally through bilingual translation.")
    epub_subparser.add_argument("input_path")
    epub_subparser.add_argument("-o", "--output", dest="output_path")
    epub_subparser.add_argument("--translate", action="store_true")
    epub_subparser.add_argument("--bilingual", action="store_true")
    epub_subparser.add_argument("--title")
    epub_subparser.add_argument("--author")
    _add_shared_translate_args(epub_subparser)

    translate_epub = subparsers.add_parser(
        "epub2epub",
        description="Convert an EPUB to Markdown, translate it, and export a bilingual EPUB.",
    )
    translate_epub.add_argument("input_path")
    translate_epub.add_argument("-o", "--output", dest="output_path")
    translate_epub.add_argument("--title")
    translate_epub.add_argument("--author")
    _add_shared_translate_args(translate_epub)

    subparsers.add_parser("translate", description="Translate short text or plain-text content.")

    return parser.parse_known_args(argv)


def _add_shared_translate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=pipeline.DEFAULT_MODEL)
    parser.add_argument("--max-chars-per-chunk", type=int, default=pipeline.DEFAULT_MAX_CHARS_PER_CHUNK)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)


def _resolve_output_mode(args: argparse.Namespace) -> str:
    if getattr(args, "bilingual", False):
        return "bilingual"
    return "chinese"


def _translate_and_maybe_cleanup(markdown_path: Path, paths: pipeline.PipelinePaths, args: argparse.Namespace) -> Path:
    translated_path = pipeline.translate_markdown_file(
        markdown_path,
        paths.bilingual_markdown_path,
        paths.cache_path,
        model=args.model,
        max_chars_per_chunk=args.max_chars_per_chunk,
        max_workers=args.max_workers,
        resume=args.resume,
        output_mode=_resolve_output_mode(args),
    )
    if _resolve_output_mode(args) == "bilingual":
        pipeline.cleanup_markdown_file(translated_path)
    return translated_path


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_args(argv)

    if args.command == "translate":
        return text_cli.main(extra_args)

    input_path = Path(args.input_path)
    paths = pipeline.derive_output_paths(input_path)
    metadata = pipeline.read_input_metadata(input_path)

    if args.command in {"pdf2markdown", "epub2markdown"}:
        markdown_output = Path(args.output_path) if args.output_path else paths.markdown_path
        markdown_path = pipeline.convert_source_to_markdown(input_path, markdown_output)
        if not args.translate:
            return 0
        _translate_and_maybe_cleanup(markdown_path, paths, args)
        return 0

    if args.command == "pdf2epub":
        markdown_path = pipeline.convert_source_to_markdown(input_path, paths.markdown_path)
        export_source = markdown_path
        export_title = args.title or metadata.title
        export_author = args.author or metadata.author
        if args.translate:
            export_source = _translate_and_maybe_cleanup(markdown_path, paths, args)
            if _resolve_output_mode(args) == "bilingual":
                export_title = pipeline.build_bilingual_title(args.title or metadata.title)
        output_epub_path = Path(args.output_path) if args.output_path else paths.bilingual_epub_path
        pipeline.export_markdown_to_epub(
            export_source,
            output_epub_path,
            title=export_title,
            author=export_author,
        )
        return 0

    if args.command == "epub2epub":
        markdown_path = pipeline.convert_source_to_markdown(input_path, paths.markdown_path)
        bilingual_path = pipeline.translate_markdown_file(
            markdown_path,
            paths.bilingual_markdown_path,
            paths.cache_path,
            model=args.model,
            max_chars_per_chunk=args.max_chars_per_chunk,
            max_workers=args.max_workers,
            resume=args.resume,
            output_mode="bilingual",
        )
        pipeline.cleanup_markdown_file(bilingual_path)
        output_epub_path = Path(args.output_path) if args.output_path else paths.bilingual_epub_path
        pipeline.export_markdown_to_epub(
            bilingual_path,
            output_epub_path,
            title=pipeline.build_bilingual_title(args.title or metadata.title),
            author=args.author or metadata.author,
        )
        return 0

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
