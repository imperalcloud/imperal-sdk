import pytest
from imperal_sdk.extension import Extension
from imperal_sdk.ui.display import Text


def test_panel_stale_while_revalidate_metadata():
    ext = Extension("test-caching")

    @ext.panel(
        "dashboard_stats",
        slot="center",
        title="Dashboard",
        stale_while_revalidate=True,
        cache_ttl=120,
    )
    def render_panel(ctx):
        return Text("Dashboard content")

    assert "dashboard_stats" in ext._panels
    panel_cfg = ext._panels["dashboard_stats"]
    assert panel_cfg["slot"] == "center"
    assert panel_cfg["stale_while_revalidate"] is True
    assert panel_cfg["cache_ttl"] == 120
