"""
Security & Boundary Enforcement Tests:
Verifies hardware-enforced domain firewall rules across personal, work, and cloud partitions.
"""

import pytest
import fleet_memory


def test_personal_node_allowed_domains(monkeypatch):
    """Personal node must be allowed to search personal and shared domains."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")

    # Default query without target_domain should query both personal and shared
    domains = fleet_memory.validate_domain_access(None, is_write=False)
    assert set(domains) == {"personal", "shared"}

    # Explicit query for personal
    domains = fleet_memory.validate_domain_access("personal", is_write=False)
    assert domains == ["personal"]

    # Explicit query for shared
    domains = fleet_memory.validate_domain_access("shared", is_write=False)
    assert domains == ["shared"]


def test_personal_node_denied_work_query(monkeypatch):
    """Personal node attempting to query enterprise work domain must raise PermissionError."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")

    with pytest.raises(PermissionError) as exc_info:
        fleet_memory.validate_domain_access("work", is_write=False)
    assert "Domain firewall violation" in str(exc_info.value)
    assert "unauthorized domain 'work'" in str(exc_info.value)


def test_personal_node_denied_all_query(monkeypatch):
    """Personal node attempting to query 'all' domains must raise PermissionError."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")

    with pytest.raises(PermissionError) as exc_info:
        fleet_memory.validate_domain_access("all", is_write=False)
    assert "cannot request 'all'" in str(exc_info.value)


def test_work_node_allowed_domains(monkeypatch):
    """Enterprise Work node must be allowed to search work and shared domains."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    domains = fleet_memory.validate_domain_access(None, is_write=False)
    assert set(domains) == {"work", "shared"}

    domains = fleet_memory.validate_domain_access("work", is_write=False)
    assert domains == ["work"]

    domains = fleet_memory.validate_domain_access("shared", is_write=False)
    assert domains == ["shared"]


def test_work_node_denied_personal_query(monkeypatch):
    """Enterprise Work node attempting to query personal domain must raise PermissionError."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    with pytest.raises(PermissionError) as exc_info:
        fleet_memory.validate_domain_access("personal", is_write=False)
    assert "Domain firewall violation" in str(exc_info.value)
    assert "unauthorized domain 'personal'" in str(exc_info.value)


def test_work_node_denied_personal_store(monkeypatch):
    """Work node attempting to write into personal domain must raise PermissionError."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "work")

    with pytest.raises(PermissionError) as exc_info:
        fleet_memory.fleet_memory_store(
            text="Personal banking credentials",
            client_id="finance",
            slot_name="bank_info",
            target_domain="personal"
        )
    assert "Domain firewall violation" in str(exc_info.value)


def test_personal_node_denied_work_store(monkeypatch):
    """Personal node attempting to write into work domain must raise PermissionError."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "personal")

    with pytest.raises(PermissionError) as exc_info:
        fleet_memory.fleet_memory_store(
            text="Client API credentials",
            client_id="payment_gw",
            slot_name="api_keys",
            target_domain="work"
        )
    assert "Domain firewall violation" in str(exc_info.value)


def test_cloud_sentinel_all_access(monkeypatch):
    """Central Sentinel (domain='all') must be allowed to query and store across any domain."""
    monkeypatch.setattr(fleet_memory, "ENFORCED_DOMAIN", "all")

    # Unrestricted read
    domains = fleet_memory.validate_domain_access(None, is_write=False)
    assert domains == []

    # Can target work
    domains = fleet_memory.validate_domain_access("work", is_write=False)
    assert domains == ["work"]

    # Can target personal
    domains = fleet_memory.validate_domain_access("personal", is_write=False)
    assert domains == ["personal"]
