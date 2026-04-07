from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SCRIPT_PATH = SRC_DIR / "convert_pdf_to_markdown.py"


def load_module():
    if not SCRIPT_PATH.exists():
        raise AssertionError("convert_pdf_to_markdown.py is missing")

    spec = importlib.util.spec_from_file_location("convert_pdf_to_markdown", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load convert_pdf_to_markdown.py")

    module = importlib.util.module_from_spec(spec)
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PdfToMarkdownTests(unittest.TestCase):
    def test_load_mineru_api_key_falls_back_to_dotenv(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text('MINERU_API_KEY="mineru-key"\n', encoding="utf-8")

            with patch.dict(module.os.environ, {}, clear=True):
                self.assertEqual(module.load_mineru_api_key(env_path), "mineru-key")

    def test_load_mineru_api_key_falls_back_to_repo_dotenv_when_cwd_differs(self):
        module = load_module()
        repo_env_path = PROJECT_ROOT / ".env"
        original_content = repo_env_path.read_text(encoding="utf-8") if repo_env_path.exists() else None

        with tempfile.TemporaryDirectory() as tmp_dir:
            previous_cwd = Path.cwd()
            previous = os.environ.pop("MINERU_API_KEY", None)
            try:
                repo_env_path.write_text('MINERU_API_KEY="repo-mineru-key"\n', encoding="utf-8")
                os.chdir(tmp_dir)
                self.assertEqual(module.load_mineru_api_key(), "repo-mineru-key")
            finally:
                os.chdir(previous_cwd)
                if original_content is None:
                    repo_env_path.unlink(missing_ok=True)
                else:
                    repo_env_path.write_text(original_content, encoding="utf-8")
                if previous is not None:
                    os.environ["MINERU_API_KEY"] = previous

    def test_convert_pdf_to_markdown_downloads_zip_assets_and_rewrites_markdown_paths(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "paper.pdf"
            output_path = tmp_path / "output" / "paper.md"
            input_path.write_bytes(b"%PDF-1.4\n")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as archive:
                archive.writestr("result.md", "# Title\n\n![](images/figure1.png)\n")
                archive.writestr("images/figure1.png", b"png-bytes")

            def fake_post(url, headers=None, json=None, timeout=None):
                if url.endswith("/file-urls/batch"):
                    self.assertEqual(headers["Authorization"], "Bearer mineru-key")
                    self.assertEqual(json["files"][0]["name"], "paper.pdf")
                    return Mock(
                        status_code=200,
                        json=lambda: {
                            "code": 0,
                            "data": {
                                "batch_id": "batch-1",
                                "file_urls": ["https://upload.example.com/file"],
                            },
                        },
                        text="ok",
                    )
                if url.endswith("/extract-results/batch/batch-1"):
                    return Mock(
                        status_code=200,
                        json=lambda: {
                            "code": 0,
                            "data": {
                                "extract_result": [
                                    {
                                        "data_id": "paper",
                                        "state": "done",
                                        "full_zip_url": "https://download.example.com/result.zip",
                                    }
                                ]
                            },
                        },
                        text="ok",
                    )
                raise AssertionError(f"unexpected POST/GET URL: {url}")

            def fake_get(url, headers=None, timeout=None, proxies=None):
                if url.endswith("/extract-results/batch/batch-1"):
                    return fake_post(url, headers=headers, timeout=timeout)
                if url == "https://download.example.com/result.zip":
                    return Mock(status_code=200, content=zip_buffer.getvalue())
                raise AssertionError(f"unexpected GET URL: {url}")

            def fake_put(url, data=None, timeout=None):
                self.assertEqual(url, "https://upload.example.com/file")
                self.assertIsNotNone(data)
                return Mock(status_code=200)

            with patch.object(module.requests, "post", side_effect=fake_post), patch.object(
                module.requests, "get", side_effect=fake_get
            ), patch.object(module.requests, "put", side_effect=fake_put), patch.object(
                module.time, "sleep", return_value=None
            ):
                module.convert_pdf_to_markdown(
                    input_path,
                    output_path,
                    api_key="mineru-key",
                    poll_interval=0,
                    timeout=1,
                )

            markdown = output_path.read_text(encoding="utf-8")
            asset_path = output_path.with_name("paper_assets") / "figure1.png"
            self.assertTrue(asset_path.exists())
            self.assertIn("![](paper_assets/figure1.png)", markdown)


if __name__ == "__main__":
    unittest.main()
