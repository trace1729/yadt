from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from simple_yaml import load_yaml


DEFAULT_CONFIG_DIRNAME = ".yaet"
DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_EPUB_BACKEND = "yaet"
DEFAULT_MARKDOWN_BACKEND = "yaet"

VALID_EPUB_BACKENDS = frozenset({"yaet", "epub_translator"})
VALID_MARKDOWN_BACKENDS = frozenset({"yaet", "free_markdown_translator"})


@dataclass
class ParserConfig:
    epub: str = DEFAULT_EPUB_BACKEND
    markdown: str = DEFAULT_MARKDOWN_BACKEND


@dataclass
class ProviderConfig:
    name: str = "openai"
    base_url: str = "https://api.deepseek.com"
    api_key: str | None = None
    api_key_env: str = "DEEPSEEK_API_KEY"
    model: str = "deepseek-chat"
    temperature: float = 0.2
    max_tokens: int = 8000


@dataclass
class StyleConfig:
    tone: str = "academic"
    preserve_terms: list[str] = field(default_factory=list)
    audience: str = "general readers"
    instructions: list[str] = field(default_factory=list)


@dataclass
class PromptConfig:
    system_template: str | None = None
    title: str = ""
    summary: str = ""
    terms: str = ""


@dataclass
class SegmentationConfig:
    max_bundle_chars: int = 6000
    max_bundle_segments: int = 36


@dataclass
class TranslationConfig:
    max_workers: int = 3
    resume: bool = True
    output_mode: str = "bilingual"


@dataclass
class YaetConfig:
    parsers: ParserConfig = field(default_factory=ParserConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    glossary: dict[str, str] = field(default_factory=dict)


def _workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_user_config_dir() -> Path:
    return Path.home() / DEFAULT_CONFIG_DIRNAME


def default_user_config_path() -> Path:
    return default_user_config_dir() / DEFAULT_CONFIG_FILENAME


def resolve_config_path(config_path: str | None = None) -> Path | None:
    root = _workspace_root()
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path).expanduser())
    candidates.extend(
        [
            root / "yaet.yaml",
            root / "yaet.yml",
            root / "config.yaml",
            root / "src" / "config.yaml",
            default_user_config_path(),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _filter_known_keys(section: dict[str, Any], config_type, section_name: str) -> dict[str, Any]:
    allowed = {item.name for item in fields(config_type)}
    unknown = sorted(set(section) - allowed)
    if unknown:
        logging.warning("Ignoring unsupported config keys in %s: %s", section_name, ", ".join(unknown))
    return {key: value for key, value in section.items() if key in allowed}


def _normalize_backend(value: str, valid: set[str] | frozenset[str], default: str) -> str:
    if value in valid:
        return value
    logging.warning("Unsupported backend '%s'; falling back to '%s'", value, default)
    return default


def _default_config_dict() -> dict[str, Any]:
    return {
        "parsers": {
            "epub": DEFAULT_EPUB_BACKEND,
            "markdown": DEFAULT_MARKDOWN_BACKEND,
        },
        "provider": {
            "name": "openai",
            "base_url": "https://api.deepseek.com",
            "api_key": None,
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 8000,
        },
        "style": {
            "tone": "academic",
            "preserve_terms": [],
            "audience": "general readers",
            "instructions": [],
        },
        "prompt": {
            "system_template": None,
            "title": "",
            "summary": "",
            "terms": "",
        },
        "segmentation": {
            "max_bundle_chars": 6000,
            "max_bundle_segments": 36,
        },
        "translation": {
            "max_workers": 3,
            "resume": True,
            "output_mode": "bilingual",
        },
        "glossary": {},
    }


def load_config(config_path: str | None = None) -> YaetConfig:
    resolved = resolve_config_path(config_path)
    loaded: dict[str, Any] = {}
    if resolved is not None:
        parsed = load_yaml(resolved.read_text(encoding="utf-8")) or {}
        if not isinstance(parsed, dict):
            raise ValueError(f"Config root must be a mapping: {resolved}")
        loaded = parsed

    data = _merge_dict(_default_config_dict(), loaded)
    parsers = ParserConfig(**_filter_known_keys(data.get("parsers", {}), ParserConfig, "parsers"))
    parsers.epub = _normalize_backend(parsers.epub, VALID_EPUB_BACKENDS, DEFAULT_EPUB_BACKEND)
    parsers.markdown = _normalize_backend(parsers.markdown, VALID_MARKDOWN_BACKENDS, DEFAULT_MARKDOWN_BACKEND)

    provider = ProviderConfig(**_filter_known_keys(data.get("provider", {}), ProviderConfig, "provider"))
    style = StyleConfig(**_filter_known_keys(data.get("style", {}), StyleConfig, "style"))
    prompt = PromptConfig(**_filter_known_keys(data.get("prompt", {}), PromptConfig, "prompt"))
    segmentation = SegmentationConfig(**_filter_known_keys(data.get("segmentation", {}), SegmentationConfig, "segmentation"))
    translation = TranslationConfig(**_filter_known_keys(data.get("translation", {}), TranslationConfig, "translation"))

    glossary = data.get("glossary", {})
    if not isinstance(glossary, dict):
        raise ValueError("Config glossary must be a mapping of source term to translated term.")

    return YaetConfig(
        parsers=parsers,
        provider=provider,
        style=style,
        prompt=prompt,
        segmentation=segmentation,
        translation=translation,
        glossary={str(key): str(value) for key, value in glossary.items()},
    )


def apply_cli_overrides(
    config: YaetConfig,
    *,
    model: str | None = None,
    max_chars_per_chunk: int | None = None,
    max_workers: int | None = None,
    epub_parser_backend: str | None = None,
    markdown_parser_backend: str | None = None,
    resume: bool | None = None,
    output_mode: str | None = None,
) -> YaetConfig:
    resolved = copy.deepcopy(config)
    if model is not None:
        resolved.provider.model = model
    if max_chars_per_chunk is not None:
        resolved.segmentation.max_bundle_chars = max_chars_per_chunk
    if max_workers is not None:
        resolved.translation.max_workers = max_workers
    if epub_parser_backend is not None:
        resolved.parsers.epub = _normalize_backend(epub_parser_backend, VALID_EPUB_BACKENDS, DEFAULT_EPUB_BACKEND)
    if markdown_parser_backend is not None:
        resolved.parsers.markdown = _normalize_backend(
            markdown_parser_backend,
            VALID_MARKDOWN_BACKENDS,
            DEFAULT_MARKDOWN_BACKEND,
        )
    if resume is not None:
        resolved.translation.resume = resume
    if output_mode is not None:
        resolved.translation.output_mode = output_mode
    return resolved


def build_cache_namespace(config: YaetConfig) -> str:
    if config == YaetConfig():
        return ""
    payload = {
        "parsers": {
            "epub": config.parsers.epub,
            "markdown": config.parsers.markdown,
        },
        "provider": {
            "name": config.provider.name,
            "base_url": config.provider.base_url,
            "model": config.provider.model,
            "temperature": config.provider.temperature,
            "max_tokens": config.provider.max_tokens,
        },
        "style": {
            "tone": config.style.tone,
            "preserve_terms": config.style.preserve_terms,
            "audience": config.style.audience,
            "instructions": config.style.instructions,
        },
        "prompt": {
            "system_template": config.prompt.system_template,
            "title": config.prompt.title,
            "summary": config.prompt.summary,
            "terms": config.prompt.terms,
        },
        "glossary": config.glossary,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:12]
