from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from env_utils import load_key_from_dotenv
from output_paths import book_output_dir, canonical_book_name, sanitize_book_dir_name

GLOSSARY = {
    "agent": "智能体",
    "society": "社会",
    "agency": "能动性",
    "holism": "整体论",
    "gestalt": "格式塔",
    "mind": "心智",
    "self": "自我",
    "consciousness": "意识",
    "representation": "表征",
    "mechanical turk": "土耳其行棋傀儡",
    "descartes": "笛卡尔",
    "plato": "柏拉图",
}


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    translatable: bool


class TranslationCache:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self._data = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def parse_blocks(source: str) -> List[Block]:
    lines = source.splitlines()
    blocks: List[Block] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            blocks.append(Block(kind="blank", text="", translatable=False))
            index += 1
            continue

        if stripped in {"---", "***", "___"}:
            blocks.append(Block(kind="rule", text=line, translatable=False))
            index += 1
            continue

        if line.startswith("```") or line.startswith("~~~"):
            fence = line[:3]
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_lines.append(lines[index])
                if lines[index].startswith(fence):
                    index += 1
                    break
                index += 1
            blocks.append(Block(kind="code_fence", text="\n".join(code_lines), translatable=False))
            continue

        if line.startswith("#"):
            blocks.append(Block(kind="heading", text=line, translatable=True))
            index += 1
            continue

        if line.startswith(">"):
            quote_lines = [line]
            index += 1
            while index < len(lines) and lines[index].startswith(">"):
                quote_lines.append(lines[index])
                index += 1
            blocks.append(Block(kind="blockquote", text="\n".join(quote_lines), translatable=True))
            continue

        if _is_list_line(line):
            list_lines = [line]
            index += 1
            while index < len(lines) and (_is_list_line(lines[index]) or _is_indented_continuation(lines[index])):
                list_lines.append(lines[index])
                index += 1
            blocks.append(Block(kind="list", text="\n".join(list_lines), translatable=True))
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            current = lines[index]
            if not current.strip():
                break
            if current.startswith(("```", "~~~", "#", ">")) or _is_list_line(current):
                break
            if current.strip() in {"---", "***", "___"}:
                break
            paragraph_lines.append(current)
            index += 1
        blocks.append(Block(kind="paragraph", text="\n".join(paragraph_lines), translatable=True))

    return blocks


