"""
Concurrency & State Resolution Tests:
Verifies deterministic UUID5 slot overwrites and Last-Write-Wins (LWW) conflict handling.
"""

import uuid
import fleet_memory


def test_uuid5_deterministic_slot_generation(monkeypatch):
    """Verifies that the same slot name and client_id deterministically map to the same UUID5."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "work:desktop_hardware:gpu_profile"))

    res1 = fleet_memory.fleet_memory_store(
        text="RTX 3070 Ti Baseline",
        client_id="desktop_hardware",
        slot_name="gpu_profile",
        target_domain="work"
    )

    res2 = fleet_memory.fleet_memory_store(
        text="RTX 3070 Ti Undervolted @ 0.925V",
        client_id="desktop_hardware",
        slot_name="gpu_profile",
        target_domain="work"
    )

    assert res1["id"] == expected_uuid
    assert res2["id"] == expected_uuid
    assert res1["mode"] == "in_place_overwrite"
    assert res2["mode"] == "in_place_overwrite"


def test_lww_monotonic_revision_increment(monkeypatch):
    """Verifies that updating a slot increments the revision number monotonically."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    # First write -> revision 1
    res1 = fleet_memory.fleet_memory_store(
        text="Version 1 configuration",
        client_id="system",
        slot_name="caddy_config",
        timestamp=1000.0
    )
    assert res1["revision"] == 1

    # Second write with newer timestamp -> revision 2
    res2 = fleet_memory.fleet_memory_store(
        text="Version 2 configuration with TLS",
        client_id="system",
        slot_name="caddy_config",
        timestamp=1050.0
    )
    assert res2["revision"] == 2
    assert res2["status"] == "success"


def test_lww_rejects_stale_concurrent_write(monkeypatch):
    """Verifies that an incoming write with an older timestamp is rejected by Last-Write-Wins."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    # Authoritative write at t=2000
    res_latest = fleet_memory.fleet_memory_store(
        text="Authoritative high-volume webhook endpoint",
        client_id="payment",
        slot_name="webhook_url",
        timestamp=2000.0
    )
    assert res_latest["status"] == "success"

    # Out-of-order stale write arriving from delayed client at t=1500
    res_stale = fleet_memory.fleet_memory_store(
        text="Old stale webhook endpoint from offline node",
        client_id="payment",
        slot_name="webhook_url",
        timestamp=1500.0
    )

    assert res_stale["status"] == "conflict_rejected"
    assert "Stale write rejected by Last-Write-Wins" in res_stale["message"]
