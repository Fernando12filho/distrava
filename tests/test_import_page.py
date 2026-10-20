import re

from app.routes import ALLOWED_IMPORT_EXTENSIONS


def _page(client):
    return client.get("/import").get_data(as_text=True)


def test_import_page_explains_how_to_refresh_an_apple_health_export(client):
    html = _page(client)

    assert "Refreshing your data" in html
    assert "Export All Health Data" in html
    assert "AirDrop" in html


def test_guide_says_reimporting_is_safe(client):
    html = _page(client)

    assert "skipped, never duplicated" in html


def test_guide_explains_the_time_correction(client):
    assert "local time" in _page(client)


def test_page_only_offers_file_types_the_importer_accepts(client):
    html = _page(client)

    accept = re.search(r'accept="([^"]+)"', html).group(1)
    assert set(accept.split(",")) == ALLOWED_IMPORT_EXTENSIONS
    assert ".fit" not in html
