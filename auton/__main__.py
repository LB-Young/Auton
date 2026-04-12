"""Auton CLI 入口：支持 python -m auton"""

from .adapters.cli.main import app

if __name__ == "__main__":
    app()
