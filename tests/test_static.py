from fastapi.testclient import TestClient


def test_root_serves_the_board_html(app_client: TestClient) -> None:
    response = app_client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "humanq" in response.text


def test_static_app_js_is_served(app_client: TestClient) -> None:
    response = app_client.get("/static/app.js")
    assert response.status_code == 200


def test_static_styles_are_served(app_client: TestClient) -> None:
    response = app_client.get("/static/styles.css")
    assert response.status_code == 200
