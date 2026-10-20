import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { Window } from "happy-dom";

const source = await readFile(new URL("../custom_components/evolute/frontend/login-panel.js", import.meta.url), "utf8");
const sms = {
  handler: "evolute", type: "form", step_id: "sms",
  description_placeholders: { phone_number: "+79991234567" }, errors: {},
};
const done = { handler: "evolute", type: "create_entry" };
const flush = () => new Promise((resolve) => setImmediate(resolve));

async function screen(t, responses, { admin = true, url, language = "ru", isolated = false } = {}) {
  const window = new Window({
    url: url || "http://homeassistant.local:8123/evolute-login?flow_id=flow-123",
    settings: { disableIframePageLoading: true, disableJavaScriptFileLoading: true },
  });
  t.after(() => window.happyDOM.close());
  if (isolated) {
    Object.defineProperty(window.HTMLIFrameElement.prototype, "credentialless", {
      configurable: true,
      get() { return this.hasAttribute("credentialless"); },
      set(value) { this.toggleAttribute("credentialless", Boolean(value)); },
    });
  } else {
    delete window.HTMLIFrameElement.prototype.credentialless;
  }
  const reloads = [];
  Object.defineProperty(window.location, "reload", {
    value: () => reloads.push(window.location.href),
  });
  window.localStorage.setItem("hass-session", "preserved");
  window.eval(source);
  const calls = [];
  const hass = {
    language, user: { is_admin: admin },
    callApi: async (...args) => {
      calls.push(structuredClone(args));
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return typeof next === "function" ? next() : next;
    },
  };
  const panel = window.document.createElement("evolute-login-panel-v3");
  window.document.body.append(panel);
  panel.hass = hass;
  await flush();
  const root = panel.shadowRoot;
  const submit = async (code) => {
    if (code !== undefined) {
      if (!root.getElementById("official").hidden) root.getElementById("received").click();
      root.getElementById("sms-code").value = code;
    }
    root.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
    await flush();
  };
  return { panel, root, calls, hass, submit, reloads, window };
}

test("requests SMS without the saved EVAssist login and finishes the same HA flow", async (t) => {
  const { root, calls, panel, hass, submit } = await screen(t, [sms, done], { isolated: true });
  const frame = root.querySelector("iframe");
  assert.equal(frame.src, "https://app.evassist.ru/login");
  assert.equal(frame.referrerPolicy, "no-referrer");
  assert.equal(frame.credentialless, true);
  assert.equal(frame.getAttribute("sandbox"), "allow-scripts allow-forms allow-same-origin");
  assert.match(root.getElementById("instructions").textContent, /\+79991234567/);
  assert.equal(root.getElementById("back").target, "");
  panel.hass = { ...hass, states: {} };
  await flush();
  assert.equal(root.querySelector("iframe"), frame);
  assert.equal(calls.length, 1);
  assert.equal(root.getElementById("entry").hidden, true);
  assert.equal(root.getElementById("sms-code").disabled, true);
  root.getElementById("received").click();
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("official").hidden, true);
  assert.equal(root.getElementById("entry").hidden, false);
  assert.equal(root.getElementById("sms-code").disabled, false);
  assert.equal(root.activeElement, root.getElementById("sms-code"));
  await submit("0123");
  assert.deepEqual(calls, [
    ["GET", "config/config_entries/flow/flow-123"],
    ["POST", "config/config_entries/flow/flow-123", { sms_code: "0123" }],
  ]);
  assert.match(root.getElementById("status").textContent, /подключён/);
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("sms-code").value, "");
});

test("invalid codes do not reach the backend", async (t) => {
  const { calls, root, submit } = await screen(t, [sms]);
  await submit("12a3");
  assert.equal(calls.length, 1);
  assert.equal(root.getElementById("error").hidden, false);
  assert.match(root.getElementById("error").textContent, /4 цифры/);
});

test("an incorrect code lets the user request another SMS in the same flow", async (t) => {
  const { root, submit } = await screen(t, [sms, { ...sms, errors: { base: "invalid_auth" } }, done]);
  const frame = root.querySelector("iframe");
  await submit("1111");
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("sms-code").value, "");
  assert.match(root.getElementById("error").textContent, /Код неверный/);
  root.getElementById("request-again").click();
  assert.notEqual(root.querySelector("iframe"), frame);
  assert.equal(root.querySelector("iframe").src, "https://app.evassist.ru/login");
  assert.equal(root.getElementById("sms-code").disabled, true);
  assert.equal(root.getElementById("error").hidden, true);
  await submit("2222");
  assert.match(root.getElementById("status").textContent, /подключён/);
});

