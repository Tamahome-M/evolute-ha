import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { Window } from "happy-dom";

const source = await readFile(new URL("../custom_components/evolute/frontend/login-form.js", import.meta.url), "utf8");
const settingsUrl = "/config/integrations/integration/evolute";
const flush = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setTimeout(resolve, 5));
};

async function field(t, { mode = "request", admin = true, isolated = true, responses = [], flowId = "flow-123", language = "ru" } = {}) {
  const window = new Window({
    url: "http://homeassistant.local:8123/config/integrations",
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
  const redirects = [];
  Object.defineProperty(window.location, "replace", { value: (url) => redirects.push(url) });
  window.localStorage.setItem("hass-session", "preserved");
  const calls = [];
  const hass = {
    language, user: { is_admin: admin },
    callApi: async (...args) => {
      calls.push(structuredClone(args));
      const value = responses.shift();
      if (value instanceof Error) throw value;
      return typeof value === "function" ? value() : value;
    },
  };
  window.eval(source);
  // ha-selector forwards its selector object to ha-selector-${selector type}.
  const selector = { evolute_login: { flow_id: flowId, mode } };
  const element = window.document.createElement(`ha-selector-${Object.keys(selector)[0]}`);
  element.hass = hass;
  element.selector = selector;
  const host = window.document.createElement("div");
  window.document.body.append(host);
  host.append(element);
  const updates = [];
  host.addEventListener("flow-update", (event) => updates.push(event.detail));
  await flush();
  return { element, root: element.shadowRoot, window, hass, calls, updates, redirects };
}

test("the request field immediately embeds EVAssist inside the existing dialog", async (t) => {
  const { root, calls, redirects, window } = await field(t);
  const frame = root.querySelector("iframe");
  assert.equal(frame.src, "https://app.evassist.ru/login");
  assert.equal(frame.credentialless, true);
  assert.equal(frame.referrerPolicy, "no-referrer");
  assert.equal(frame.getAttribute("sandbox"), "allow-scripts allow-forms allow-same-origin");
  assert.match(frame.title, /EVAssist/);
  assert.equal(root.querySelector("input, form"), null);
  // The only continuation control is HA's own translated form footer.
  assert.deepEqual([...root.querySelectorAll("button")].map((b) => b.id), ["restart"]);
  assert.deepEqual(calls, []);
  assert.deepEqual(redirects, []);
  assert.equal(window.location.pathname, "/config/integrations");
});

test("HA state updates preserve the iframe and CAPTCHA session", async (t) => {
  const { element, root, hass } = await field(t);
  const frame = root.querySelector("iframe");
  element.hass = { ...hass, states: { changed: true } };
  element.selector = structuredClone(element.selector);
  await flush();
  assert.equal(root.querySelector("iframe"), frame);
});

test("Enter on recovery controls cannot submit the native HA form", async (t) => {
  const { root, window } = await field(t);
  let submissions = 0;
  window.document.body.addEventListener("keydown", () => { submissions += 1; });
  for (const control of root.querySelectorAll("summary, button, a")) {
    control.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, composed: true }));
  }
  assert.equal(submissions, 0);
});

test("switching to the code step removes the website and leaves phone/code to HA", async (t) => {
  const { element, root } = await field(t);
  const frame = root.querySelector("iframe");
  element.selector = { evolute_login: { flow_id: "flow-123", mode: "actions" } };
  assert.equal(frame.isConnected, false);
  assert.equal(root.querySelector("iframe, input, form"), null);
  assert.equal(root.getElementById("again").textContent, "Запросить новую СМС");
});

test("requesting another SMS updates the same native flow without submitting credentials", async (t) => {
  const step = { handler: "evolute", flow_id: "flow-123", type: "form", step_id: "request_sms" };
  const { root, calls, updates, redirects } = await field(t, { mode: "actions", responses: [step] });
  root.getElementById("again").click();
  await flush();
  assert.deepEqual(calls, [["POST", "config/config_entries/flow/flow-123", { evassist: "request_again" }]]);
  assert.equal(updates.length, 1);
  assert.deepEqual(await updates[0].stepPromise, step);
  assert.deepEqual(redirects, []);
});

test("recovery is disabled while HA submits or another recovery request is pending", async (t) => {
  let resolve;
  const { element, root, calls } = await field(t, {
    mode: "actions", responses: [() => new Promise((done) => { resolve = done; })],
  });
  element.disabled = true;
  root.getElementById("again").click();
  assert.equal(calls.length, 0);
  element.disabled = false;
  root.getElementById("again").click();
  root.getElementById("again").click();
  assert.equal(calls.length, 1);
  assert.equal(root.getElementById("again").disabled, true);
  resolve({ handler: "evolute", flow_id: "flow-123", type: "form", step_id: "request_sms" });
  await flush();
  assert.equal(root.getElementById("again").disabled, false);
});

