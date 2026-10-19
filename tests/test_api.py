"""Test authentication and existing command behavior at the HTTP boundary."""

import pytest
import requests

from custom_components.evolute.api import (
    EvolUteAPIError,
    EvolUteAuthError,
    EvolUteClient,
    EvolUteRateLimitError,
)
from custom_components.evolute.const import BASE_URL, LOGIN_URL, REFRESH_URL

SEARCH_URL = f"{BASE_URL}/car-service/car/v2/search"


def test_sms_login_and_cookies(requests_mock):
    """The app's phone/code payload yields the session used for car requests."""
    requests_mock.post(
        LOGIN_URL,
        json={"accessToken": "access", "refreshToken": "refresh"},
        headers={"Set-Cookie": "evy-platform-access=stale; Path=/"},
    )
    requests_mock.post(SEARCH_URL, json={"rows": [{"_id": "car"}], "total": 1})
    client = EvolUteClient()
    try:
        assert client.login("79991234567", "0123") == ("access", "refresh")
        assert requests_mock.request_history[0].json() == {
            "phone": "79991234567",
            "code": "0123",
        }
        assert client.fetch_cars() == [{"_id": "car"}]
        request = requests_mock.last_request
        assert request.headers["x-app"] == "web"
        assert request.headers["Cookie"].count("evy-platform-access=") == 1
        assert "evy-platform-access=access" in request.headers["Cookie"]
        assert "evy-platform-refresh=refresh" in request.headers["Cookie"]
    finally:
        client.close()


@pytest.mark.parametrize(
    "status,error",
    [
        (400, EvolUteAuthError),
        (401, EvolUteAuthError),
        (403, EvolUteAuthError),
        (429, EvolUteRateLimitError),
        (500, EvolUteAPIError),
    ],
)
def test_login_http_errors(requests_mock, status, error):
    """Classify rejected codes, throttling and service failures without secrets."""
    requests_mock.post(LOGIN_URL, status_code=status, text="sensitive server response")
    client = EvolUteClient()
    try:
        with pytest.raises(error) as exc:
            client.login("79991234567", "0123")
        assert "sensitive" not in str(exc.value)
        assert "79991234567" not in str(exc.value)
        assert "0123" not in str(exc.value)
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"accessToken": "new"},
        {"accessToken": "new", "refreshToken": ""},
        {"accessToken": 123, "refreshToken": "refresh"},
    ],
)
def test_malformed_token_pair_is_atomic(requests_mock, payload):
    """Malformed responses must not leave the client with half a new session."""
    requests_mock.post(REFRESH_URL, json=payload)
    client = EvolUteClient("car", "old-access", "old-refresh")
    try:
        with pytest.raises(EvolUteAPIError):
            client.refresh_tokens()
        assert (client.access_token, client.refresh_token) == (
            "old-access",
            "old-refresh",
        )
    finally:
        client.close()


@pytest.mark.parametrize(
    "response",
    [
        {"text": "not JSON"},
        {"exc": requests.Timeout},
    ],
)
def test_login_bad_json_and_timeout(requests_mock, response):
    """Transport and decoding errors use the API error contract."""
    requests_mock.post(LOGIN_URL, **response)
    client = EvolUteClient()
    try:
        with pytest.raises(EvolUteAPIError):
            client.login("79991234567", "0123")
    finally:
        client.close()


def test_car_pagination(requests_mock):
    """Discover all pages rather than silently omitting additional cars."""
    requests_mock.post(
        SEARCH_URL,
        [
            {"json": {"rows": [{"_id": "first"}], "total": 2}},
            {"json": {"rows": [{"_id": "second"}], "total": 2}},
        ],
    )
    client = EvolUteClient()
    try:
        assert client.fetch_cars() == [{"_id": "first"}, {"_id": "second"}]
        assert [r.json()["offset"] for r in requests_mock.request_history] == [0, 1]
        assert requests_mock.last_request.json()["addSensors"] is False
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"rows": "invalid", "total": 1},
        {"rows": [{}], "total": 1},
        {"rows": [], "total": 1},
        {"rows": [], "total": -1},
    ],
)
def test_invalid_car_list(requests_mock, payload):
    """Distinguish broken API responses from a genuinely empty account."""
    requests_mock.post(SEARCH_URL, json=payload)
    client = EvolUteClient()
    try:
        with pytest.raises(EvolUteAPIError):
            client.fetch_cars()
    finally:
        client.close()


def test_empty_command_response(requests_mock):
    """Authentication changes must preserve successful bodyless commands."""
    url = f"{BASE_URL}/car-service/tbox/v1/car/blink"
    requests_mock.post(url, status_code=204)
    client = EvolUteClient("car", "access", "refresh")
    try:
        assert client.tbox_command("blink", timeout=60) is None
        assert requests_mock.last_request.json() == {}
        assert requests_mock.last_request.timeout == 60
    finally:
        client.close()