test("double submission sends a one-time code once and supports reauthentication", async (t) => {
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  const { root, calls, submit } = await screen(t, [sms, () => pending]);
  await submit("0123");
  assert.equal(root.getElementById("submit").disabled, true);
  assert.equal(root.getElementById("request-again").disabled, true);
  root.getElementById("request-again").click();
  assert.equal(root.querySelector("iframe"), null);
  await submit("0123");
  assert.equal(calls.length, 2);
  finish({ handler: "evolute", type: "abort", reason: "reauth_successful" });
  await flush();
  assert.match(root.getElementById("status").textContent, /обновлено/);
  assert.equal(root.querySelector("iframe"), null);
});

test("car selection uses the serialized HA schema and treats labels as text", async (t) => {
  const cars = {
    handler: "evolute", type: "form", step_id: "select_car", errors: {},
    data_schema: [{ name: "car_id", type: "select", options: [
      ["one", "i-JOY"], ["two", "<img src=x onerror=alert(1)>"],
    ] }],
  };
  const { root, calls, submit } = await screen(t, [sms, cars, done]);
  await submit("0123");
  assert.equal(root.querySelector("iframe"), null);
  const select = root.getElementById("car-id");
  assert.equal(select.options.length, 2);
  assert.equal(select.options[1].textContent, "<img src=x onerror=alert(1)>");
  assert.equal(root.querySelector("img"), null);
  assert.equal(root.getElementById("sms-code").disabled, true);
  select.value = "two";
  await submit();
  assert.deepEqual(calls[2][2], { car_id: "two" });
});

test("failed discovery retries without submitting the SMS code again", async (t) => {
  const retry = {
    handler: "evolute", type: "form", step_id: "select_car",
    data_schema: [], errors: { base: "cannot_connect" },
  };
  const { root, calls, submit } = await screen(t, [sms, retry, done]);
  await submit("0123");
  assert.match(root.getElementById("submit").textContent, /Повторить/);
  assert.equal(root.getElementById("car-field").hidden, true);
  await submit();
  assert.deepEqual(calls[2][2], {});
});

test("requires a Home Assistant administrator before loading the site or flow", async (t) => {
  const { root, calls } = await screen(t, [], { admin: false });
  assert.equal(calls.length, 0);
  assert.equal(root.querySelector("iframe"), null);
  assert.match(root.getElementById("status").textContent, /администратор/);
  root.getElementById("received").click();
  root.getElementById("restart").click();
  assert.equal(root.querySelector("iframe"), null);
});

test("does not open an unrelated integration flow", async (t) => {
  const { root, calls, submit } = await screen(t, [{ ...sms, handler: "other" }]);
  assert.equal(root.querySelector("iframe"), null);
  await submit("0123");
  assert.equal(calls.length, 1);
});

test("an expired flow gives a route back to setup", async (t) => {
  const { root } = await screen(t, [new Error("Not found")]);
  assert.equal(root.querySelector("iframe"), null);
  assert.match(root.getElementById("status").textContent, /начните вход заново/);
  assert.match(root.getElementById("back").href, /\/config\/integrations$/);
});

test("network errors keep the user on the HA code step", async (t) => {
  const { root, calls, submit } = await screen(t, [sms, new Error("Disconnected"), done]);
  await submit("0123");
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("official").hidden, true);
  assert.equal(root.getElementById("entry").hidden, false);
  assert.equal(root.getElementById("submit").disabled, false);
  assert.equal(root.getElementById("sms-code").value, "");
  await submit("4567");
  assert.equal(calls.length, 3);
  assert.match(root.getElementById("status").textContent, /подключён/);
});

