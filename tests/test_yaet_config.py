from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from yaet_config import load_config, resolve_config_path


class YaetConfigTests(unittest.TestCase):
    def test_resolve_config_path_prefers_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "custom.yaml"
            config_path.write_text("provider:\n  model: custom\n", encoding="utf-8")

            self.assertEqual(resolve_config_path(str(config_path)), config_path)

    def test_load_config_parses_nested_yaml_and_glossary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "yaet.yaml"
            config_path.write_text(
                (
                    "parsers:\n"
                    "  epub: epub_translator\n"
                    "  markdown: free_markdown_translator\n"
                    "provider:\n"
                    "  model: custom-model\n"
                    "style:\n"
                    "  tone: literary\n"
                    "  audience: researchers\n"
                    "  preserve_terms:\n"
                    "    - Markdown\n"
                    "    - EPUB\n"
                    "  instructions:\n"
                    "    - Keep citations stable.\n"
                    "prompt:\n"
                    "  title: The Book Title\n"
                    "  summary: A short summary.\n"
                    "  terms: Prefer established terminology.\n"
                    "glossary:\n"
                    "  agent: 智能体\n"
                    "  model: 模型\n"
                ),
                encoding="utf-8",
            )

            config = load_config(str(config_path))

        self.assertEqual(config.parsers.epub, "epub_translator")
        self.assertEqual(config.parsers.markdown, "free_markdown_translator")
        self.assertEqual(config.provider.model, "custom-model")
        self.assertEqual(config.style.tone, "literary")
        self.assertEqual(config.style.audience, "researchers")
        self.assertEqual(config.style.preserve_terms, ["Markdown", "EPUB"])
        self.assertEqual(config.style.instructions, ["Keep citations stable."])
        self.assertEqual(config.prompt.title, "The Book Title")
        self.assertEqual(config.prompt.summary, "A short summary.")
        self.assertEqual(config.prompt.terms, "Prefer established terminology.")
        self.assertEqual(config.glossary["agent"], "智能体")
        self.assertEqual(config.glossary["model"], "模型")


if __name__ == "__main__":
    unittest.main()