test("a failed recovery keeps the current step usable", async (t) => {
  const { root, redirects } = await field(t, { mode: "actions", responses: [new Error("offline")] });
  root.getElementById("again").click();
  await flush();
  assert.match(root.getElementById("error").textContent, /Повторите попытку/);
  assert.equal(root.getElementById("error").hidden, false);
  assert.equal(root.getElementById("again").disabled, false);
  assert.deepEqual(redirects, []);
});

test("restart cancels only the unfinished flow then replaces the top-level document", async (t) => {
  const { root, calls, redirects, window } = await field(t, { responses: [null] });
  assert.match(root.getElementById("recovery-help").textContent, /новой изолированной сессии/);
  root.getElementById("restart").click();
  await flush();
  assert.deepEqual(calls, [["DELETE", "config/config_entries/flow/flow-123"]]);
  assert.deepEqual(redirects, [settingsUrl]);
  assert.equal(window.localStorage.getItem("hass-session"), "preserved");
});

test("restart failure shows the recovery instruction without navigating", async (t) => {
  const { root, redirects } = await field(t, { responses: [new Error("offline")] });
  root.getElementById("restart").click();
  await flush();
  assert.match(root.getElementById("error").textContent, /Закройте диалог/);
  assert.equal(root.getElementById("restart").disabled, false);
  assert.deepEqual(redirects, []);
});

test("browsers without isolation receive cookie and local-storage recovery instructions", async (t) => {
  const { root } = await field(t, { isolated: false });
  assert.equal(root.querySelector("iframe").hasAttribute("credentialless"), false);
  assert.match(root.getElementById("recovery-help").textContent, /cookies.*локальное хранилище/);
  const link = root.querySelector("a");
  assert.equal(link.target, "_blank");
  assert.equal(link.rel, "noopener noreferrer");
});

for (const [mode, result] of [
  ["actions", { type: "create_entry" }],
  ["actions", { type: "abort", reason: "reauth_successful" }],
  ["status", { type: "abort", reason: "reconfigure_successful" }],
  ["status", { type: "create_entry" }],
]) {
  test(`${mode}: ${result.type}/${result.reason || "new car"} returns to integration settings`, async (t) => {
    const { element, window, redirects } = await field(t, { mode });
    const step = { handler: "evolute", flow_id: "flow-123", ...result };
    element.dispatchEvent(new window.CustomEvent("flow-update", {
      bubbles: true, composed: true, detail: { step },
    }));
    // HA disconnects the field when it processes a terminal result.
    element.remove();
    await flush();
    assert.deepEqual(redirects, [settingsUrl]);
  });
}

test("an unrelated flow, invalid code, cancellation or another integration never redirects", async (t) => {
  const { element, window, redirects } = await field(t, { mode: "actions" });
  for (const step of [
    { handler: "evolute", flow_id: "another-flow", type: "create_entry" },
    { handler: "another_domain", flow_id: "flow-123", type: "create_entry" },
    { handler: "evolute", flow_id: "flow-123", type: "form", step_id: "sms", errors: { base: "invalid_auth" } },
    { handler: "evolute", flow_id: "flow-123", type: "abort", reason: "wrong_account" },
    undefined,
  ]) {
    element.dispatchEvent(new window.CustomEvent("flow-update", { bubbles: true, composed: true, detail: { step } }));
  }
  await flush();
  assert.deepEqual(redirects, []);
});

test("disconnected fields no longer watch other dialogs", async (t) => {
  const { element, window, redirects } = await field(t, { mode: "actions" });
  element.remove();
  window.dispatchEvent(new window.CustomEvent("flow-update", {
    detail: { step: { handler: "evolute", flow_id: "flow-123", type: "create_entry" } },
  }));
  await flush();
  assert.deepEqual(redirects, []);
});

test("non-admins and invalid flow IDs cannot embed the site or call flow APIs", async (t) => {
  for (const options of [{ admin: false }, { flowId: "../../other" }]) {
    const { root, calls } = await field(t, options);
    assert.equal(root.childElementCount, 0);
    assert.deepEqual(calls, []);
  }
});

test("status mode stays invisible and English users see English recovery labels", async (t) => {
  const { element, root } = await field(t, { mode: "status" });
  assert.equal(element.hidden, true);
  assert.equal(root.querySelector("button, iframe"), null);
  const english = await field(t, { language: "en" });
  assert.equal(english.root.getElementById("restart").textContent, "Start sign-in again");
});

test("loading the module twice does not replace the custom element", async (t) => {
  const { element, window, root } = await field(t);
  const frame = root.querySelector("iframe");
  window.eval(source);
  assert.equal(window.customElements.get("ha-selector-evolute_login"), element.constructor);
  assert.equal(root.querySelector("iframe"), frame);
});