test("restart reopens the official login page without restarting HA setup", async (t) => {
  const { root, calls, reloads } = await screen(t, [sms]);
  const oldFrame = root.querySelector("iframe");
  assert.equal(oldFrame.hasAttribute("credentialless"), false);
  oldFrame.src = "https://app.evassist.ru/pick-organization";
  root.getElementById("sms-code").value = "0123";
  root.getElementById("recovery").open = true;
  root.getElementById("restart").click();
  assert.notEqual(root.querySelector("iframe"), oldFrame);
  assert.equal(root.querySelector("iframe").src, "https://app.evassist.ru/login");
  assert.equal(root.getElementById("sms-code").value, "");
  assert.equal(root.getElementById("sms-code").disabled, true);
  assert.equal(calls.length, 1);
  assert.equal(reloads.length, 0);
  assert.match(root.getElementById("instructions").textContent, /\+79991234567/);
  assert.match(root.getElementById("status").textContent, /открыта заново/);
  assert.match(root.getElementById("session-help").textContent, /локальное хранилище/);
  assert.match(root.getElementById("session-help").textContent, /приватном окне/);
  assert.doesNotMatch(root.getElementById("session-help").textContent, /значок выхода/);
});

test("reset reloads the top-level page to discard the credentialless session", async (t) => {
  const { root, calls, reloads, window } = await screen(t, [sms], { isolated: true });
  root.querySelector("iframe").src = "https://app.evassist.ru/pick-organization";
  root.getElementById("sms-code").value = "0123";
  assert.equal(root.getElementById("restart").textContent, "Сбросить встроенный вход");
  assert.match(root.getElementById("session-help").textContent, /перезагрузит эту страницу/);
  root.getElementById("restart").click();
  assert.deepEqual(reloads, ["http://homeassistant.local:8123/evolute-login?flow_id=flow-123"]);
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("sms-code").value, "");
  assert.equal(calls.length, 1);
  assert.equal(window.localStorage.getItem("hass-session"), "preserved");
  assert.match(root.getElementById("status").textContent, /Сбрасываем/);
  root.getElementById("restart").click();
  assert.equal(reloads.length, 1);
});

test("requesting another SMS discards the isolated session after a used code", async (t) => {
  const { root, calls, reloads, submit } = await screen(t, [
    sms, { ...sms, errors: { base: "invalid_auth" } },
  ], { isolated: true });
  await submit("0123");
  assert.equal(root.querySelector("iframe"), null);
  root.getElementById("request-again").click();
  assert.equal(reloads.length, 1);
  assert.equal(new URL(reloads[0]).searchParams.get("flow_id"), "flow-123");
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1][2], { sms_code: "0123" });
});

test("a hidden HA code field cannot submit while requesting an SMS", async (t) => {
  const { root, calls, submit } = await screen(t, [sms]);
  root.getElementById("sms-code").value = "0123";
  await submit();
  assert.equal(calls.length, 1);
  assert.equal(root.getElementById("entry").hidden, true);
  assert.notEqual(root.querySelector("iframe"), null);
});

test("returning to request another SMS clears the previous code", async (t) => {
  const { root, calls } = await screen(t, [sms]);
  root.getElementById("received").click();
  root.getElementById("sms-code").value = "0123";
  root.getElementById("request-again").click();
  assert.equal(root.getElementById("sms-code").value, "");
  assert.equal(root.getElementById("entry").hidden, true);
  assert.notEqual(root.querySelector("iframe"), null);
  root.getElementById("received").click();
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("sms-code").value, "");
  assert.equal(calls.length, 1);
});

test("HA updates preserve a partially entered code without remounting the website", async (t) => {
  const { root, panel, hass, calls } = await screen(t, [sms]);
  root.getElementById("received").click();
  root.getElementById("sms-code").value = "01";
  panel.hass = { ...hass, states: {} };
  await flush();
  assert.equal(root.getElementById("sms-code").value, "01");
  assert.equal(root.querySelector("iframe"), null);
  assert.equal(root.getElementById("entry").hidden, false);
  assert.equal(calls.length, 1);
});

test("recovery controls are localized in English", async (t) => {
  const { root } = await screen(t, [sms], { language: "en" });
  assert.match(root.getElementById("recovery-title").textContent, /entered the code/);
  assert.equal(root.getElementById("restart").textContent, "Restart the EVAssist form");
  root.getElementById("received").click();
  assert.equal(root.getElementById("request-again").textContent, "Request another SMS");
});

test("isolated recovery is localized in English", async (t) => {
  const { root, reloads } = await screen(t, [sms], { language: "en", isolated: true });
  assert.equal(root.getElementById("restart").textContent, "Reset the embedded sign-in");
  assert.match(root.getElementById("session-help").textContent, /clean form session/);
  root.getElementById("restart").click();
  assert.equal(reloads.length, 1);
  assert.equal(root.getElementById("status").textContent, "Resetting the embedded sign-in…");
});
