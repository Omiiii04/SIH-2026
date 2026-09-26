"""
tests/test_env_nodes.py
────────────────────────
Tests for orchestrator.env_nodes.parse_node_configs().

All tests pass an explicit `env` dict so they run without a .env file,
without a live database, and without network access.
"""
import pytest
from orchestrator.env_nodes import parse_node_configs, NodeEnvConfig


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — exactly 2 nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_two_nodes() -> None:
    env = {
        "NODE_1_URL": "http://192.168.1.1:1234",
        "NODE_2_URL": "http://192.168.1.2:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 2
    assert cfgs[0].node_id == "NODE-1"
    assert cfgs[1].node_id == "NODE-2"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — exactly 6 nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_six_nodes() -> None:
    env = {f"NODE_{i}_URL": f"http://10.0.0.{i}:1234" for i in range(1, 7)}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 6
    assert [c.node_id for c in cfgs] == [f"NODE-{i}" for i in range(1, 7)]


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — sparse indexes (gaps are fine)
# ─────────────────────────────────────────────────────────────────────────────

def test_sparse_indexes() -> None:
    env = {
        "NODE_1_URL":  "http://a:1234",
        "NODE_4_URL":  "http://b:1234",
        "NODE_9_URL":  "http://c:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 3
    assert [c.node_id for c in cfgs] == ["NODE-1", "NODE-4", "NODE-9"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — trailing slash is stripped (URL normalisation)
# ─────────────────────────────────────────────────────────────────────────────

def test_trailing_slash_stripped() -> None:
    env = {"NODE_1_URL": "http://192.168.1.110:1234/"}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1
    assert cfgs[0].url == "http://192.168.1.110:1234"


def test_no_trailing_slash_preserved() -> None:
    """URL without trailing slash is not modified."""
    env = {"NODE_1_URL": "http://192.168.1.110:1234"}
    cfgs = parse_node_configs(env)
    assert cfgs[0].url == "http://192.168.1.110:1234"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — optional metadata (NAME / PRIORITY / ENABLED)
# ─────────────────────────────────────────────────────────────────────────────

def test_optional_metadata_parsed() -> None:
    env = {
        "NODE_3_URL":      "http://10.0.0.3:1234",
        "NODE_3_NAME":     "Gaming Laptop",
        "NODE_3_PRIORITY": "2",
        "NODE_3_ENABLED":  "true",
    }
    cfg = parse_node_configs(env)[0]
    assert cfg.node_id   == "NODE-3"
    assert cfg.name      == "Gaming Laptop"
    assert cfg.priority  == 2
    assert cfg.enabled   is True


def test_defaults_when_metadata_omitted() -> None:
    """NAME/PRIORITY/ENABLED absent → sensible defaults."""
    env = {"NODE_5_URL": "http://10.0.0.5:1234"}
    cfg = parse_node_configs(env)[0]
    assert cfg.name     == "Node 5"   # default
    assert cfg.priority == 1          # default
    assert cfg.enabled  is True       # default


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — NODE_N_ENABLED=false creates a disabled entry
# ─────────────────────────────────────────────────────────────────────────────

def test_disabled_in_env() -> None:
    env = {
        "NODE_1_URL":     "http://a:1234",
        "NODE_1_ENABLED": "false",
    }
    cfg = parse_node_configs(env)[0]
    assert cfg.enabled is False


def test_disabled_variations() -> None:
    """0, no, off, FALSE are all treated as disabled."""
    for val in ("0", "no", "off", "FALSE", "False"):
        env = {"NODE_1_URL": "http://a:1234", "NODE_1_ENABLED": val}
        assert parse_node_configs(env)[0].enabled is False, f"failed for {val!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — invalid scheme is rejected
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_scheme_rejected() -> None:
    env = {"NODE_1_URL": "ftp://a:1234"}
    assert parse_node_configs(env) == []


def test_unsupported_scheme_rejected() -> None:
    env = {"NODE_1_URL": "ssh://host:22"}
    assert parse_node_configs(env) == []


def test_https_accepted() -> None:
    env = {"NODE_1_URL": "https://secure.host:443"}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1
    assert cfgs[0].url.startswith("https://")


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — empty URL is skipped
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_url_skipped() -> None:
    env = {
        "NODE_1_URL": "",
        "NODE_2_URL": "http://b:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1
    assert cfgs[0].node_id == "NODE-2"


def test_whitespace_only_url_skipped() -> None:
    env = {"NODE_1_URL": "   ", "NODE_2_URL": "http://b:1234"}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 9 — deterministic IDs for any index
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_id_high_index() -> None:
    env = {"NODE_14_URL": "http://x:1234"}
    cfg = parse_node_configs(env)[0]
    assert cfg.node_id == "NODE-14"
    assert cfg.index == 14


def test_deterministic_id_single_digit() -> None:
    env = {"NODE_7_URL": "http://x:1234"}
    cfg = parse_node_configs(env)[0]
    assert cfg.node_id == "NODE-7"


# ─────────────────────────────────────────────────────────────────────────────
# Test 10 — no maximum — high indexes accepted
# ─────────────────────────────────────────────────────────────────────────────

def test_no_hardcoded_maximum() -> None:
    """NODE_1, NODE_2, NODE_8, NODE_14 should all be accepted."""
    env = {
        "NODE_1_URL":  "http://10.0.0.1:1234",
        "NODE_2_URL":  "http://10.0.0.2:1234",
        "NODE_8_URL":  "http://10.0.0.8:1234",
        "NODE_14_URL": "http://10.0.0.14:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 4
    ids = [c.node_id for c in cfgs]
    assert ids == ["NODE-1", "NODE-2", "NODE-8", "NODE-14"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 11 — non-NODE_ keys are ignored
# ─────────────────────────────────────────────────────────────────────────────

def test_non_node_keys_ignored() -> None:
    env = {
        "NODE_1_URL":     "http://a:1234",
        "POSTGRES_HOST":  "localhost",
        "DEBUG":          "false",
        "NODE_1_NAME":    "My Node",
        "APP_NAME":       "SIH-2026",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1
    assert cfgs[0].node_id == "NODE-1"


# ─────────────────────────────────────────────────────────────────────────────
# Test 12 — empty env → empty list (no crash)
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_env_returns_empty_list() -> None:
    assert parse_node_configs({}) == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 13 — sort order by index (not insertion order)
# ─────────────────────────────────────────────────────────────────────────────

def test_sorted_by_index() -> None:
    """Results must be sorted by index regardless of dict iteration order."""
    env = {
        "NODE_9_URL": "http://c:1234",
        "NODE_1_URL": "http://a:1234",
        "NODE_4_URL": "http://b:1234",
    }
    cfgs = parse_node_configs(env)
    assert [c.index for c in cfgs] == [1, 4, 9]


# ─────────────────────────────────────────────────────────────────────────────
# Test 14 — NodeEnvConfig fields have correct types
# ─────────────────────────────────────────────────────────────────────────────

def test_config_field_types() -> None:
    env = {
        "NODE_2_URL":      "http://10.0.0.2:1234",
        "NODE_2_PRIORITY": "3",
        "NODE_2_ENABLED":  "true",
    }
    cfg = parse_node_configs(env)[0]
    assert isinstance(cfg.index, int)
    assert isinstance(cfg.node_id, str)
    assert isinstance(cfg.url, str)
    assert isinstance(cfg.name, str)
    assert isinstance(cfg.priority, int)
    assert isinstance(cfg.enabled, bool)
