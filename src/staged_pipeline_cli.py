from __future__ import annotations

from typing import Sequence

from yaet_cli import main as yaet_main


def main(argv: Sequence[str] | None = None) -> int:
    return yaet_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
