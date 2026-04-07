from __future__ import annotations

import argparse
import io
import os
import re
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

try:
    import requests
except ImportError:
    requests = SimpleNamespace(post=None, get=None, put=None)

from output_paths import book_output_dir, canonical_book_name, sanitize_book_dir_name


CLOUD_API_URL = "https://mineru.net/api/v4"
DEFAULT_MODEL_VERSION = "pipeline"
DEFAULT_LANGUAGE = "ch"
DEFAULT_TIMEOUT = 600
DEFAULT_POLL_INTERVAL = 5
IMAGE_REFERENCE_PATTERN = re.compile(r"(!\[[^\]]*\]\()images/([^)]+)\)")


def load_mineru_api_key(env_path: Path | None = None) -> str | None:
    api_key = os.environ.get("MINERU_API_KEY")
    if api_key:
        return api_key

    dotenv_path = env_path or Path(".env")
    if not dotenv_path.exists():
        return None

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != "MINERU_API_KEY":
            continue
        cleaned = value.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    return None


def convert_pdf_to_markdown(
    input_path: Path,
    output_path: Path,
    *,
    api_key: str,
    cloud_url: str = CLOUD_API_URL,
    model_version: str = DEFAULT_MODEL_VERSION,
    language: str = DEFAULT_LANGUAGE,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
) -> None:
    _ensure_requests_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data_id = input_path.stem
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "files": [{"name": input_path.name, "data_id": data_id}],
        "model_version": model_version,
        "enable_formula": True,
        "enable_table": True,
        "language": language,
    }

    response = requests.post(f"{cloud_url}/file-urls/batch", headers=headers, json=payload, timeout=30)
    response_data = _json_or_raise(response, "MinerU upload-url request failed")
    file_urls = response_data.get("data", {}).get("file_urls", [])
    batch_id = response_data.get("data", {}).get("batch_id", "")
    if not batch_id or not file_urls:
        raise RuntimeError("MinerU cloud response did not include batch_id or upload URL")

    upload_url = file_urls[0] if isinstance(file_urls[0], str) else file_urls[0].get("url", "")
    if not upload_url:
        raise RuntimeError("MinerU cloud upload URL was empty")

    with input_path.open("rb") as source_file:
        upload_response = requests.put(upload_url, data=source_file, timeout=120)
    if upload_response.status_code not in (200, 201):
        raise RuntimeError(f"MinerU upload failed with HTTP {upload_response.status_code}")

    poll_headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        poll_response = requests.get(
            f"{cloud_url}/extract-results/batch/{batch_id}",
            headers=poll_headers,
            timeout=30,
        )
        poll_data = _json_or_raise(poll_response, "MinerU poll request failed")
        results = poll_data.get("data", {}).get("extract_result", [])
        if not results:
            continue
        item = results[0]
        state = item.get("state", "")
        if state == "running":
            continue
        if state == "failed":
            raise RuntimeError(f"MinerU parsing failed: {item.get('err_msg', 'unknown')}")
        if state == "done":
            markdown = _download_cloud_result(item, output_path)
            if not markdown:
                raise RuntimeError("MinerU cloud result did not contain Markdown output")
            output_path.write_text(markdown, encoding="utf-8")
            return

    raise RuntimeError(f"MinerU cloud parsing timed out after {timeout}s")


def _json_or_raise(response, context: str) -> dict:
    if response.status_code != 200:
        raise RuntimeError(f"{context}: HTTP {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"{context}: invalid JSON response") from error
    if payload.get("code", 0) not in {0, None}:
        raise RuntimeError(f"{context}: {payload.get('msg', 'unknown error')}")
    return payload


def _ensure_requests_available() -> None:
    if not callable(getattr(requests, "post", None)):
        raise RuntimeError("Missing dependency: install `requests` first")


def _download_cloud_result(item: dict, output_path: Path) -> str | None:
    direct_markdown = item.get("md_content")
    if isinstance(direct_markdown, str) and direct_markdown.strip():
        return direct_markdown

    zip_url = item.get("full_zip_url")
    if zip_url:
        response = requests.get(zip_url, timeout=120, proxies={"http": None, "https": None})
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download MinerU zip result: HTTP {response.status_code}")
        return _extract_zip_markdown(response.content, output_path)

    md_url = item.get("md_url")
    if md_url:
        response = requests.get(md_url, timeout=60, proxies={"http": None, "https": None})
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download MinerU markdown result: HTTP {response.status_code}")
        return response.text

    return None


def _extract_zip_markdown(zip_bytes: bytes, output_path: Path) -> str | None:
    asset_dir = output_path.with_name(f"{output_path.stem}_assets")
    markdown: str | None = None

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            if name.endswith(".md") and markdown is None:
                markdown = archive.read(name).decode("utf-8")
                continue
            parts = Path(name).parts
            filename = parts[-1]
            target_path = asset_dir / filename if "images" in parts else asset_dir / filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(archive.read(name))

    if markdown is None:
        return None

    asset_dir_name = asset_dir.name
    return IMAGE_REFERENCE_PATTERN.sub(rf"\1{asset_dir_name}/\2)", markdown)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a PDF file to Markdown via MinerU cloud.")
    parser.add_argument("input_path", help="Path to the source PDF file.")
    parser.add_argument("-o", "--output", dest="output_path", help="Path to the output Markdown file.")
    parser.add_argument("--cloud-url", default=CLOUD_API_URL, help="MinerU cloud API base URL.")
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input_path)
    output_path = (
        Path(args.output_path)
        if args.output_path
        else book_output_dir(input_path) / f"{sanitize_book_dir_name(canonical_book_name(input_path))}.md"
    )
    api_key = load_mineru_api_key()
    if not api_key:
        raise SystemExit("Missing MINERU_API_KEY; set the env var or add it to .env")

    convert_pdf_to_markdown(
        input_path,
        output_path,
        api_key=api_key,
        cloud_url=args.cloud_url,
        model_version=args.model_version,
        language=args.language,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
