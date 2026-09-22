from __future__ import annotations

import pytest

from aaw_telemetry.errors import ApiError
from aaw_telemetry.services.telemetry_filters import (
    TelemetryFilterService,
    evaluate_filters,
    validate_filters,
)


def _valid_filters() -> dict:
    return {
        "max_file_bytes": 10_485_760,
        "excluded_dirs": ["node_modules", ".idea", "!vendor"],
        "excluded_suffixes": [".md", ".log", ".png", ".pdf"],
    }


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/anomalies/admin/login", json={"password": "123456"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


# ── validation ──────────────────────────────────────────────


def test_validate_filters_accepts_valid_payload() -> None:
    validated = validate_filters(_valid_filters())
    assert validated["max_file_bytes"] == 10_485_760
    assert set(validated) == {
        "max_file_bytes",
        "excluded_dirs",
        "excluded_suffixes",
    }


def test_validate_filters_merges_legacy_suffix_keys() -> None:
    filters = _valid_filters() | {
        "diff_excluded_suffixes": [".md", ".rst"],
        "snapshot_excluded_suffixes": [".png", ".md"],
    }
    filters.pop("excluded_suffixes")
    validated = validate_filters(filters)
    assert validated["excluded_suffixes"] == [".md", ".rst", ".png"]


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"max_file_bytes": 0}, id="size-too-small"),
        pytest.param({"max_file_bytes": "big"}, id="size-not-int"),
        pytest.param({"excluded_dirs": ["/etc"]}, id="dir-absolute"),
        pytest.param({"excluded_dirs": ["../outside"]}, id="dir-parent"),
        pytest.param({"excluded_suffixes": ["md"]}, id="suffix-no-dot"),
        pytest.param({"excluded_suffixes": [".tar.gz"]}, id="suffix-double-dot"),
        pytest.param({"unknown_key": []}, id="unknown-key"),
    ],
)
def test_validate_filters_rejects_bad_payloads(mutation: dict) -> None:
    filters = _valid_filters() | mutation
    with pytest.raises(ApiError) as excinfo:
        validate_filters(filters)
    assert excinfo.value.code == "FILTER_INVALID"


# ── evaluate (rule preview) ─────────────────────────────────


def test_evaluate_filters_orders_the_decision_chain() -> None:
    decisions = evaluate_filters(
        _valid_filters(),
        [
            ".aaw/telemetry/pending/x.json",
            "node_modules/pkg/index.js",
            "assets/logo.png",
            "docs/readme.md",
            "src/main.py",
        ],
    )
    by_path = {decision.path: decision for decision in decisions}
    assert by_path[".aaw/telemetry/pending/x.json"].rule == "internal"
    assert by_path["node_modules/pkg/index.js"] == (
        by_path["node_modules/pkg/index.js"].__class__(
            "node_modules/pkg/index.js", True, "dir_excluded", "node_modules"
        )
    )
    assert by_path["assets/logo.png"].rule == "suffix_excluded"
    assert by_path["docs/readme.md"].rule == "suffix_excluded"
    assert by_path["src/main.py"].excluded is False


# ── API surface ─────────────────────────────────────────────


def test_public_config_endpoint_404_before_first_save(client) -> None:
    response = client.get("/api/v1/telemetry/config")
    assert response.status_code == 404
    assert response.json()["code"] == "FILTER_CONFIG_NOT_FOUND"


def test_save_then_public_pull_returns_latest_version(client) -> None:
    headers = _admin(client)
    saved = client.put(
        "/api/v1/admin/telemetry-config", headers=headers, json={"filters": _valid_filters()}
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["version"] == 1
    assert body["updated_by"] == "系统管理员"

    pulled = client.get("/api/v1/telemetry/config")
    assert pulled.status_code == 200
    assert pulled.json()["version"] == 1
    assert pulled.json()["filters"] == _valid_filters()

    again = client.put(
        "/api/v1/admin/telemetry-config", headers=headers, json={"filters": _valid_filters()}
    )
    assert again.json()["version"] == 2
    assert client.get("/api/v1/telemetry/config").json()["version"] == 2


def test_save_rejects_invalid_filters_without_writing(client) -> None:
    headers = _admin(client)
    filters = _valid_filters() | {"sensitive_names": ["("]}
    rejected = client.put(
        "/api/v1/admin/telemetry-config", headers=headers, json={"filters": filters}
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "FILTER_INVALID"
    assert client.get("/api/v1/telemetry/config").status_code == 404


def test_save_requires_admin_session(client) -> None:
    denied = client.put("/api/v1/admin/telemetry-config", json={"filters": _valid_filters()})
    assert denied.status_code == 401
    # GET 不需要管理员（配置本身是公开只读）
    assert client.get("/api/v1/admin/telemetry-config").status_code == 404


def test_history_lists_versions_newest_first(client) -> None:
    headers = _admin(client)
    for size in (10_485_760, 20_971_520):
        client.put(
            "/api/v1/admin/telemetry-config",
            headers=headers,
            json={"filters": _valid_filters() | {"max_file_bytes": size}},
        )
    history = client.get("/api/v1/admin/telemetry-config/history").json()["items"]
    assert [item["version"] for item in history] == [2, 1]
    assert history[0]["filters"]["max_file_bytes"] == 20_971_520


def test_preview_endpoint_evaluates_candidate_paths(client) -> None:
    headers = _admin(client)
    response = client.post(
        "/api/v1/admin/telemetry-config/test",
        headers=headers,
        json={
            "filters": _valid_filters(),
            "paths": ["node_modules/x.js", "src/main.py", "logo.png"],
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items[0]["excluded"] is True and items[0]["rule"] == "dir_excluded"
    assert items[1]["excluded"] is False
    assert items[2]["excluded"] is True and items[2]["rule"] == "suffix_excluded"


def test_preview_rejects_invalid_filters(client) -> None:
    headers = _admin(client)
    response = client.post(
        "/api/v1/admin/telemetry-config/test",
        headers=headers,
        json={"filters": _valid_filters() | {"sensitive_names": ["("]}, "paths": []},
    )
    assert response.status_code == 422
