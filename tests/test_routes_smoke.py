from app.models import Activity
from regression_fixtures import seed_best_effort_runs, seed_load_schedule

# Every GET page that existed before the coach work began. A route that
# disappears fails here; a new route is picked up by the url_map sweep below.
PRE_COACH_GET_ENDPOINTS = {
    "main.index",
    "main.activity_list",
    "main.activity_detail",
    "main.activity_stream",
    "main.import_page",
    "main.settings_page",
    "main.dashboard",
}


def _get_urls(app, activity_id):
    urls = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint == "static":
            continue
        args = {"activity_id": activity_id} if "activity_id" in rule.arguments else {}
        assert set(args) == set(rule.arguments), f"smoke test can't fill args for {rule.rule}"
        urls.append(rule.build(args, append_unknown=False)[1])
    return urls


def test_pre_coach_endpoints_still_exist(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}

    assert PRE_COACH_GET_ENDPOINTS <= endpoints


def test_every_get_route_returns_200_with_data(app, client, db_session):
    seed_load_schedule(db_session)
    seed_best_effort_runs(db_session)
    run = db_session.query(Activity).filter(Activity.activity_type == "Run").first()

    for url in _get_urls(app, run.id):
        assert client.get(url, follow_redirects=True).status_code == 200, url


def test_every_get_route_without_an_id_returns_200_on_empty_database(app, client):
    for url in _get_urls(app, activity_id=1):
        expected = 404 if "/activities/1" in url else 200
        assert client.get(url, follow_redirects=True).status_code == expected, url
