from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _YamlLine:
    indent: int
    content: str


def load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_simple_yaml(text)
    return yaml.safe_load(text) or {}


def _parse_simple_yaml(text: str) -> Any:
    lines = _preprocess(text)
    if not lines:
        return {}
    parsed, index = _parse_block(lines, 0, lines[0].indent)
    if index != len(lines):
        raise ValueError("Unable to parse YAML content completely")
    return parsed


def _preprocess(text: str) -> list[_YamlLine]:
    processed: list[_YamlLine] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        processed.append(_YamlLine(indent=indent, content=raw_line[indent:]))
    return processed


def _parse_block(lines: list[_YamlLine], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index].content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines: list[_YamlLine], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise ValueError(f"Unexpected indentation at line: {line.content}")
        if line.content.startswith("- "):
            break

        key, separator, remainder = line.content.partition(":")
        if not separator:
            raise ValueError(f"Expected ':' in YAML mapping line: {line.content}")

        key = key.strip()
        remainder = remainder.strip()
        index += 1

        if remainder:
            result[key] = _parse_scalar(remainder)
            continue

        if index >= len(lines) or lines[index].indent <= indent:
            result[key] = {}
            continue

        child, index = _parse_block(lines, index, lines[index].indent)
        result[key] = child

    return result, index


def _parse_list(lines: list[_YamlLine], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise ValueError(f"Unexpected indentation at line: {line.content}")
        if not line.content.startswith("- "):
            break

        remainder = line.content[2:].strip()
        index += 1

        if remainder:
            result.append(_parse_scalar(remainder))
            continue

        if index >= len(lines) or lines[index].indent <= indent:
            result.append(None)
            continue

        child, index = _parse_block(lines, index, lines[index].indent)
        result.append(child)

    return result, index


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
