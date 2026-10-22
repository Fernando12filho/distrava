def test_sidebar_has_a_collapse_toggle_and_short_wordmark(client):
    html = client.get("/dashboard").get_data(as_text=True)

    assert 'data-sidebar-toggle' in html
    assert 'aria-controls="sidebar"' in html
    assert 'class="sidebar-wordmark-short wordmark"' in html
    assert 'D<span class="accent-letter">S</span>V' in html


def test_collapsed_state_is_applied_before_first_paint(client):
    html = client.get("/dashboard").get_data(as_text=True)

    # Restoring the saved state in <head> avoids the sidebar flashing open
    # on every page load.
    head = html.split("</head>")[0]
    assert "distrava.sidebarCollapsed" in head
    assert "sidebar-collapsed" in head
