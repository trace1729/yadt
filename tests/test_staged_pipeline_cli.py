from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SCRIPT_PATH = SRC_DIR / "yaet_cli.py"
WRAPPER_PATH = PROJECT_ROOT / "yaet"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError("yaet_cli.py is missing")

    spec = importlib.util.spec_from_file_location("yaet_cli", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load yaet_cli.py")

    module = importlib.util.module_from_spec(spec)
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StagedPipelineCliTests(unittest.TestCase):
    def test_wrapper_script_exists(self):
        self.assertTrue(WRAPPER_PATH.exists())

    def test_wrapper_script_resolves_repo_root_when_invoked_via_symlink(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            symlink_path = tmp_path / "yaet"
            symlink_path.symlink_to(WRAPPER_PATH)

            result = subprocess.run(
                [str(symlink_path), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("pdf2md", result.stdout)

    def test_pdf2md_without_translation_only_converts_pdf(self):
        module = load_module()
        events: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "paper.pdf"
            input_path.write_bytes(b"%PDF-1.4\n")

            def fake_convert_source_to_markdown(input_value, output_path=None):
                events.append("convert")
                output = output_path or module.pipeline.derive_output_paths(input_value).markdown_path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("# Paper\n", encoding="utf-8")
                return output

            with patch.object(module.pipeline, "convert_source_to_markdown", side_effect=fake_convert_source_to_markdown), patch.object(
                module.pipeline, "translate_markdown_file"
            ) as translate_mock, patch.object(module.pipeline, "cleanup_markdown_file") as cleanup_mock:
                exit_code = module.main(["pdf2md", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert"])
        translate_mock.assert_not_called()
        cleanup_mock.assert_not_called()

    def test_pdf2md_with_translate_bilingual_runs_translation_and_cleanup(self):
        module = load_module()
        events: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "paper.pdf"
            input_path.write_bytes(b"%PDF-1.4\n")
            paths = module.pipeline.derive_output_paths(input_path)

            def fake_convert_source_to_markdown(input_value, output_path=None):
                events.append("convert")
                paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
                paths.markdown_path.write_text("# Paper\n", encoding="utf-8")
                return paths.markdown_path

            def fake_translate_markdown_file(input_value, output_path, cache_path, **kwargs):
                events.append("translate")
                output_path.write_text("# Paper\n\n# 论文\n", encoding="utf-8")
                cache_path.write_text("{}", encoding="utf-8")
                return output_path

            def fake_cleanup_markdown_file(path):
                events.append("cleanup")
                path.write_text("# Paper (论文)\n", encoding="utf-8")
                return path

            with patch.object(module.pipeline, "convert_source_to_markdown", side_effect=fake_convert_source_to_markdown), patch.object(
                module.pipeline, "translate_markdown_file", side_effect=fake_translate_markdown_file
            ), patch.object(module.pipeline, "cleanup_markdown_file", side_effect=fake_cleanup_markdown_file):
                exit_code = module.main(["pdf2md", str(input_path), "--translate", "--bilingual"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert", "translate", "cleanup"])

    def test_md2md_without_translation_copies_markdown_to_output_location(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "notes.md"
            input_path.write_text("# Notes\n\nHello.\n", encoding="utf-8")
            output_path = module.pipeline.derive_output_paths(input_path).markdown_path

            with patch.object(module.pipeline, "translate_markdown_file") as translate_mock, patch.object(
                module.pipeline, "cleanup_markdown_file"
            ) as cleanup_mock:
                exit_code = module.main(["md2md", str(input_path)])

            self.assertEqual(output_path.read_text(encoding="utf-8"), "# Notes\n\nHello.\n")

        self.assertEqual(exit_code, 0)
        translate_mock.assert_not_called()
        cleanup_mock.assert_not_called()

    def test_md2md_with_translate_bilingual_runs_translation_and_cleanup(self):
        module = load_module()
        events: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "notes.md"
            input_path.write_text("# Notes\n\nHello.\n", encoding="utf-8")
            paths = module.pipeline.derive_output_paths(input_path)

            def fake_translate_markdown_file(input_value, output_path, cache_path, **kwargs):
                events.append("translate")
                self.assertEqual(input_value, paths.markdown_path)
                self.assertEqual(input_value.read_text(encoding="utf-8"), "# Notes\n\nHello.\n")
                output_path.write_text("# Notes\n\n# 笔记\n", encoding="utf-8")
                cache_path.write_text("{}", encoding="utf-8")
                return output_path

            def fake_cleanup_markdown_file(path):
                events.append("cleanup")
                path.write_text("# Notes (笔记)\n", encoding="utf-8")
                return path

            with patch.object(module.pipeline, "translate_markdown_file", side_effect=fake_translate_markdown_file), patch.object(
                module.pipeline, "cleanup_markdown_file", side_effect=fake_cleanup_markdown_file
            ):
                exit_code = module.main(["md2md", str(input_path), "--translate", "--bilingual"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["translate", "cleanup"])

    def test_epub2epub_produces_bilingual_epub(self):
        module = load_module()
        events: list[str] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "book.epub"
            input_path.write_bytes(b"epub")
            paths = module.pipeline.derive_output_paths(input_path)

            def fake_convert_source_to_markdown(input_value, output_path=None):
                events.append("convert")
                paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
                paths.markdown_path.write_text("# Book\n", encoding="utf-8")
                return paths.markdown_path

            def fake_translate_markdown_file(input_value, output_path, cache_path, **kwargs):
                events.append("translate")
                output_path.write_text("# Book\n\n# 书\n", encoding="utf-8")
                cache_path.write_text("{}", encoding="utf-8")
                return output_path

            def fake_cleanup_markdown_file(path):
                events.append("cleanup")
                path.write_text("# Book (书)\n", encoding="utf-8")
                return path

            def fake_export_markdown_to_epub(input_value, output_path, title, author):
                events.append("epub")
                output_path.write_bytes(b"epub")
                return output_path

            with patch.object(module.pipeline, "convert_source_to_markdown", side_effect=fake_convert_source_to_markdown), patch.object(
                module.pipeline,
                "read_input_metadata",
                return_value=module.pipeline.BookMetadata(
                    title="Book",
                    author="Author",
                    bilingual_title="Book (Bilingual)",
                ),
            ), patch.object(
                module.pipeline, "translate_markdown_file", side_effect=fake_translate_markdown_file
            ), patch.object(module.pipeline, "cleanup_markdown_file", side_effect=fake_cleanup_markdown_file), patch.object(
                module.pipeline, "export_markdown_to_epub", side_effect=fake_export_markdown_to_epub
            ):
                exit_code = module.main(["epub2epub", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert", "translate", "cleanup", "epub"])

    def test_epub2md_reads_config_and_forwards_backend_selection(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "book.epub"
            input_path.write_bytes(b"epub")
            paths = module.pipeline.derive_output_paths(input_path)

            config = module.yaet_config.YaetConfig(
                parsers=module.yaet_config.ParserConfig(epub="epub_translator", markdown="free_markdown_translator"),
                provider=module.yaet_config.ProviderConfig(model="cfg-model"),
                prompt=module.yaet_config.PromptConfig(),
                style=module.yaet_config.StyleConfig(),
                segmentation=module.yaet_config.SegmentationConfig(max_bundle_chars=4321),
                translation=module.yaet_config.TranslationConfig(max_workers=7),
                glossary={},
            )

            def fake_convert_source_to_markdown(input_value, output_path=None, epub_parser_backend="yaet"):
                self.assertEqual(epub_parser_backend, "epub_translator")
                output = output_path or paths.markdown_path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("# Book\n", encoding="utf-8")
                return output

            def fake_translate_markdown_file(input_value, output_path, cache_path, **kwargs):
                self.assertEqual(kwargs["markdown_parser_backend"], "free_markdown_translator")
                self.assertEqual(kwargs["model"], "cfg-model")
                self.assertEqual(kwargs["max_chars_per_chunk"], 4321)
                self.assertEqual(kwargs["max_workers"], 7)
                output_path.write_text("# Book\n\n# 书\n", encoding="utf-8")
                cache_path.write_text("{}", encoding="utf-8")
                return output_path

            with patch.object(module.yaet_config, "load_config", return_value=config), patch.object(
                module.pipeline, "convert_source_to_markdown", side_effect=fake_convert_source_to_markdown
            ), patch.object(
                module.pipeline, "read_input_metadata",
                return_value=module.pipeline.BookMetadata(title="Book", author="Author", bilingual_title="Book (Bilingual)")
            ), patch.object(
                module.pipeline, "translate_markdown_file", side_effect=fake_translate_markdown_file
            ), patch.object(module.pipeline, "cleanup_markdown_file", return_value=paths.bilingual_markdown_path):
                exit_code = module.main(["epub2md", str(input_path), "--translate", "--bilingual", "--config", "yaet.yaml"])

        self.assertEqual(exit_code, 0)

    def test_translate_subcommand_delegates_to_translate_text_cli(self):
        module = load_module()

        with patch.object(module.text_cli, "main", return_value=0) as text_main:
            exit_code = module.main(["translate", "Hello world"])

        self.assertEqual(exit_code, 0)
        text_main.assert_called_once_with(["Hello world"])

    def test_translate_subcommand_forwards_bilingual_flags(self):
        module = load_module()

        with patch.object(module.text_cli, "main", return_value=0) as text_main:
            exit_code = module.main(["translate", "--bilingual", "--input", "notes.txt", "--output", "notes.bilingual.txt"])

        self.assertEqual(exit_code, 0)
        text_main.assert_called_once_with(["--bilingual", "--input", "notes.txt", "--output", "notes.bilingual.txt"])


if __name__ == "__main__":
    unittest.main()
