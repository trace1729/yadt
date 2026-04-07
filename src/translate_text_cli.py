from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from translate_markdown_book import create_client, load_api_key


DEFAULT_MODEL = "deepseek-chat"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Translate one English string to Simplified Chinese.")
    parser.add_argument("text", help="English text to translate")
    parser.add_argument("-v", "--verbose", action="store_true", help="Include pronunciation and an example sentence")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="DeepSeek model name")
    return parser.parse_args(argv)


def translate_text(client, text: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You translate English into natural Simplified Chinese. Return only the translated Chinese text.",
            },
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def translate_text_verbose(client, text: str, model: str) -> dict[str, str]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You help English speakers understand Chinese translations. "
                    "Return JSON with translation, pronunciation, and example fields."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Translate this English text into Simplified Chinese and provide pronunciation guidance "
                    "plus one short Chinese example sentence as JSON: "
                    f"{text}"
                ),
            },
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return parse_verbose_response(response.choices[0].message.content)


def parse_verbose_response(content: str) -> dict[str, str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("DeepSeek returned invalid verbose JSON") from error

    required_fields = ("translation", "pronunciation", "example")
    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        raise ValueError(f"DeepSeek verbose response is missing required fields: {', '.join(missing)}")

    return {field: str(payload[field]).strip() for field in required_fields}


def format_verbose_output(payload: dict[str, str]) -> str:
    return (
        f"Translation: {payload['translation']}\n"
        f"Pronunciation: {payload['pronunciation']}\n"
        f"Example: {payload['example']}"
    )


def main(argv: Sequence[str] | None = None, env_path: Path | None = None) -> int:
    args = parse_args(argv)
    api_key = load_api_key(env_path)
    if not api_key:
        print("Missing DEEPSEEK_API_KEY. Set it in the environment or .env.", file=sys.stderr)
        return 1

    try:
        client = create_client(api_key)
        if args.verbose:
            payload = translate_text_verbose(client, args.text, model=args.model)
            print(format_verbose_output(payload))
        else:
            print(translate_text(client, args.text, model=args.model))
    except Exception as error:
        print(f"Translation failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
