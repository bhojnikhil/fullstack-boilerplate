"""Version gate matrix and GET /v1/meta."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.appversion import parse_version
from app.factory import create_app


@pytest.fixture
async def gated(config, session_factory):
    gated_config = config.model_copy(
        update={"min_supported_app_version": "2.1.0", "latest_app_version": "2.5.0"}
    )
    app = create_app(gated_config, session_factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


def headers(platform: str | None, version: str | None) -> dict[str, str]:
    result = {}
    if platform is not None:
        result["X-Platform"] = platform
    if version is not None:
        result["X-App-Version"] = version
    return result


@pytest.mark.parametrize("platform", ["ios", "android", "IOS"])
@pytest.mark.parametrize("version", ["2.0.9", "1.9.99", "0.0.1", "2.0.0-rc.1"])
async def test_mobile_clients_below_the_minimum_get_426(gated, platform, version):
    response = await gated.get("/v1/items", headers=headers(platform, version))
    assert response.status_code == 426
    assert response.json() == {
        "error": {
            "code": "app_update_required",
            "message": "Update the app to continue",
            "details": {"min_supported_app_version": "2.1.0"},
        }
    }
    assert "X-Request-Id" in response.headers


@pytest.mark.parametrize(
    "version", ["2.1.0", "2.1", "2.1.1", "2.2.0", "3.0.0", "10.0.0", "2.1.0-rc.1"]
)
async def test_mobile_clients_at_or_above_the_minimum_continue(gated, version):
    # Past the gate, the request reaches authentication.
    response = await gated.get("/v1/items", headers=headers("android", version))
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("platform", "version"),
    [
        ("web", "0.0.1"),
        ("web", None),
        (None, "0.0.1"),
        ("other", "0.0.1"),
    ],
)
async def test_web_unidentified_and_unparseable_clients_are_not_gated(gated, platform, version):
    response = await gated.get("/v1/items", headers=headers(platform, version))
    assert response.status_code == 401


@pytest.mark.parametrize("platform", ["ios", "android"])
@pytest.mark.parametrize("version", [None, "", " ", "not-a-version", "1.2.3.4", "v2.1.0", "2.x"])
async def test_mobile_clients_with_a_missing_or_malformed_version_get_426(gated, platform, version):
    response = await gated.get("/v1/items", headers=headers(platform, version))
    assert response.status_code == 426
    assert response.json()["error"]["code"] == "app_update_required"


@pytest.mark.parametrize("path", ["/v1/meta", "/health", "/ready", "/openapi.json"])
async def test_meta_and_probes_stay_reachable_for_old_clients(gated, path):
    response = await gated.get(path, headers=headers("ios", "1.0.0"))
    assert response.status_code == 200


async def test_preflight_is_not_gated(gated):
    response = await gated.options(
        "/v1/items",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-app-version,x-platform",
            **headers("ios", "1.0.0"),
        },
    )
    assert response.status_code == 200
    assert "x-app-version" in response.headers["access-control-allow-headers"].lower()


async def test_gate_applies_to_every_v1_method(gated):
    response = await gated.post("/v1/auth/login", json={}, headers=headers("ios", "1.0.0"))
    assert response.status_code == 426


async def test_meta_reports_configured_versions(gated):
    response = await gated.get("/v1/meta")
    assert response.json() == {
        "min_supported_app_version": "2.1.0",
        "latest_app_version": "2.5.0",
    }


async def test_unversioned_mobile_clients_can_still_read_meta(gated):
    response = await gated.get("/v1/meta", headers=headers("android", None))
    assert response.status_code == 200


async def test_default_configuration_gates_nobody(client):
    assert (await client.get("/v1/meta")).json() == {
        "min_supported_app_version": "0.0.0",
        "latest_app_version": "1.0.0",
    }
    for version in ("0.0.1", None, "junk"):
        response = await client.get("/v1/items", headers=headers("ios", version))
        assert response.status_code == 401


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("1.2.3", (1, 2, 3)),
        ("1.2", (1, 2, 0)),
        ("7", (7, 0, 0)),
        ("1.2.3-beta.1", (1, 2, 3)),
        ("1.2.3+45", (1, 2, 3)),
        (" 1.2.3 ", (1, 2, 3)),
        ("", None),
        ("v1.2.3", None),
        ("1.2.3.4", None),
        ("a.b.c", None),
        ("1.2.x", None),
    ],
)
def test_parse_version(text, parsed):
    assert parse_version(text) == parsed
