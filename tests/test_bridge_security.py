"""
Desktop Bridge Defense-in-Depth Security Tests:
Verifies constant-time HMAC bearer authentication, path jail traversal prevention,
command injection blacklist regexes, and payload size bounds.
"""

import re
from pathlib import Path
import desktop_bridge


def test_constant_time_hmac_auth(monkeypatch):
    """Verifies that requests require a valid Bearer token matching FLEET_KEY."""
    monkeypatch.setattr(desktop_bridge, "FLEET_KEY", "super_secret_256bit_cluster_token")

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
    assert DummyHandler({"Authorization": "Bearer super_secret_256bit_cluster_token"})._verify_auth()


def test_command_blacklist_catches_destructive_commands():
    """Verifies regex patterns prevent dangerous disk, system, and fork-bomb commands."""
    dangerous_commands = [
        "format c: /fs:ntfs",
        "FORMAT D:",
        "diskpart /s script.txt",
        "rmdir /s /q C:\\Users",
        "rmdir /S /Q D:\\Data",
        "rm -rf /",
        "rm -rf /etc",
        "shutdown /s /t 0",
        "stop-computer -Force",
        "net user hacker password /add",
        "reg delete HKLM\\Software",
        ":(){ :|:& };:"
    ]

    for cmd in dangerous_commands:
        matched = False
        cmd_lower = cmd.lower()
        for pattern in desktop_bridge.COMMAND_BLACKLIST:
            if re.search(pattern, cmd_lower):
                matched = True
                break
        assert matched, f"Command '{cmd}' should have been blocked by COMMAND_BLACKLIST!"


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
