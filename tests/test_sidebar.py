def test_sidebar_has_a_collapse_toggle_and_short_wordmark(client):
    html = client.get("/dashboard").get_data(as_text=True)

    assert 'data-sidebar-toggle' in html
    assert 'aria-controls="sidebar"' in html
    assert 'class="sidebar-wordmark-short wordmark"' in html
    assert 'D<span class="accent-letter">S</span>V' in html


def test_every_live_nav_link_has_an_icon_and_a_tooltip_for_the_rail(client):
    html = client.get("/dashboard").get_data(as_text=True)
    nav = html.split('<nav class="sidebar-nav">')[1].split("</nav>")[0]
    links = nav.split("<a ")[1:]

    assert len(links) == 5
    for link in links:
        assert 'class="nav-icon"' in link
        assert 'title="' in link
        assert 'class="nav-label"' in link


def test_collapsed_state_is_applied_before_first_paint(client):
    html = client.get("/dashboard").get_data(as_text=True)

    # Restoring the saved state in <head> avoids the sidebar flashing open
    # on every page load.
    head = html.split("</head>")[0]
    assert "distrava.sidebarCollapsed" in head
    assert "sidebar-collapsed" in head
