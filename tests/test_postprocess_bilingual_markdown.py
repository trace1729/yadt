from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "cleanup_bilingual_markdown.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError("cleanup_bilingual_markdown.py is missing")

    spec = importlib.util.spec_from_file_location("cleanup_bilingual_markdown", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load cleanup_bilingual_markdown.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PostprocessBilingualMarkdownTests(unittest.TestCase):
    def test_postprocess_updates_reference_style_link_titles(self):
        module = load_module()
        source = (
            "See [§1-2. The Sea Of Mental Mysteries][sec-1-2].\n\n"
            "[sec-1-2]: #1-2-the-sea-of-mental-mysteries\n\n"
            "### §1-2. The Sea Of Mental Mysteries\n\n"
            "### §1-2. 心智奥秘之海\n"
        )

        output = module.postprocess_markdown(source)

        self.assertIn(
            "See [§1-2. The Sea Of Mental Mysteries (心智奥秘之海)][sec-1-2].",
            output,
        )
        self.assertNotIn("See [§1-2. The Sea Of Mental Mysteries][sec-1-2].", output)

    def test_postprocess_updates_toc_items_to_match_merged_bilingual_headings(self):
        module = load_module()
        source = (
            "# Table of Contents\n\n"
            "- [§1-2. The Sea Of Mental Mysteries](#1-2-the-sea-of-mental-mysteries)\n\n"
            "### §1-2. The Sea Of Mental Mysteries\n\n"
            "### §1-2. 心智奥秘之海\n\n"
            "Body paragraph.\n"
        )

        output = module.postprocess_markdown(source)

        self.assertIn("# Table of Contents", output)
        self.assertIn(
            "- [§1-2. The Sea Of Mental Mysteries (心智奥秘之海)](#1-2-the-sea-of-mental-mysteries)",
            output,
        )
        self.assertNotIn("- [§1-2. The Sea Of Mental Mysteries](#1-2-the-sea-of-mental-mysteries)", output)

    def test_postprocess_merges_adjacent_bilingual_headings(self):
        module = load_module()
        source = (
            "### §1-2. The Sea Of Mental Mysteries\n\n"
            "### §1-2. 心智奥秘之海\n\n"
            "Body paragraph.\n"
        )

        output = module.postprocess_markdown(source)

        self.assertIn("### §1-2. The Sea Of Mental Mysteries (心智奥秘之海)", output)
        self.assertNotIn("### §1-2. 心智奥秘之海", output)

    def test_postprocess_removes_duplicate_images_and_separators(self):
        module = load_module()
        source = (
            "English paragraph.\n\n"
            "中文段落。\n\n"
            "![](emotion_machine_assets/i_001.png)\n\n"
            "![](emotion_machine_assets/i_001.png)\n\n"
            "∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞\n\n"
            "∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞\n\n"
            "Next paragraph.\n"
        )

        output = module.postprocess_markdown(source)

        self.assertEqual(output.count("![](emotion_machine_assets/i_001.png)"), 1)
        self.assertNotIn("∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞∞", output)
        self.assertIn("Next paragraph.", output)

    def test_postprocess_removes_duplicate_images_with_parentheses_in_paths(self):
        module = load_module()
        source = (
            "![](The_Paper_Menagerie_and_Oth_(Z-Library)_assets/cover.jpeg)\n\n"
            "![](The_Paper_Menagerie_and_Oth_(Z-Library)_assets/cover.jpeg)\n\n"
            "Next paragraph.\n"
        )

        output = module.postprocess_markdown(source)

        self.assertEqual(
            output.count("![](The_Paper_Menagerie_and_Oth_(Z-Library)_assets/cover.jpeg)"),
            1,
        )
        self.assertIn("Next paragraph.", output)

    def test_cli_writes_processed_output_file(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.md"
            output_path = tmp_path / "output.md"
            input_path.write_text(
                "# Title\n\n# 标题\n\n![](a.png)\n\n![](a.png)\n\n",
                encoding="utf-8",
            )

            result = module.main([str(input_path), "-o", str(output_path)])

            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())
            output = output_path.read_text(encoding="utf-8")
            self.assertIn("# Title (标题)", output)
            self.assertEqual(output.count("![](a.png)"), 1)


if __name__ == "__main__":
    unittest.main()
