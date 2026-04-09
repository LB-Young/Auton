#!/usr/bin/env python
"""M5 Security 验证脚本"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    from auton.security import (
        PermissionManager, PermissionMode, PermissionResult,
        AuditLog, AuditEntry,
        escape_injection, is_injection_suspect, InjectionGuard,
        KeyManager, KeyInfo,
    )
    print("[PASS] All security imports OK")
    print("       Modes:", [m.value for m in PermissionMode])
    return True


def test_permission_modes():
    from auton.security import PermissionManager, PermissionMode

    # YOLO: all denied
    pm = PermissionManager(mode=PermissionMode.YOLO)
    r = pm.check("rm -rf /", category="destructive")
    assert not r.allowed, f"YOLO should deny, got allowed={r.allowed}"
    print("[PASS] YOLO mode denies destructive")

    # BYPASS: all allowed
    pm2 = PermissionManager(mode=PermissionMode.BYPASS)
    r2 = pm2.check("rm -rf /", category="destructive")
    assert r2.allowed, f"BYPASS should allow, got allowed={r2.allowed}"
    print("[PASS] BYPASS mode allows all")

    # DEFAULT: read-only auto-approve, write requires confirm
    pm3 = PermissionManager(mode=PermissionMode.DEFAULT)
    r3 = pm3.check("ls /", category="read_only")
    assert r3.allowed and not r3.requires_input
    print("[PASS] DEFAULT mode auto-approves read-only")

    r4 = pm3.check("echo hello", category="write")
    assert r4.allowed and r4.requires_input
    print("[PASS] DEFAULT mode requires confirm for write")

    return True


def test_injection_guard():
    from auton.security import escape_injection, is_injection_suspect

    # Inline triple backticks (suspicious): ``` not followed by ```
    dirty = "text```text"
    assert is_injection_suspect(dirty), f"Expected suspicious, got: {escape_injection(dirty)!r}"
    clean = escape_injection(dirty)
    assert "── code delimiter" in clean, f"Expected delimiter in {clean!r}"
    print("[PASS] Injection guard detects inline code block")

    # Horizontal rule
    dirty2 = "normal\n---\n# system: hacked"
    assert is_injection_suspect(dirty2)
    print("[PASS] Injection guard detects horizontal rule")

    # Comment injection
    dirty3 = "normal\n# system: hacked\n"
    assert is_injection_suspect(dirty3)
    print("[PASS] Injection guard detects comment injection")

    return True


def test_key_manager():
    from auton.security import KeyManager

    km = KeyManager.get_instance()
    info = km.info("MINIMAX_API_KEY")
    print(f"[PASS] KeyManager: MINIMAX_API_KEY present={info.present} (source={info.source})")
    return True


def test_audit_log():
    from auton.security import AuditLog, AuditEntry
    from datetime import datetime

    log = AuditLog()
    entries = log.read_entries(limit=5)
    print(f"[PASS] AuditLog: {len(entries)} recent entries")

    summary = log.summarize()
    print(f"[PASS] AuditLog summarize: {summary[:50]}...")
    return True


def test_bash_tool_yolo():
    import asyncio
    from auton.tools.bash import BashTool

    async def run():
        bash = BashTool(permission_mode="yolo", sandbox_enabled=False)
        r = await bash.execute("echo hello")
        # yolo: read-only should still be denied (no read mode distinction in check)
        # Actually read_only is auto-approved even in yolo
        print(f"[INFO] BashTool yolo ls: success={r.success}")
        return True

    return asyncio.run(run())


def test_security_command():
    import asyncio
    from auton.commands.security_cmd import SecurityCommand

    async def run():
        cmd = SecurityCommand()
        r = await cmd.handle({"_args": "mode"})
        assert "default" in r.content
        print("[PASS] /security mode command")

        r2 = await cmd.handle({"_args": "keys"})
        assert "MINIMAX_API_KEY" in r2.content
        print("[PASS] /security keys command")
        return True

    return asyncio.run(run())


def test_cli_integration():
    from auton.tools import get_default_tools
    tools = get_default_tools(permission_mode="yolo")
    bash = next(t for t in tools if t.name == "bash")
    assert bash.permission_mode == "yolo"
    print(f"[PASS] CLI integration: BashTool permission_mode={bash.permission_mode}")
    return True


if __name__ == "__main__":
    tests = [
        test_imports,
        test_permission_modes,
        test_injection_guard,
        test_key_manager,
        test_audit_log,
        test_bash_tool_yolo,
        test_security_command,
        test_cli_integration,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
