from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import run_book_pipeline as pipeline
import translate_text_cli as text_cli
import yaet_config


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Run YAET staged pipeline and translation commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    markdown_commands = {
        "pdf2md": "Convert a PDF to Markdown, optionally translating it.",
        "epub2md": "Convert an EPUB to Markdown, optionally translating it.",
        "md2md": "Normalize or translate an existing Markdown file.",
    }
    for name, description in markdown_commands.items():
        subparser = subparsers.add_parser(name, description=description)
        subparser.add_argument("input_path")
        subparser.add_argument("-o", "--output", dest="output_path")
        subparser.add_argument("--config")
        subparser.add_argument("--epub-parser-backend", choices=("yaet", "epub_translator"))
        subparser.add_argument("--markdown-parser-backend", choices=("yaet", "free_markdown_translator"))
        subparser.add_argument("--translate", action="store_true")
        subparser.add_argument("--bilingual", action="store_true")
        _add_shared_translate_args(subparser)

    epub_subparser = subparsers.add_parser("pdf2epub", description="Convert a PDF to EPUB, optionally through bilingual translation.")
    epub_subparser.add_argument("input_path")
    epub_subparser.add_argument("-o", "--output", dest="output_path")
    epub_subparser.add_argument("--config")
    epub_subparser.add_argument("--epub-parser-backend", choices=("yaet", "epub_translator"))
    epub_subparser.add_argument("--markdown-parser-backend", choices=("yaet", "free_markdown_translator"))
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
    translate_epub.add_argument("--config")
    translate_epub.add_argument("--epub-parser-backend", choices=("yaet", "epub_translator"))
    translate_epub.add_argument("--markdown-parser-backend", choices=("yaet", "free_markdown_translator"))
    translate_epub.add_argument("--title")
    translate_epub.add_argument("--author")
    _add_shared_translate_args(translate_epub)

    subparsers.add_parser("translate", description="Translate short text or plain-text content.")

    return parser.parse_known_args(argv)


def _add_shared_translate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model")
    parser.add_argument("--max-chars-per-chunk", type=int)
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=None)


def _resolve_output_mode(args: argparse.Namespace) -> str:
    if getattr(args, "bilingual", False):
        return "bilingual"
    return "chinese"


def _translate_and_maybe_cleanup(markdown_path: Path, paths: pipeline.PipelinePaths, args: argparse.Namespace) -> Path:
    runtime_config = _runtime_config_from_args(args)
    translated_path = pipeline.translate_markdown_file(
        markdown_path,
        paths.bilingual_markdown_path,
        paths.cache_path,
        model=runtime_config.provider.model,
        max_chars_per_chunk=runtime_config.segmentation.max_bundle_chars,
        max_workers=runtime_config.translation.max_workers,
        resume=runtime_config.translation.resume,
        output_mode=_resolve_output_mode(args),
        markdown_parser_backend=runtime_config.parsers.markdown,
        provider_base_url=runtime_config.provider.base_url,
        provider_api_key=runtime_config.provider.api_key,
        provider_api_key_env=runtime_config.provider.api_key_env,
        prompt_config=runtime_config.prompt,
        style_config=runtime_config.style,
        glossary=runtime_config.glossary,
        cache_namespace=yaet_config.build_cache_namespace(runtime_config),
    )
    if _resolve_output_mode(args) == "bilingual":
        pipeline.cleanup_markdown_file(translated_path)
    return translated_path


def _runtime_config_from_args(args: argparse.Namespace) -> yaet_config.YaetConfig:
    config = yaet_config.load_config(getattr(args, "config", None))
    return yaet_config.apply_cli_overrides(
        config,
        model=getattr(args, "model", None),
        max_chars_per_chunk=getattr(args, "max_chars_per_chunk", None),
        max_workers=getattr(args, "max_workers", None),
        epub_parser_backend=getattr(args, "epub_parser_backend", None),
        markdown_parser_backend=getattr(args, "markdown_parser_backend", None),
        resume=getattr(args, "resume", None),
    )


def _prepare_markdown_input(input_path: Path, output_path: Path | None, paths: pipeline.PipelinePaths) -> Path:
    markdown_output = Path(output_path) if output_path else paths.markdown_path
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() != markdown_output.resolve():
        shutil.copyfile(input_path, markdown_output)
    return markdown_output


def _convert_source_with_backend(
    input_path: Path,
    output_path: Path,
    runtime_config: yaet_config.YaetConfig,
) -> Path:
    if runtime_config.parsers.epub == "yaet":
        return pipeline.convert_source_to_markdown(input_path, output_path)
    return pipeline.convert_source_to_markdown(
        input_path,
        output_path,
        epub_parser_backend=runtime_config.parsers.epub,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args, extra_args = parse_args(argv)

    if args.command == "translate":
        return text_cli.main(extra_args)

    input_path = Path(args.input_path)
    paths = pipeline.derive_output_paths(input_path)
    metadata = pipeline.read_input_metadata(input_path)
    runtime_config = _runtime_config_from_args(args)

    if args.command in {"pdf2md", "epub2md"}:
        markdown_output = Path(args.output_path) if args.output_path else paths.markdown_path
        markdown_path = _convert_source_with_backend(input_path, markdown_output, runtime_config)
        if not args.translate:
            return 0
        _translate_and_maybe_cleanup(markdown_path, paths, args)
        return 0

    if args.command == "md2md":
        markdown_path = _prepare_markdown_input(input_path, args.output_path, paths)
        if not args.translate:
            return 0
        _translate_and_maybe_cleanup(markdown_path, paths, args)
        return 0

    if args.command == "pdf2epub":
        markdown_path = _convert_source_with_backend(input_path, paths.markdown_path, runtime_config)
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
        markdown_path = _convert_source_with_backend(input_path, paths.markdown_path, runtime_config)
        bilingual_path = pipeline.translate_markdown_file(
            markdown_path,
            paths.bilingual_markdown_path,
            paths.cache_path,
            model=runtime_config.provider.model,
            max_chars_per_chunk=runtime_config.segmentation.max_bundle_chars,
            max_workers=runtime_config.translation.max_workers,
            resume=runtime_config.translation.resume,
            output_mode="bilingual",
            markdown_parser_backend=runtime_config.parsers.markdown,
            provider_base_url=runtime_config.provider.base_url,
            provider_api_key=runtime_config.provider.api_key,
            provider_api_key_env=runtime_config.provider.api_key_env,
            prompt_config=runtime_config.prompt,
            style_config=runtime_config.style,
            glossary=runtime_config.glossary,
            cache_namespace=yaet_config.build_cache_namespace(runtime_config),
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
