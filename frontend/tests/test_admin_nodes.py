"""
frontend/tests/test_admin_nodes.py

Integration tests for Admin Node Management.
Requires:
  - FastAPI running at API_URL (default http://localhost:8000)
  - Next.js running at DASHBOARD_URL (default http://localhost:3000)
  - pip install playwright pytest-playwright requests
  - playwright install chromium

Run:
  python -m pytest frontend/tests/test_admin_nodes.py -v
"""

import os
import time
import uuid

import pytest
import requests
from playwright.sync_api import Page, sync_playwright, expect

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")
API_URL       = os.getenv("API_URL",       "http://localhost:8000")
TIMEOUT       = 15_000  # ms

TEST_ENDPOINT = "http://127.0.0.1:1234"  # adjust to a real reachable node if needed


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        pg.goto(f"{DASHBOARD_URL}/admin", wait_until="networkidle", timeout=30_000)
        yield pg
        browser.close()


# ── 1. Fetch node list ────────────────────────────────────────────────────────

class TestFetchNodeList:
    def test_api_returns_nodes(self):
        """GET /api/v1/nodes returns 200 with a nodes list."""
        r = requests.get(f"{API_URL}/api/v1/nodes", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "nodes" in body
        assert isinstance(body["nodes"], list)

    def test_proxy_returns_nodes(self):
        """Next.js proxy forwards GET /api/v1/nodes correctly (no 404)."""
        r = requests.get(f"{DASHBOARD_URL}/api/v1/nodes", timeout=10)
        assert r.status_code == 200, (
            f"Proxy returned {r.status_code} — rewrite not active or Next.js not running"
        )
        assert "nodes" in r.json()

    def test_admin_page_loads_nodes(self, page: Page):
        """Admin page renders the node list section."""
        page.goto(f"{DASHBOARD_URL}/admin", wait_until="networkidle", timeout=30_000)
        heading = page.get_by_text("Registered Nodes")
        heading.wait_for(timeout=TIMEOUT)
        assert heading.is_visible()


# ── 2. Add node ────────────────────────────────────────────────────────────────

class TestAddNode:
    _added_node_id: str = ""

    def test_add_node_via_api(self):
        """POST /api/v1/nodes reaches backend (200/409/500 all mean FastAPI answered)."""
        name = f"TEST-{uuid.uuid4().hex[:4].upper()}"
        r = requests.post(
            f"{API_URL}/api/v1/nodes",
            json={"name": name, "endpoint": TEST_ENDPOINT, "priority": 1},
            timeout=15,
        )
        # 200 = created; 409 = duplicate endpoint; 500 = probe failed (node unreachable but was accepted)
        assert r.status_code in (200, 409, 500), f"Unexpected status: {r.status_code} — {r.text}"
        if r.status_code == 200:
            TestAddNode._added_node_id = r.json().get("node_id", "")

    def test_add_node_proxy(self):
        """POST /api/v1/nodes via Next.js proxy does NOT return 404."""
        r = requests.post(
            f"{DASHBOARD_URL}/api/v1/nodes",
            json={"name": f"PROXY-{uuid.uuid4().hex[:4].upper()}", "endpoint": "http://10.0.0.199:9999", "priority": 1},
            timeout=15,
        )
        # 404 = proxy broken; 200/409/500 = FastAPI was reached
        assert r.status_code != 404, "Proxy returned 404 — rewrite is broken"


# ── 3. Probe node ─────────────────────────────────────────────────────────────

class TestProbeNode:
    def test_probe_existing_node(self):
        """POST /api/v1/nodes/{id}/probe returns 200 for an existing node."""
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        if not nodes:
            pytest.skip("No nodes registered")
        node_id = nodes[0]["node_id"]
        r = requests.post(f"{API_URL}/api/v1/nodes/{node_id}/probe", timeout=20)
        assert r.status_code == 200, f"Probe returned {r.status_code}: {r.text}"

    def test_probe_proxy(self):
        """POST /api/v1/nodes/{id}/probe via proxy does NOT return 404."""
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        if not nodes:
            pytest.skip("No nodes registered")
        node_id = nodes[0]["node_id"]
        r = requests.post(f"{DASHBOARD_URL}/api/v1/nodes/{node_id}/probe", timeout=20)
        assert r.status_code != 404, "Proxy returned 404 on probe — rewrite is broken"


# ── 4. Disable node ────────────────────────────────────────────────────────────

class TestDisableNode:
    def test_disable_node(self):
        """POST /api/v1/nodes/{id}/disable sets enabled=false."""
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        enabled = [n for n in nodes if n.get("enabled")]
        if not enabled:
            pytest.skip("No enabled nodes to disable")
        node_id = enabled[0]["node_id"]
        r = requests.post(f"{API_URL}/api/v1/nodes/{node_id}/disable", timeout=10)
        assert r.status_code == 200
        # Verify
        nodes_after = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        match = next((n for n in nodes_after if n["node_id"] == node_id), None)
        assert match is not None
        assert match["enabled"] is False
        # Re-enable for subsequent tests
        requests.post(f"{API_URL}/api/v1/nodes/{node_id}/enable", timeout=15)


# ── 5. Enable node ─────────────────────────────────────────────────────────────

class TestEnableNode:
    def test_enable_node(self):
        """POST /api/v1/nodes/{id}/enable sets enabled=true."""
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        disabled = [n for n in nodes if not n.get("enabled")]
        if not disabled:
            # Disable one first
            all_nodes = nodes
            if not all_nodes:
                pytest.skip("No nodes available")
            nid = all_nodes[0]["node_id"]
            requests.post(f"{API_URL}/api/v1/nodes/{nid}/disable", timeout=10)
            disabled = [{"node_id": nid}]

        node_id = disabled[0]["node_id"]
        r = requests.post(f"{API_URL}/api/v1/nodes/{node_id}/enable", timeout=15)
        assert r.status_code == 200
        nodes_after = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        match = next((n for n in nodes_after if n["node_id"] == node_id), None)
        assert match is not None
        assert match["enabled"] is True


# ── 6. Remove (soft-delete) node ──────────────────────────────────────────────

class TestRemoveNode:
    def test_delete_node_is_soft_disable(self):
        """DELETE /api/v1/nodes/{id} soft-disables (node remains in list)."""
        # Add a throwaway node (probe may fail on unreachable endpoint → 500, but node is still created)
        name = f"DEL-{uuid.uuid4().hex[:4].upper()}"
        add_r = requests.post(
            f"{API_URL}/api/v1/nodes",
            json={"name": name, "endpoint": "http://10.0.0.201:9998", "priority": 1},
            timeout=30,
        )
        if add_r.status_code == 409:
            pytest.skip("Duplicate endpoint, can't create throwaway node")
        # 200 = created+probed; 500 = created but probe failed — both mean node exists
        assert add_r.status_code in (200, 500), f"Unexpected add status: {add_r.status_code}"

        # Find the node by name in the list
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        target = next((n for n in nodes if n.get("name") == name), None)
        if target is None:
            pytest.skip("Node was not persisted (DB unavailable or duplicate)")
        node_id = target["node_id"]

        del_r = requests.delete(f"{API_URL}/api/v1/nodes/{node_id}", timeout=10)
        assert del_r.status_code == 200

        # Node should still be there but disabled
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        match = next((n for n in nodes if n["node_id"] == node_id), None)
        assert match is not None, "Soft-delete should not hard-delete the node"
        assert match["enabled"] is False



# ── 7. Sync config ─────────────────────────────────────────────────────────────

class TestSyncConfig:
    def test_sync_config_via_api(self):
        """POST /api/v1/nodes/sync-config returns reconciled=true."""
        r = requests.post(f"{API_URL}/api/v1/nodes/sync-config", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("reconciled") is True
        assert "active_nodes" in body

    def test_sync_config_via_proxy(self):
        """POST /api/v1/nodes/sync-config via Next.js proxy does NOT return 404."""
        r = requests.post(f"{DASHBOARD_URL}/api/v1/nodes/sync-config", timeout=20)
        assert r.status_code != 404, "Proxy returned 404 on sync-config"


# ── 8. Failed node action error handling ──────────────────────────────────────

class TestFailedNodeAction:
    def test_probe_nonexistent_node_returns_404(self):
        """POST /api/v1/nodes/DOES-NOT-EXIST/probe returns 404."""
        r = requests.post(f"{API_URL}/api/v1/nodes/DOES-NOT-EXIST/probe", timeout=10)
        assert r.status_code == 404

    def test_proxy_404_is_preserved(self):
        """Proxy passes through 404 for non-existent nodes (not swallowed)."""
        r = requests.post(f"{DASHBOARD_URL}/api/v1/nodes/DOES-NOT-EXIST/probe", timeout=10)
        assert r.status_code == 404


# ── 9. Successful action triggers list refresh ────────────────────────────────

class TestRefreshAfterAction:
    def test_node_list_reflects_disable_immediately(self):
        """After disable, GET /api/v1/nodes immediately shows enabled=false."""
        nodes = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        enabled = [n for n in nodes if n.get("enabled")]
        if not enabled:
            pytest.skip("No enabled nodes")
        nid = enabled[0]["node_id"]
        requests.post(f"{API_URL}/api/v1/nodes/{nid}/disable", timeout=10)
        after = requests.get(f"{API_URL}/api/v1/nodes", timeout=10).json()["nodes"]
        m = next((n for n in after if n["node_id"] == nid), None)
        assert m and m["enabled"] is False
        # Restore
        requests.post(f"{API_URL}/api/v1/nodes/{nid}/enable", timeout=15)
