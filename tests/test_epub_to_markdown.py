from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

from ebooklib import epub

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import convert_epub_to_markdown as epub_to_markdown_module
from convert_epub_to_markdown import convert_epub_to_markdown


class EpubToMarkdownTests(unittest.TestCase):
    def test_main_defaults_output_to_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            input_path.write_bytes(b"epub")
            captured: dict[str, Path] = {}

            def fake_convert(input_value: Path, output_value: Path, asset_dir_name=None) -> None:
                captured["input"] = input_value
                captured["output"] = output_value

            with patch.object(epub_to_markdown_module, "convert_epub_to_markdown", side_effect=fake_convert):
                result = epub_to_markdown_module.main([str(input_path)])

        self.assertEqual(result, 0)
        self.assertEqual(captured["input"], input_path)
        self.assertEqual(captured["output"], tmp_path / "output" / "sample" / "sample.md")

    def test_convert_epub_to_markdown_creates_missing_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "output" / "sample.md"
            self._write_sample_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            self.assertTrue(output_path.exists())

    def test_convert_epub_to_markdown_uses_metadata_title_for_top_level_heading_and_toc(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_sample_epub(input_path, book_title="未来简史")

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("- [未来简史](#未来简史)", markdown)
            self.assertIn("# 未来简史", markdown)
            self.assertNotIn("- [Book Title](#book-title)", markdown)

    def test_convert_epub_to_markdown_preserves_hierarchy_and_generates_toc(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_sample_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("# Table of Contents", markdown)
            self.assertIn("- [Sample Book](#sample-book)", markdown)
            self.assertIn("- [Chapter One](#chapter-one)", markdown)
            self.assertIn("## Chapter One", markdown)
            self.assertIn("First paragraph with [a link](https://example.com).", markdown)
            self.assertIn("- First bullet", markdown)
            self.assertIn("> A thoughtful quote.", markdown)
            self.assertIn("```", markdown)

    def test_convert_epub_to_markdown_exports_images_to_asset_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_sample_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            asset_path = tmp_path / "sample_assets" / "pixel.png"
            self.assertTrue(asset_path.exists())
            self.assertIn("![](sample_assets/pixel.png)", markdown)

    def test_convert_epub_to_markdown_detects_cover_image_not_referenced_in_body(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_cover_only_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            asset_path = tmp_path / "sample_assets" / "cover.jpg"
            self.assertTrue(asset_path.exists())
            self.assertIn("![](sample_assets/cover.jpg)", markdown)

    def test_convert_epub_to_markdown_detects_svg_titlepage_cover_image(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_svg_cover_page_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            asset_path = tmp_path / "sample_assets" / "cover.jpeg"
            self.assertTrue(asset_path.exists())
            self.assertIn("![](sample_assets/cover.jpeg)", markdown)

    def test_convert_epub_to_markdown_renders_note_links_as_references(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_sample_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("Paragraph with a citation[39][notes.xhtml#notes39n].", markdown)
            self.assertIn("[notes.xhtml#notes39n]: 39. Detailed citation explanation.", markdown)

    def test_convert_epub_to_markdown_promotes_title_class_blocks_to_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_title_class_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("- [Part I](#part-i)", markdown)
            self.assertIn("  - [Section 1](#section-1)", markdown)
            self.assertIn("    - [Subsection A](#subsection-a)", markdown)
            self.assertIn("## Part I", markdown)
            self.assertIn("### Section 1", markdown)
            self.assertIn("##### Subsection A", markdown)
            self.assertIn("Body paragraph.", markdown)

    def test_convert_epub_to_markdown_descends_into_span_wrappers_with_block_children(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_title_class_epub(input_path, wrap_in_span=True)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("## Part I", markdown)
            self.assertIn("### Section 1", markdown)
            self.assertIn("Body paragraph.", markdown)

    def test_convert_epub_to_markdown_prefers_epub_toc_hierarchy_over_title_classes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_toc_driven_title_class_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("## Part I", markdown)
            self.assertIn("## Part II", markdown)
            self.assertIn("### Section 1", markdown)
            self.assertIn("### Section 2", markdown)
            self.assertNotIn("### Part II", markdown)
            self.assertIn("- [Part I](#part-i)", markdown)
            self.assertIn("- [Part II](#part-ii)", markdown)
            self.assertIn("  - [Section 1](#section-1)", markdown)
            self.assertIn("  - [Section 2](#section-2)", markdown)

    def test_convert_epub_to_markdown_recovers_nested_span_sections_after_separator(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_nested_span_section_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("## Section 3.2", markdown)
            self.assertIn("### Subtopic", markdown)
            self.assertIn("∞∞∞∞∞", markdown)
            self.assertIn("Details continue here.", markdown)

    def test_convert_epub_to_markdown_strips_punctuation_only_emphasis_in_headings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_heading_punctuation_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("### §2-2. Attachments and Goals", markdown)
            self.assertNotIn("§2-2**.**Attachments and Goals", markdown)
            self.assertIn("  - [§2-2. Attachments and Goals](#2-2-attachments-and-goals)", markdown)

    def test_convert_epub_to_markdown_strips_punctuation_only_emphasis_in_paragraphs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.epub"
            output_path = tmp_path / "sample.md"
            self._write_inline_punctuation_epub(input_path)

            convert_epub_to_markdown(input_path, output_path)

            markdown = output_path.read_text(encoding="utf-8")
            self.assertIn("Sentence one. Sentence two.", markdown)
            self.assertNotIn("Sentence one**.**Sentence two.", markdown)

    def _write_sample_epub(self, output_path: Path, book_title: str = "Sample Book") -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title(book_title)
        book.set_language("en")
        book.add_author("Test Author")

        image = epub.EpubItem(
            uid="pixel",
            file_name="images/pixel.png",
            media_type="image/png",
            content=(
                b"\x89PNG\r\n\x1a\n"
                b"\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
                b"\x90wS\xde"
                b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
                b"\x0b\xe7\x02\x9d"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            ),
        )
        book.add_item(image)

        chapter = epub.EpubHtml(title="Chapter One", file_name="text/chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <h1>Book Title</h1>
            <h2>Chapter One</h2>
            <p>First paragraph with <a href="https://example.com">a link</a>.</p>
            <p>Paragraph with a citation<a href="../notes.xhtml#notes39n">39</a>.</p>
            <ul><li>First bullet</li><li>Second bullet</li></ul>
            <blockquote><p>A thoughtful quote.</p></blockquote>
            <pre><code>print("hi")</code></pre>
            <p><img src="../images/pixel.png" alt="" /></p>
          </body>
        </html>
        """

        book.add_item(chapter)
        notes = epub.EpubHtml(title="Notes", file_name="notes.xhtml", lang="en")
        notes.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <h1>Notes</h1>
            <p><a id="notes39n" href="text/chapter1.xhtml#notes39">39</a>. Detailed citation explanation.</p>
          </body>
        </html>
        """
        book.add_item(notes)
        book.toc = (chapter,)
        book.spine = ["nav", chapter, notes]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_cover_only_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("cover-book")
        book.set_title("Cover Book")
        book.set_language("en")
        book.add_author("Cover Author")

        cover = epub.EpubItem(
            uid="cover",
            file_name="cover.jpg",
            media_type="image/jpeg",
            content=b"jpeg-bytes",
        )
        book.add_item(cover)

        chapter = epub.EpubHtml(title="Chapter One", file_name="chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <h1>Chapter One</h1>
            <p>Body paragraph.</p>
          </body>
        </html>
        """
        book.add_item(chapter)
        book.toc = (chapter,)
        book.spine = ["nav", chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_svg_cover_page_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("svg-cover-book")
        book.set_title("SVG Cover Book")
        book.set_language("en")
        book.add_author("Cover Author")

        cover = epub.EpubItem(
            uid="cover",
            file_name="cover.jpeg",
            media_type="image/jpeg",
            content=b"jpeg-bytes",
        )
        book.add_item(cover)

        titlepage = epub.EpubHtml(title="Cover", file_name="titlepage.xhtml", lang="en")
        titlepage.content = """
        <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
          <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
            <meta name="calibre:cover" content="true"/>
            <title>Cover</title>
          </head>
          <body>
            <div>
              <svg xmlns="http://www.w3.org/2000/svg"
                   xmlns:xlink="http://www.w3.org/1999/xlink"
                   version="1.1"
                   width="100%"
                   height="100%"
                   viewBox="0 0 925 1388"
                   preserveAspectRatio="none">
                <image width="925" height="1388" xlink:href="cover.jpeg"/>
              </svg>
            </div>
          </body>
        </html>
        """
        book.add_item(titlepage)

        chapter = epub.EpubHtml(title="Chapter One", file_name="chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <h1>Chapter One</h1>
            <p>Body paragraph.</p>
          </body>
        </html>
        """
        book.add_item(chapter)
        book.toc = (chapter,)
        book.spine = ["nav", titlepage, chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_title_class_epub(self, output_path: Path, wrap_in_span: bool = False) -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title("Sample Book")
        book.set_language("en")
        book.add_author("Test Author")

        body = """
            <div class="title1"><p class="p">Part I</p></div>
            <div class="title2"><p class="p">Section 1</p></div>
            <div class="title4"><p class="p">Subsection A</p></div>
            <p>Body paragraph.</p>
        """
        if wrap_in_span:
            body = f'<span id="id1">{body}</span>'

        chapter = epub.EpubHtml(title="Part I", file_name="text/chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            {body}
          </body>
        </html>
        """.format(body=body)

        book.add_item(chapter)
        book.toc = (chapter,)
        book.spine = ["nav", chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_toc_driven_title_class_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title("Sample Book")
        book.set_language("en")
        book.add_author("Test Author")

        chapter1 = epub.EpubHtml(title="Part I", file_name="text/chapter1.xhtml", lang="en")
        chapter1.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <span id="part1">
              <div class="title1"><p class="p">Part I</p></div>
            </span>
            <span id="section1">
              <div class="title2"><p class="p">Section 1</p></div>
            </span>
            <p>Body 1.</p>
          </body>
        </html>
        """

        chapter2 = epub.EpubHtml(title="Part II", file_name="text/chapter2.xhtml", lang="en")
        chapter2.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <span id="part2">
              <div class="title2"><p class="p">Part II</p></div>
            </span>
            <span id="section2">
              <div class="title3"><p class="p">Section 2</p></div>
            </span>
            <p>Body 2.</p>
          </body>
        </html>
        """

        book.add_item(chapter1)
        book.add_item(chapter2)
        book.toc = (
            (epub.Section("Part I", "text/chapter1.xhtml#part1"), [epub.Link("text/chapter1.xhtml#section1", "Section 1", "section1")]),
            (epub.Section("Part II", "text/chapter2.xhtml#part2"), [epub.Link("text/chapter2.xhtml#section2", "Section 2", "section2")]),
        )
        book.spine = ["nav", chapter1, chapter2]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_nested_span_section_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title("Sample Book")
        book.set_language("en")
        book.add_author("Test Author")

        chapter = epub.EpubHtml(title="Section 3.2", file_name="text/chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <span>
              <span id="section32">
                <div class="title4"><p class="p">Section 3.2</p></div>
                <span>
                  <p>Lead paragraph.</p>
                  <p class="subtitle">∞∞∞∞∞</p>
                </span>
                <span id="subtopic">
                  <div class="title5"><p class="p">Subtopic</p></div>
                  <p>Details continue here.</p>
                </span>
              </span>
            </span>
          </body>
        </html>
        """

        book.add_item(chapter)
        book.toc = (
            (
                epub.Section("Section 3.2", "text/chapter1.xhtml#section32"),
                [epub.Link("text/chapter1.xhtml#subtopic", "Subtopic", "subtopic")],
            ),
        )
        book.spine = ["nav", chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_heading_punctuation_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title("Sample Book")
        book.set_language("en")
        book.add_author("Test Author")

        chapter = epub.EpubHtml(title="Part I", file_name="text/chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <span id="part1">
              <div class="title1"><p class="p">Part I</p></div>
            </span>
            <span id="section22">
              <div class="title2"><p class="p">§2-2<strong>. </strong>Attachments and Goals</p></div>
            </span>
            <p>Body text.</p>
          </body>
        </html>
        """

        book.add_item(chapter)
        book.toc = (
            (
                epub.Section("Part I", "text/chapter1.xhtml#part1"),
                [epub.Link("text/chapter1.xhtml#section22", "§2-2. Attachments and Goals", "section22")],
            ),
        )
        book.spine = ["nav", chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)

    def _write_inline_punctuation_epub(self, output_path: Path) -> None:
        book = epub.EpubBook()
        book.set_identifier("sample-book")
        book.set_title("Sample Book")
        book.set_language("en")
        book.add_author("Test Author")

        chapter = epub.EpubHtml(title="Chapter One", file_name="text/chapter1.xhtml", lang="en")
        chapter.content = """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <h2>Chapter One</h2>
            <p>Sentence one<strong>. </strong>Sentence two.</p>
          </body>
        </html>
        """

        book.add_item(chapter)
        book.toc = (chapter,)
        book.spine = ["nav", chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        epub.write_epub(str(output_path), book)


if __name__ == "__main__":
    unittest.main()
