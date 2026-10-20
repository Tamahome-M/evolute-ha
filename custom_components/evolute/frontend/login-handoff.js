// Follow only this integration's completed handoff, in the current HA tab.
(() => {
  const registered = Symbol.for("evolute.loginHandoff.v1");
  if (window[registered]) return;
  window[registered] = true;
  let navigating = false;

  window.addEventListener("flow-update", async (event) => {
    try {
      // Menu steps may dispatch the pending request instead of its result.
      const step = await (event.detail?.step || event.detail?.stepPromise);
      if (navigating || step?.handler !== "evolute" || step.type !== "abort"
        || step.reason !== "continue_in_panel") return;
      const url = step.description_placeholders?.login_url;
      if (typeof url !== "string" || !/^\/evolute-login\?flow_id=[a-zA-Z0-9_-]+$/.test(url)) return;
      navigating = true;
      // Let HA finish processing the terminal result before leaving its dialog.
      window.setTimeout(() => window.location.assign(url), 0);
    } catch {
      // HA displays request errors; the handoff link remains a manual fallback.
    }
  }, { capture: true });
})();
