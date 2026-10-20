import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { Window } from "happy-dom";

const source = await readFile(new URL("../custom_components/evolute/frontend/login-handoff.js", import.meta.url), "utf8");
const handoff = {
  handler: "evolute", type: "abort", reason: "continue_in_panel",
  description_placeholders: { login_url: "/evolute-login?flow_id=flow-123" },
};
const flush = () => new Promise((resolve) => setTimeout(resolve, 10));

function helper(t) {
  const window = new Window({ url: "http://homeassistant.local:8123/config/integrations" });
  t.after(() => window.happyDOM.close());
  const navigations = [];
  const popups = [];
  Object.defineProperty(window.location, "assign", { value: (url) => navigations.push(url) });
  window.open = (url) => popups.push(url);
  const dialog = window.document.createElement("div");
  const root = dialog.attachShadow({ mode: "open" });
  const form = window.document.createElement("step-flow-form");
  root.append(form);
  window.document.body.append(dialog);
  window.eval(source);
  const emit = (detail) => form.dispatchEvent(new window.CustomEvent("flow-update", {
    detail, bubbles: true, composed: true,
  }));
  return { window, navigations, popups, emit };
}

test("a completed Evolute handoff opens its panel in the current tab", async (t) => {
  const { emit, navigations, popups } = helper(t);
  emit({ step: handoff });
  await flush();
  assert.deepEqual(navigations, ["/evolute-login?flow_id=flow-123"]);
  assert.deepEqual(popups, []);
});

test("menu step promises wait for completion before navigating", async (t) => {
  const { emit, navigations } = helper(t);
  let resolve;
  const result = new Promise((finish) => { resolve = finish; });
  emit({ stepPromise: result });
  await flush();
  assert.deepEqual(navigations, []);
  resolve(handoff);
  await flush();
  assert.deepEqual(navigations, ["/evolute-login?flow_id=flow-123"]);
});

test("other flows, errors and unsafe destinations never trigger navigation", async (t) => {
  const { emit, navigations } = helper(t);
  emit({});
  emit({ step: { ...handoff, handler: "other" } });
  emit({ step: { ...handoff, type: "form" } });
  emit({ step: { ...handoff, reason: "wrong_account" } });
  emit({ stepPromise: Promise.reject(new Error("Disconnected")) });
  for (const url of [
    "https://example.com/evolute-login?flow_id=flow-123",
    "//example.com/evolute-login?flow_id=flow-123",
    "/evolute-login?flow_id=",
    "/evolute-login?flow_id=flow-123&redirect=other",
    "/config/integrations?flow_id=flow-123",
  ]) {
    emit({ step: { ...handoff, description_placeholders: { login_url: url } } });
  }
  await flush();
  assert.deepEqual(navigations, []);
  emit({ step: handoff });
  await flush();
  assert.equal(navigations.length, 1);
});

test("loading the helper or receiving the handoff twice navigates once", async (t) => {
  const { window, emit, navigations } = helper(t);
  window.eval(source);
  emit({ step: handoff });
  emit({ step: handoff });
  await flush();
  assert.deepEqual(navigations, ["/evolute-login?flow_id=flow-123"]);
});
