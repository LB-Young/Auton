"""Verify bootstrap orchestration without downloads, dependency changes, or model calls."""

import importlib.util
import sys
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from auton.bootstrap.config import ApplicationConfig


@pytest.fixture
def launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "auton_server_launcher", Path(__file__).parents[1] / "scripts/server.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_env_template_private_and_existing_key_never_overwritten(
    launcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env.example").write_text("DEEPSEEK_API_KEY=\n")
    assert not launcher.ensure_env(tmp_path)
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    private = "fixture-secret-kept-only-in-test"
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=" + private)
    assert launcher.ensure_env(tmp_path)
    assert (tmp_path / ".env").read_text().endswith(private)
    assert private not in capsys.readouterr().out


def test_startup_excludes_concurrent_dependency_mutation(
    launcher: ModuleType, tmp_path: Path
) -> None:
    with launcher.startup_lock(tmp_path):
        with pytest.raises(SystemExit, match="重复启动"):
            with launcher.startup_lock(tmp_path):
                pytest.fail("Concurrent bootstrap acquired the lock")
    with launcher.startup_lock(tmp_path):
        pass


def test_prepare_caches_frontend_and_uses_existing_verified_downloaders(
    launcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = tmp_path / "clients/web"
    web.mkdir(parents=True)
    (web / "package.json").write_text("{}")
    (web / "package-lock.json").write_text("{}")
    commands = []

    def run(command: list[str], root: Path, env: dict[str, str] | None = None) -> None:
        commands.append((command, root, env))
        if command[0] == "npm":
            (web / "node_modules/.bin").mkdir(parents=True)
            (web / "node_modules/.bin/vite").touch()
            (web / "node_modules/.package-lock.json").write_text("{}")

    monkeypatch.setattr(launcher, "run", run)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-provider-credential")
    monkeypatch.setenv("HF_TOKEN", "fixture-hf-credential")
    assert launcher.prepare(tmp_path) == tmp_path / ".venv/bin/python"
    assert commands[0][0] == ["uv", "sync", "--frozen", "--extra", "judgment"]
    downloads = [
        c
        for c in commands
        if c[0][-1].endswith(("download_context_tokenizers.py", "download_laya.py"))
    ]
    assert len(downloads) == 2
    for _, _, env in downloads:
        assert env is not None and "DEEPSEEK_API_KEY" not in env and "HF_TOKEN" not in env
    launcher.prepare(tmp_path)
    assert sum(c[0][0] == "npm" for c in commands) == 1
    (web / "package-lock.json").write_text('{"changed":true}')
    # Simulate npm replacing its own node_modules on a lockfile change.
    monkeypatch.setattr(
        launcher, "run", lambda cmd, root, env=None: commands.append((cmd, root, env))
    )
    launcher.prepare(tmp_path)
    assert sum(c[0][0] == "npm" for c in commands) == 2


def test_main_pins_real_config_and_refuses_busy_ports_before_setup(
    launcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["server.py"])
    monkeypatch.setattr(launcher, "ensure_env", lambda root: True)
    monkeypatch.setattr(launcher, "check_tools", lambda: None)
    called = []

    def prepared(root: Path) -> Path:
        called.append("prepare")
        return root / ".venv/bin/python"

    monkeypatch.setattr(launcher, "prepare", prepared)

    def busy() -> None:
        raise SystemExit("port occupied")

    monkeypatch.setattr(launcher, "check_ports", busy)
    with pytest.raises(SystemExit, match="occupied"):
        launcher.main()
    assert called == []
    monkeypatch.setattr(launcher, "check_ports", lambda: None)
    monkeypatch.setattr(
        launcher, "run", lambda command, root, env: called.append(env["AUTON_CONFIG"])
    )
    monkeypatch.setenv("AUTON_CONFIG", "config/test.toml")
    launcher.main()
    assert called == ["prepare", str(tmp_path / "config/server.toml")]


def test_server_preset_is_real_bounded_and_does_not_enable_training() -> None:
    path = Path(__file__).parents[1] / "config/server.toml"
    config = ApplicationConfig.model_validate(tomllib.loads(path.read_text()))
    assert config.profile == "dev" and config.implementation == "disabled"
    assert (
        config.models.backend == "deepseek" and config.models.secret_reference == "DEEPSEEK_API_KEY"
    )
    assert config.constitution.remote_providers == ("deepseek",)
    assert config.judgment.backend == "laya" and not config.judgment.application_enabled
    assert config.training.backend == config.decision_training.backend == "disabled"
    assert not config.operations.enabled
