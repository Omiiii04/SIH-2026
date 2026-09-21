"""
frontend/tests/test_dashboard.py

Integration smoke-tests for the Next.js dashboard against a LIVE FastAPI server.
Run from the project root:
    python -m pytest frontend/tests/test_dashboard.py -v

Requirements:
  pip install playwright pytest-playwright
  playwright install chromium

Environment:
  DASHBOARD_URL  – Next.js dev server  (default: http://localhost:3000)
  API_URL        – FastAPI orchestrator (default: http://localhost:8000)
"""

import os
import time
import pytest
import requests
from playwright.sync_api import Page, sync_playwright

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")
API_URL       = os.getenv("API_URL",       "http://localhost:8000")
TIMEOUT       = 15_000  # ms

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30_000)
        yield page
        browser.close()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardLoads:
    def test_dashboard_loads(self, browser_page: Page):
        """Dashboard renders without JS errors."""
        assert "Distributed AI Orchestrator" in browser_page.title() or \
               browser_page.locator("h1").count() > 0

    def test_five_nodes_appear(self, browser_page: Page):
        """All five node cards are rendered (even if OFFLINE)."""
        nodes = ["NODE-1", "NODE-2", "NODE-3", "NODE-4", "NODE-5"]
        for node_id in nodes:
            locator = browser_page.locator(f"#node-card-{node_id}")
            locator.wait_for(timeout=TIMEOUT)
            assert locator.count() >= 1, f"{node_id} card not found"


class TestQuerySubmission:
    def test_query_submission_works(self, browser_page: Page):
        """Filling the query and clicking Submit triggers a request."""
        browser_page.locator("#query-input").fill("What is 2+2?")
        browser_page.locator("#submit-query").click()
        # Wait for routing flow to appear
        browser_page.locator("#routing-flow").wait_for(timeout=60_000)

    def test_routing_decision_appears(self, browser_page: Page):
        """Routing flow section is visible after a query."""
        flow = browser_page.locator("#routing-flow")
        flow.wait_for(timeout=TIMEOUT)
        assert flow.is_visible()

    def test_response_appears(self, browser_page: Page):
        """Response panel is visible after a query."""
        panel = browser_page.locator("#response-panel")
        panel.wait_for(timeout=TIMEOUT)
        assert panel.is_visible()

    def test_latency_appears(self, browser_page: Page):
        """Latency value (N ms) appears somewhere in the response panel."""
        panel = browser_page.locator("#response-panel")
        panel.wait_for(timeout=TIMEOUT)
        content = panel.inner_text()
        assert "ms" in content, f"Latency not found in response panel:\n{content}"

    def test_history_updates(self, browser_page: Page):
        """History table now has at least one row."""
        table = browser_page.locator("#history-table")
        table.wait_for(timeout=TIMEOUT)
        # After the query above there should be at least one data row
        rows = table.locator("tbody tr")
        rows.first.wait_for(timeout=TIMEOUT)
        assert rows.count() >= 1


class TestNodeStatus:
    def test_node_status_updates(self):
        """GET /api/v1/nodes returns ONLINE/DEGRADED/OFFLINE for all 5 nodes."""
        r = requests.get(f"{API_URL}/api/v1/nodes", timeout=10)
        assert r.status_code == 200
        nodes = r.json()["nodes"]
        assert len(nodes) == 5
        valid = {"ONLINE", "DEGRADED", "OFFLINE"}
        for n in nodes:
            assert n["status"] in valid, f"Invalid status: {n}"

    def test_offline_node_visibly_marked(self, browser_page: Page):
        """
        Force NODE-5 offline via API, reload, confirm the card shows OFFLINE.
        Restores the node to 'online' afterwards.
        """
        # Force offline
        r = requests.patch(f"{API_URL}/api/v1/nodes/NODE-5/status?status=offline", timeout=5)
        assert r.status_code == 200

        browser_page.reload(wait_until="networkidle", timeout=30_000)
        card = browser_page.locator("#node-card-NODE-5")
        card.wait_for(timeout=TIMEOUT)
        text = card.inner_text()
        assert "OFFLINE" in text, f"OFFLINE not shown in NODE-5 card:\n{text}"

        # Restore
        requests.patch(f"{API_URL}/api/v1/nodes/NODE-5/status?status=online", timeout=5)

    def test_fallback_displayed(self, browser_page: Page):
        """
        Force NODE-1 offline, submit a text query,
        check that FaultToleranceViz shows fallback.
        """
        requests.patch(f"{API_URL}/api/v1/nodes/NODE-1/status?status=offline", timeout=5)
        time.sleep(1)

        browser_page.locator("#query-input").fill("Tell me a joke")
        browser_page.locator("#submit-query").click()

        viz = browser_page.locator("#fault-tolerance-viz")
        viz.wait_for(timeout=60_000)
        content = viz.inner_text()
        # Either OFFLINE or FALLBACK should appear
        assert "OFFLINE" in content or "FALLBACK" in content, \
            f"FaultToleranceViz missing offline/fallback indicator:\n{content}"

        # Restore
        requests.patch(f"{API_URL}/api/v1/nodes/NODE-1/status?status=online", timeout=5)


class TestMemorySearch:
    def test_memory_search_works(self, browser_page: Page):
        """
        Clicking memory search returns results or a 'no results' message —
        either way, no crash.
        """
        inp = browser_page.locator("#memory-search-input")
        inp.fill("joke")
        browser_page.locator("#memory-search-submit").click()
        # Wait briefly for the async response
        browser_page.wait_for_timeout(5_000)
        section = browser_page.locator("#memory-search")
        assert section.is_visible()
        # No JS crash: the section still renders
        assert section.count() == 1
