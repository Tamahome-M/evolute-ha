"""Drive the real HA frontend and config flow in Chromium, including first use."""

import json
import os
import re
from pathlib import Path

import pytest
from homeassistant.components.onboarding.const import STEPS
from homeassistant.setup import async_setup_component

from custom_components.evolute.const import BASE_URL, DOMAIN, LOGIN_URL

pytestmark = [
    pytest.mark.usefixtures("enable_custom_integrations"),
    pytest.mark.skipif(
        os.environ.get("EVOLUTE_BROWSER_TESTS") != "1",
        reason="The browser job installs the real HA frontend and Chromium",
    ),
]


@pytest.mark.parametrize(
    "viewport",
    [{"width": 1280, "height": 1000}, {"width": 390, "height": 844}],
    ids=["desktop", "mobile"],
)
async def test_first_sms_choice_opens_working_panel(
    hass,
    hass_client,
    hass_access_token,
    hass_storage,
    requests_mock,
    mock_setup_entry,
    viewport,
):
    """Reproduce the reported path without preloading any Evolute JS module."""
    playwright = pytest.importorskip("playwright.async_api")
    hass_storage["onboarding"] = {"version": 4, "data": {"done": STEPS}}
    assert await async_setup_component(hass, "frontend", {"frontend": {}})
    client = await hass_client()
    base = str(client.make_url("/")).rstrip("/")
    assert DOMAIN not in hass.config.components
    requests_mock.post(
        LOGIN_URL, json={"accessToken": "access", "refreshToken": "refresh"}
    )
    requests_mock.post(
        f"{BASE_URL}/car-service/car/v2/search",
        json={
            "rows": [{"_id": "car-1", "carModel": {"name": "i-JOY"}}],
            "total": 1,
        },
    )
    artifacts = Path("artifacts") / str(viewport["width"])
    artifacts.mkdir(parents=True, exist_ok=True)
    async with playwright.async_playwright() as driver:
        browser = await driver.chromium.launch(args=["--no-sandbox"])
        context = await browser.new_context(locale="ru-RU", viewport=viewport)
        # Only the third-party SMS/CAPTCHA page and vehicle API are mocked.
        # HA's frontend, authentication, HTTP API and panel loader are real.
        await context.route(
            "https://app.evassist.ru/**",
            lambda route: route.fulfill(
                content_type="text/html; charset=utf-8",
                body="<h1>EVAssist</h1><label>Телефон<input type='tel'></label>"
                "<button onclick=\"document.querySelector('p').textContent='СМС отправлена'\">Запросить СМС</button><p></p>",
            ),
        )
        tokens = {
            "access_token": hass_access_token,
            "token_type": "Bearer",
            "refresh_token": "browser-test",
            "expires": 9999999999999,
            "expires_in": 1800,
            "hassUrl": base,
            "client_id": base + "/",
        }
        await context.add_init_script(
            "localStorage.setItem('hassTokens', "
            + json.dumps(json.dumps(tokens))
            + ");"
        )
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/config/integrations/dashboard")
        await page.get_by_role(
            "button", name=re.compile("Добавить интеграцию|Add integration")
        ).first.click(timeout=45000)
        await page.screenshot(path=str(artifacts / "integration-picker.png"))
        await page.get_by_role("textbox").last.fill("Evolute")
        await page.get_by_text("Evolute", exact=True).last.click()
        await page.screenshot(path=str(artifacts / "login-method.png"))
        # This fails on v1.2.14b: it returns a blank form instead of opening a page.
        async with context.expect_page(timeout=15000) as opened:
            await page.get_by_text(
                re.compile("По номеру телефона и СМС|Phone number and SMS code"),
                exact=True,
            ).click()
        panel = await opened.value
        panel.on("pageerror", lambda error: errors.append(str(error)))
        await panel.wait_for_load_state()
        await panel.locator("evolute-login-panel-v8 iframe").wait_for(
            state="visible", timeout=45000
        )
        phone = panel.get_by_label("Номер телефона", exact=True)
        code = panel.get_by_label("Код из СМС", exact=True)
        assert await phone.is_visible() and await code.is_visible()
        assert await phone.is_enabled() and await code.is_enabled()
        assert (
            await panel.get_by_role("button", name=re.compile("СМС получено")).count()
            == 0
        )
        frame_box = await panel.locator("iframe").bounding_box()
        phone_box = await phone.bounding_box()
        assert phone_box["y"] >= frame_box["y"] + frame_box["height"]
        assert phone_box["x"] >= 0
        assert phone_box["x"] + phone_box["width"] <= viewport["width"]
        await panel.screenshot(path=str(artifacts / "login-screen.png"), full_page=True)
        frame = panel.frame_locator("iframe")
        await frame.get_by_role("button", name="Запросить СМС").click()
        await phone.fill("+79991234567")
        await code.fill("0123")
        assert await panel.locator("iframe").count() == 1
        assert await frame.get_by_text("СМС отправлена", exact=True).count() == 1
        await panel.screenshot(path=str(artifacts / "login-code.png"))
        await panel.get_by_role("button", name="Войти", exact=True).click()
        await panel.wait_for_url(
            "**/config/integrations/integration/evolute", timeout=30000
        )
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert not any("MISSING_VALUE" in error for error in errors), errors
        await browser.close()
