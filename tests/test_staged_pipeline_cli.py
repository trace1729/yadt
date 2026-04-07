from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SCRIPT_PATH = SRC_DIR / "staged_pipeline_cli.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError("staged_pipeline_cli.py is missing")

    spec = importlib.util.spec_from_file_location("staged_pipeline_cli", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load staged_pipeline_cli.py")

    module = importlib.util.module_from_spec(spec)
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StagedPipelineCliTests(unittest.TestCase):
    def test_pdf2markdown_without_translation_only_converts_pdf(self):
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
                exit_code = module.main(["pdf2markdown", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert"])
        translate_mock.assert_not_called()
        cleanup_mock.assert_not_called()

    def test_pdf2markdown_with_translate_bilingual_runs_translation_and_cleanup(self):
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
                exit_code = module.main(["pdf2markdown", str(input_path), "--translate", "--bilingual"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert", "translate", "cleanup"])

    def test_translate_epub_produces_bilingual_epub(self):
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
                exit_code = module.main(["translate_epub", str(input_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["convert", "translate", "cleanup", "epub"])


if __name__ == "__main__":
    unittest.main()
