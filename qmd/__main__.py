"""qmd 包入口：python -m qmd ...

转发到新 CLI；旧 CLI 仍可通过 python -m qmd.cli.main 访问（M3 前保留）。
"""
from qmd.cli.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