def _is_list_line(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(("- ", "* ", "+ ")):
        return True
    head = stripped.split(".", 1)[0]
    return head.isdigit() and stripped[len(head) :].startswith(". ")


def _is_indented_continuation(line: str) -> bool:
    return bool(line) and line[:1].isspace()


def batch_block_indexes(blocks: Sequence[Block], max_chars_per_chunk: int) -> List[List[int]]:
    batches: List[List[int]] = []
    current_batch: List[int] = []
    current_size = 0

    for index, block in enumerate(blocks):
        if not block.translatable:
            continue

        block_size = len(block.text)
        if current_batch and current_size + block_size > max_chars_per_chunk:
            batches.append(current_batch)
            current_batch = []
            current_size = 0

        current_batch.append(index)
        current_size += block_size

    if current_batch:
        batches.append(current_batch)

    return batches


def reconstruct_markdown(
    blocks: Sequence[Block],
    translations: Dict[int, str],
    output_mode: str = "bilingual",
) -> str:
    if output_mode not in {"bilingual", "chinese"}:
        raise ValueError(f"Unsupported output mode: {output_mode}")

    output_lines: List[str] = []

    for index, block in enumerate(blocks):
        if block.kind == "blank":
            if output_lines and output_lines[-1] != "":
                output_lines.append("")
            continue

        if block.translatable:
            translated = translations.get(index)
            if output_mode == "bilingual":
                output_lines.extend(block.text.splitlines())
                if translated is not None:
                    output_lines.append("")
                    output_lines.extend(translated.splitlines())
            elif translated is not None:
                output_lines.extend(translated.splitlines())
        else:
            output_lines.extend(block.text.splitlines())

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    return "\n".join(output_lines)


def block_cache_key(block: Block, model: str) -> str:
    digest = hashlib.sha256()
    digest.update(model.encode("utf-8"))
    digest.update(b"\0")
    digest.update(block.kind.encode("utf-8"))
    digest.update(b"\0")
    digest.update(block.text.encode("utf-8"))
    return digest.hexdigest()


def build_messages(
    texts: Sequence[str],
    current_heading: str | None = None,
    previous_context: Dict[str, str] | None = None,
) -> List[Dict[str, str]]:
    glossary_text = "\n".join(f"- {english} -> {chinese}" for english, chinese in GLOSSARY.items())
    blocks = [{"id": index, "text": text} for index, text in enumerate(texts)]
    user_payload = {
        "instructions": [
            "Translate each Markdown block into Simplified Chinese.",
            "Keep Markdown markers and structure.",
            "Do not add commentary.",
            "Return valid JSON with a translations array of objects using the exact same ids you received.",
            "Each translations item must have shape {\"id\": <same id>, \"text\": <translated markdown>}.",
            "Keep terminology consistent across the whole book and follow the glossary with high priority.",
            "Preserve the depth of philosophical arguments and historical references rather than flattening them.",
            "If a literal translation would confuse Chinese readers, you may add a very brief parenthetical note.",
            "Use a style that is academically precise yet readable and lightly literary, avoiding stiff word-for-word translation.",
        ],
        "glossary": glossary_text,
        "current_heading": current_heading,
        "previous_context": previous_context,
        "blocks": blocks,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a careful translator of philosophical and cognitive-science books. "
                "Preserve Markdown structure, keep terminology consistent, retain the depth of philosophical reasoning and historical allusions, "
                "and use a brief parenthetical note only when it is needed to make an allusion understandable in Chinese."
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _parse_translation_items(content: str, expected_count: int) -> List[str]:
    payload = json.loads(content)
    items = payload["translations"]
    ordered: Dict[int, str] = {}

    for item in items:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            raise ValueError("DeepSeek returned malformed translation items")
        ordered[int(item["id"])] = str(item["text"])

    if len(ordered) != expected_count:
        raise ValueError("DeepSeek returned a mismatched translation count")

    missing = [index for index in range(expected_count) if index not in ordered]
    if missing:
        raise ValueError("DeepSeek returned translation items with missing ids")

    return [ordered[index] for index in range(expected_count)]


def _is_structural_batch_error(error: Exception) -> bool:
    message = str(error)
    return "mismatched translation count" in message or "missing ids" in message


def translate_batch(
    client,
    texts: Sequence[str],
    model: str,
    retries: int = 3,
    current_heading: str | None = None,
    previous_context: Dict[str, str] | None = None,
) -> List[str]:
    if not texts:
        return []

    last_error = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=build_messages(
                    texts,
                    current_heading=current_heading,
                    previous_context=previous_context,
                ),
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return _parse_translation_items(content, expected_count=len(texts))
        except Exception as error:  # pragma: no cover - branch exercised with mocks and retries
            last_error = error
            if _is_structural_batch_error(error) and len(texts) > 1:
                break
            if attempt < retries - 1:
                time.sleep(2**attempt)

    if len(texts) > 1:
        midpoint = len(texts) // 2
        return translate_batch(
            client,
            texts[:midpoint],
            model=model,
            retries=retries,
            current_heading=current_heading,
            previous_context=previous_context,
        ) + translate_batch(
            client,
            texts[midpoint:],
            model=model,
            retries=retries,
            current_heading=current_heading,
            previous_context=previous_context,
        )

    raise RuntimeError(f"Translation failed after {retries} attempts") from last_error


def create_client(api_key: str):
    try:
        from openai import OpenAI
    except ImportError as error:  # pragma: no cover - depends on environment
        raise RuntimeError("Missing dependency: install `openai` first") from error

    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def load_api_key(env_path: Path | None = None) -> str | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        return api_key

    return load_key_from_dotenv("DEEPSEEK_API_KEY", __file__, env_path)


def _compute_heading_map(blocks: Sequence[Block]) -> Dict[int, str | None]:
    headings: Dict[int, str | None] = {}
    current_heading: str | None = None
    for index, block in enumerate(blocks):
        if block.kind == "heading":
            current_heading = block.text
        headings[index] = current_heading
    return headings


def _previous_context_for_index(
    block_index: int,
    blocks: Sequence[Block],
    translations: Dict[int, str],
) -> Dict[str, str] | None:
    for previous_index in range(block_index - 1, -1, -1):
        if previous_index in translations and blocks[previous_index].translatable:
            return {
                "source": blocks[previous_index].text,
                "translation": translations[previous_index],
            }
    return None


def run_translation_pipeline(
    input_path: Path,
    output_path: Path,
    client,
    model: str,
    max_chars_per_chunk: int,
    cache_path: Path,
    resume: bool,
    max_workers: int = 1,
    output_mode: str = "bilingual",
    executor_factory: Callable[..., ThreadPoolExecutor] = ThreadPoolExecutor,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    source = input_path.read_text(encoding="utf-8")
    blocks = parse_blocks(source)
    translations: Dict[int, str] = {}
    cache = TranslationCache(cache_path)
    heading_map = _compute_heading_map(blocks)

    pending_jobs: List[tuple[list[int], str | None, Dict[str, str] | None]] = []

    for batch in batch_block_indexes(blocks, max_chars_per_chunk=max_chars_per_chunk):
        missing_indexes: List[int] = []
        missing_texts: List[str] = []

        for block_index in batch:
            cache_key = block_cache_key(blocks[block_index], model)
            cached = cache.get(cache_key) if resume else None
            if cached is not None:
                translations[block_index] = cached
            else:
                missing_indexes.append(block_index)
                missing_texts.append(blocks[block_index].text)

        if not missing_indexes:
            continue

        pending_jobs.append(
            (
                missing_indexes,
                heading_map.get(missing_indexes[0]),
                _previous_context_for_index(missing_indexes[0], blocks, translations),
            )
        )

    if pending_jobs:
        with executor_factory(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(
                    translate_batch,
                    client,
                    [blocks[index].text for index in indexes],
                    model,
                    3,
                    heading,
                    previous_context,
                ): (indexes, heading, previous_context)
                for indexes, heading, previous_context in pending_jobs
            }

            for future in as_completed(future_to_job):
                indexes, _, _ = future_to_job[future]
                translated_texts = future.result()
                for block_index, translated_text in zip(indexes, translated_texts):
                    translations[block_index] = translated_text
                    cache.set(block_cache_key(blocks[block_index], model), translated_text)
                cache.save()

    output_path.write_text(
        reconstruct_markdown(blocks, translations, output_mode=output_mode),
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate a Markdown book into bilingual Markdown via DeepSeek.")
    parser.add_argument("input_path", nargs="?", default="The_society_of_mind.md")
    parser.add_argument("-o", "--output", dest="output_path")
    parser.add_argument("--output-mode", choices=("bilingual", "chinese"), default="bilingual")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--max-chars-per-chunk", type=int, default=6000)
    parser.add_argument("--cache-path")
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.set_defaults(resume=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input_path)
    book_name = sanitize_book_dir_name(canonical_book_name(input_path))
    default_output_dir = book_output_dir(input_path)
    output_suffix = ".bilingual.md" if args.output_mode == "bilingual" else ".zh.md"
    output_path = Path(args.output_path) if args.output_path else default_output_dir / f"{book_name}{output_suffix}"
    cache_path = Path(args.cache_path) if args.cache_path else default_output_dir / f"{book_name}.translation_cache.json"
    api_key = load_api_key()
    if not api_key:
        raise SystemExit("Missing DEEPSEEK_API_KEY; set the env var or add it to .env")

    client = create_client(api_key)
    run_translation_pipeline(
        input_path=input_path,
        output_path=output_path,
        client=client,
        model=args.model,
        max_chars_per_chunk=args.max_chars_per_chunk,
        cache_path=cache_path,
        resume=args.resume,
        max_workers=args.max_workers,
        output_mode=args.output_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
