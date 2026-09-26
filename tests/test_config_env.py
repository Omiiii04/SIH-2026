"""
tests/test_config_env.py
────────────────────────
Tests for dynamic .env configuration parsing.
Replaces the old test_env_nodes.py.
"""
import pytest
from orchestrator.env_nodes import parse_node_configs

def test_two_nodes() -> None:
    env = {
        "NODE_1_URL": "http://192.168.1.1:1234",
        "NODE_2_URL": "http://192.168.1.2:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 2
    assert cfgs[0].node_id == "NODE-1"
    assert cfgs[1].node_id == "NODE-2"

def test_six_nodes() -> None:
    env = {f"NODE_{i}_URL": f"http://10.0.0.{i}:1234" for i in range(1, 7)}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 6
    assert [c.node_id for c in cfgs] == [f"NODE-{i}" for i in range(1, 7)]

def test_sparse_indexes() -> None:
    env = {
        "NODE_1_URL":  "http://a:1234",
        "NODE_4_URL":  "http://b:1234",
        "NODE_9_URL":  "http://c:1234",
    }
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 3
    assert [c.node_id for c in cfgs] == ["NODE-1", "NODE-4", "NODE-9"]

def test_trailing_slash_stripped() -> None:
    env = {"NODE_1_URL": "http://192.168.1.110:1234/"}
    cfgs = parse_node_configs(env)
    assert len(cfgs) == 1
    assert cfgs[0].url == "http://192.168.1.110:1234"

def test_no_trailing_slash_preserved() -> None:
    env = {"NODE_1_URL": "http://192.168.1.110:1234"}
    cfgs = parse_node_configs(env)
    assert cfgs[0].url == "http://192.168.1.110:1234"

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

def test_disabled_in_env() -> None:
    env = {
        "NODE_1_URL":     "http://a:1234",
        "NODE_1_ENABLED": "false",
    }
    cfg = parse_node_configs(env)[0]
    assert cfg.enabled is False

def test_invalid_scheme_rejected() -> None:
    env = {"NODE_1_URL": "ftp://a:1234"}
    assert parse_node_configs(env) == []

def test_deterministic_id_high_index() -> None:
    env = {"NODE_14_URL": "http://x:1234"}
    cfg = parse_node_configs(env)[0]
    assert cfg.node_id == "NODE-14"
    assert cfg.index == 14
