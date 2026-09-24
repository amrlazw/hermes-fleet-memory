"""Credentials must not reach the shared domain.

Fake credentials are assembled at runtime so this file never contains a
string that looks like a real token to secret scanners.
"""
import fleet_memory
import pytest
from secret_scan import find_secrets

HEX64 = "7c" * 32
FAKE = {
    "hex256_key": f"cluster key rotated to {HEX64}",
    "fleet_bearer_token": "bearer " + "flk" + "_" + "Ab3" * 8,
    "a2a_peer_token": "peer token " + "tok" + "_fleet_a2a_" + "x9" * 10,
    "cloudflare_token": "tunnel " + "cfut" + "_" + "Z1" * 12,
    "api_secret_key": "OPENAI_API_KEY=" + "sk" + "-proj-" + "q" * 30,
    "github_token": "gh" + "p_" + "a1" * 18,
    "aws_access_key": "AK" + "IA" + "Q" * 16,
    "slack_token": "xo" + "xb-" + "1234-abcd-efgh",
    "telegram_bot_token": "123456789:" + "A" * 35,
    "private_key_block": "-----BEGIN " + "OPENSSH PRIVATE KEY-----",
}


@pytest.mark.parametrize("name", sorted(FAKE))
def test_each_pattern_is_detected(name):
    assert name in find_secrets(FAKE[name])


@pytest.mark.parametrize("text", [
    "Commit 4889fd0e1f2a3b4c5d6e7f8091a2b3c4d5e6f708 fixed the CLI",   # 40-hex git sha
    f"image digest sha256:{HEX64}",                                   # content hash
    "Set FLEET_KEY=your_control_plane_bearer_token in $FLEET_HOME/.env",
    "Live value in Qdrant slot 'kimchi_recovery_key', never copied here",
    "",
])
def test_ordinary_cards_pass(text):
    assert find_secrets(text) == []


def test_findings_never_echo_the_secret():
    assert HEX64 not in repr(find_secrets(FAKE["hex256_key"]))


def test_shared_write_with_a_secret_is_refused(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    res = fleet_memory.fleet_memory_store(
        text=FAKE["a2a_peer_token"], client_id="fleet_infra", slot_name="node2_identity",
        target_domain="shared")

    assert res["status"] == "rejected"
    assert res["error_type"] == "secret_detected"
    assert res["findings"] == ["a2a_peer_token"]
    assert "tok_" not in res["message"]
    assert mock_fleet_memory_engine.points == {}


def test_default_domain_on_an_all_node_is_shared_and_refused(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    res = fleet_memory.fleet_memory_store(text=FAKE["hex256_key"])
    assert res["status"] == "rejected"
    assert mock_fleet_memory_engine.points == {}


def test_personal_write_with_a_secret_is_stored_with_a_warning(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")
    res = fleet_memory.fleet_memory_store(
        text=FAKE["hex256_key"], client_id="personal", slot_name="recovery_key", target_domain="personal")

    assert res["status"] == "success"
    assert "hex256_key" in res["secret_warning"]
    assert len(mock_fleet_memory_engine.points) == 1


def test_clean_shared_write_has_no_warning(monkeypatch, mock_fleet_memory_engine):
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")
    res = fleet_memory.fleet_memory_store(
        text="Qdrant key lives in $FLEET_HOME/.env as FLEET_QDRANT_KEY", client_id="fleet_infra",
        slot_name="where_keys_live", target_domain="shared")

    assert res["status"] == "success"
    assert "secret_warning" not in res
