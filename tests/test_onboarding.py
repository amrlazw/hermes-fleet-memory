"""What a new user sees during onboarding: the wizard's questions and hints, and --doctor."""
import sys
from unittest.mock import patch

import fleet_memory
import pytest

import fleet_wizard


def run_wizard(tmp_path, monkeypatch, capsys, answers):
    """Drive the interactive wizard with scripted answers. Returns (prompts, stdout, client .env)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["fleet_wizard.py"])
    monkeypatch.delenv("FLEET_TELEMETRY", raising=False)
    prompts, queue = [], list(answers)

    def fake_input(prompt=""):
        prompts.append(prompt)
        return queue.pop(0)

    with patch("builtins.input", fake_input):
        fleet_wizard.main()
    assert queue == [], f"wizard asked fewer questions than expected, {len(queue)} answers unused"
    env = (tmp_path / "client" / ".env").read_text(encoding="utf-8")
    return prompts, capsys.readouterr().out, env


def env_keys(env):
    return {line.split("=", 1)[0] for line in env.splitlines() if "=" in line and not line.startswith("#")}


def test_standalone_asks_only_about_local_qdrant(tmp_path, monkeypatch, capsys):
    prompts, out, env = run_wizard(tmp_path, monkeypatch, capsys, [
        "3",   # 1 machine only
        "",    # Qdrant URL -> default local
        "",    # API key -> none
        "",    # domain -> default
        "",    # node name -> default
        "4",   # framework -> manual
    ])

    asked = "\n".join(prompts)
    assert "Hub" not in asked and "Tunnel" not in asked and "Bridge" not in asked
    assert "Enter your Qdrant URL" in asked
    assert "FLEET_QDRANT_HOST=127.0.0.1" in env and "FLEET_QDRANT_PORT=6333" in env
    assert "FLEET_HARD_DOMAIN=personal" in env
    # No invented key for a keyless local Qdrant, and nothing that belongs to a mesh.
    assert env_keys(env).isdisjoint({"FLEET_QDRANT_KEY", "FLEET_BRIDGE_KEY", "FLEET_TUNNEL_KEY", "FLEET_SERVER_HOST"})
    assert "docker run" in out and "start-tunnel" not in out
    assert "↳" in out


def test_standalone_keeps_a_key_when_given_one(tmp_path, monkeypatch, capsys):
    _, _, env = run_wizard(tmp_path, monkeypatch, capsys,
                           ["3", "https://abc.cloud.qdrant.io:6333", "cloud-key", "", "", "4"])
    assert "FLEET_QDRANT_KEY=cloud-key" in env and "FLEET_QDRANT_HTTPS=true" in env


def test_mesh_member_is_told_where_each_key_lives(tmp_path, monkeypatch, capsys):
    _, out, env = run_wizard(tmp_path, monkeypatch, capsys, [
        "2",    # 3+ nodes
        "2",    # personal node
        "",     # hub URL -> default
        "qk",   # Qdrant key
        "tk",   # tunnel key
        "bk",   # bridge key
        "",     # domain
        "",     # node name
        "n",    # enable bridge
        "4",    # framework -> manual
    ])

    for where in ("Node Join Credentials", "FLEET_QDRANT_KEY in the hub's server/.env",
                  "FLEET_TUNNEL_KEY in the hub's server/.env", "FLEET_BRIDGE_KEY in the hub's server/.env"):
        assert where in out
    assert "FLEET_QDRANT_KEY=qk" in env and "FLEET_TUNNEL_KEY=tk" in env and "FLEET_BRIDGE_KEY=bk" in env


def test_qdrant_cloud_pair_points_at_the_cluster_page(tmp_path, monkeypatch, capsys):
    _, out, env = run_wizard(tmp_path, monkeypatch, capsys,
                             ["1", "1", "https://abc.cloud.qdrant.io:6333", "cloud-key", "", "", "n", "4"])
    assert "cloud.qdrant.io" in out and "API Keys" in out
    assert "FLEET_QDRANT_KEY=cloud-key" in env


@pytest.mark.parametrize("tasks_url, expected", [
    ("", "[INFO] no control plane (FLEET_TASKS_URL unset)"),
    ("http://127.0.0.1:8088", "[WARN] control-plane token comes from FLEET_QDRANT_KEY"),
])
def test_doctor_warns_about_the_task_token_only_with_a_control_plane(monkeypatch, capsys, tasks_url, expected):
    monkeypatch.setattr(fleet_memory, "FLEET_TASKS_URL", tasks_url)
    monkeypatch.setattr(fleet_memory, "QDRANT_API_KEY", "q")
    monkeypatch.setattr(fleet_memory, "FLEET_KEY", "q")
    monkeypatch.setattr(fleet_memory, "FLEET_KEY_SOURCE", "FLEET_QDRANT_KEY")
    monkeypatch.setattr(fleet_memory, "_probe_qdrant", lambda: (True, 1.0, ["hermes_fleet_memory"]))

    fleet_memory.cmd_doctor(fleet_memory._build_parser().parse_args(["--doctor"]))

    section = capsys.readouterr().out.split("secret separation:")[1].split("vector engine")[0]
    assert expected in section
    if not tasks_url:
        assert "[WARN] control-plane" not in section


def test_fresh_wizard_install_has_no_doctor_warnings(tmp_path, monkeypatch, capsys):
    """The first --doctor after a 2-node Qdrant Cloud setup must not raise alarms."""
    run_wizard(tmp_path, monkeypatch, capsys, ["1", "2", "https://abc.cloud.qdrant.io:6333", "k", "", "", "4"])
    monkeypatch.setattr(fleet_memory, "FLEET_TASKS_URL", "")
    monkeypatch.setattr(fleet_memory, "FLEET_BRIDGE_KEY", "")
    monkeypatch.setattr(fleet_memory, "QDRANT_API_KEY", "k")
    monkeypatch.setattr(fleet_memory, "FLEET_KEY", "k")
    monkeypatch.setattr(fleet_memory, "_probe_qdrant", lambda: (True, 1.0, ["hermes_fleet_memory"]))

    fleet_memory.cmd_doctor(fleet_memory._build_parser().parse_args(["--doctor"]))

    assert "[WARN]" not in capsys.readouterr().out.split("secret separation:")[1].split("vector engine")[0]
