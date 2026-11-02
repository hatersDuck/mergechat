from __future__ import annotations

from fastapi.testclient import TestClient

from mergechat.api.app import create_app
from mergechat.config import Settings


def test_api_token_is_enforced_when_configured(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        session_encryption_key="test-passphrase",
        jev_api_key="",
        api_token="test-api-token",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/accounts").status_code == 401
        authorized = client.get(
            "/accounts",
            headers={"Authorization": "Bearer test-api-token"},
        )
        assert authorized.status_code == 200


def test_web_ui_is_public(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ui.db'}",
        session_encryption_key="test-passphrase",
        jev_api_key="",
        api_token="test-api-token",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        index = client.get("/ui/")
        assert index.status_code == 200
        assert "MergeChat" in index.text

        assert client.get("/ui/app.js").status_code == 200
        assert client.get("/ui/styles.css").status_code == 200
        assert client.get("/info").status_code == 200
        assert client.get("/").status_code == 200


def test_account_creation_and_health(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        session_encryption_key="test-passphrase",
        jev_api_key="",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

        created = client.post("/accounts", json={"display_name": "Owner"})
        assert created.status_code == 201
        account = created.json()
        assert account["status"] == "created"
        assert account["has_session"] is False

        accounts = client.get("/accounts").json()
        assert [item["id"] for item in accounts] == [account["id"]]

        missing = client.get("/accounts/does-not-exist/status")
        assert missing.status_code == 404

        missing_classification = client.get("/messages/does-not-exist/classification")
        assert missing_classification.status_code == 404

        selection = client.post(
            f"/accounts/{account['id']}/chats/selection",
            json={"chat_ids": []},
        )
        assert selection.status_code == 409

        assert client.delete(f"/accounts/{account['id']}/session").status_code == 204
        assert client.delete(f"/accounts/{account['id']}").status_code == 204
        assert client.get(f"/accounts/{account['id']}/status").status_code == 404
