from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "fix_special_toc_links.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError("fix_special_toc_links.py is missing")

    spec = importlib.util.spec_from_file_location("fix_special_toc_links", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load fix_special_toc_links.py")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FixSpecialTocHeadingsTests(unittest.TestCase):
    def test_does_not_rewrite_top_level_book_title_heading(self):
        module = load_module()
        source = (
            "# Table of Contents\n\n"
            "- [The Paper Menagerie and Other Stories](#the-paper-menagerie-and-other-stories)\n\n"
            "# The Paper Menagerie and Other Stories\n\n"
            "Body.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn("# The Paper Menagerie and Other Stories", output)
        self.assertNotIn("## the-paper-menagerie-and-other-stories", output)

    def test_promotes_matching_body_line_to_internal_ref_heading(self):
        module = load_module()
        source = (
            "# Table of Contents\n\n"
            "[STATE CHANGE](#STATE_CHANGE)\n\n"
            "Some intro.\n\n"
            "STATE CHANGE\n\n"
            "Body paragraph.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn("[STATE CHANGE](#STATE_CHANGE)", output)
        self.assertIn("## STATE_CHANGE", output)
        self.assertNotIn("\nSTATE CHANGE\n", output)

    def test_keeps_toc_display_text_while_matching_body_heading_to_ref(self):
        module = load_module()
        source = (
            "CONTENTS\n\n"
            "[STATE CHANGE](#STATE_CHANGE)\n\n"
            "STATE CHANGE\n\n"
            "More text.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn("[STATE CHANGE](#STATE_CHANGE)", output)
        self.assertIn("## STATE_CHANGE", output)
        self.assertNotIn("## STATE CHANGE", output)

    def test_rewrites_external_toc_link_to_internal_underscore_anchor_and_promotes_body_heading(self):
        module = load_module()
        source = (
            "CONTENTS\n\n"
            "[THE BOOKMAKING HABITS OF SELECT SPECIES](index_split_006.html#filepos10209)\n\n"
            "THE BOOKMAKING HABITS OF SELECT SPECIES\n\n"
            "Story body.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn(
            "[THE BOOKMAKING HABITS OF SELECT SPECIES](#THE_BOOKMAKING_HABITS_OF_SELECT_SPECIES)",
            output,
        )
        self.assertIn("## THE_BOOKMAKING_HABITS_OF_SELECT_SPECIES", output)
        self.assertNotIn("index_split_006.html#filepos10209", output)
        self.assertNotIn("\nTHE BOOKMAKING HABITS OF SELECT SPECIES\n", output)

    def test_does_not_rewrite_normal_title_case_heading(self):
        module = load_module()
        source = (
            "CONTENTS\n\n"
            "[The Perfect Match](#The_Perfect_Match)\n\n"
            "The Perfect Match\n\n"
            "Story body.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn("[The Perfect Match](#The_Perfect_Match)", output)
        self.assertIn("\nThe Perfect Match\n", output)
        self.assertNotIn("## The_Perfect_Match", output)

    def test_does_not_rewrite_overlong_all_caps_heading(self):
        module = load_module()
        source = (
            "CONTENTS\n\n"
            "[THIS IS A VERY LONG ALL CAPS TITLE THAT SHOULD NOT BE REWRITTEN](#THIS_IS_A_VERY_LONG_ALL_CAPS_TITLE_THAT_SHOULD_NOT_BE_REWRITTEN)\n\n"
            "THIS IS A VERY LONG ALL CAPS TITLE THAT SHOULD NOT BE REWRITTEN\n\n"
            "Story body.\n"
        )

        output = module.fix_special_toc_headings(source)

        self.assertIn(
            "[THIS IS A VERY LONG ALL CAPS TITLE THAT SHOULD NOT BE REWRITTEN](#THIS_IS_A_VERY_LONG_ALL_CAPS_TITLE_THAT_SHOULD_NOT_BE_REWRITTEN)",
            output,
        )
        self.assertIn("\nTHIS IS A VERY LONG ALL CAPS TITLE THAT SHOULD NOT BE REWRITTEN\n", output)
        self.assertNotIn("## THIS_IS_A_VERY_LONG_ALL_CAPS_TITLE_THAT_SHOULD_NOT_BE_REWRITTEN", output)

    def test_cli_rewrites_file_in_place(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.md"
            input_path.write_text(
                "[STATE CHANGE](#STATE_CHANGE)\n\nSTATE CHANGE\n",
                encoding="utf-8",
            )

            result = module.main([str(input_path)])

            self.assertEqual(result, 0)
            output = input_path.read_text(encoding="utf-8")
            self.assertIn("## STATE_CHANGE", output)


if __name__ == "__main__":
    unittest.main()
