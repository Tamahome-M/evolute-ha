// A field in HA's native config flow; phone/code and submission belong to HA.
(() => {
  const elementName = "ha-selector-evolute_login";
  if (customElements.get(elementName)) return;
  const settingsUrl = "/config/integrations/integration/evolute";
  const words = {
    ru: {
      title: "Официальная форма EVAssist",
      again: "Запросить новую СМС",
      recovery: "Уже вошли на сайте или видите «Choose account»?",
      isolated: "Нажмите «Начать вход заново»: диалог закроется и страница HA перезагрузится. Начните вход ещё раз — форма откроется в новой изолированной сессии.",
      shared: "Очистите cookies и данные app.evassist.ru в настройках браузера, включая локальное хранилище, затем начните вход заново. Также можно запросить СМС на официальном сайте в приватном окне.",
      restart: "Начать вход заново",
      fallback: "Не загружается капча? Открыть официальный сайт",
      failure: "Не удалось вернуться к форме. Повторите попытку.",
      restartFailure: "Не удалось завершить текущий вход. Закройте диалог и обновите страницу HA.",
    },
    en: {
      title: "Official EVAssist form",
      again: "Request another SMS",
      recovery: "Already signed in on the website or seeing “Choose account”?",
      isolated: "Press “Start sign-in again”: the dialog will close and HA will reload. Start sign-in again to open the form in a fresh isolated session.",
      shared: "Clear cookies and site data for app.evassist.ru, including local storage, then start sign-in again. You can also request an SMS on the official site in a private window.",
      restart: "Start sign-in again",
      fallback: "CAPTCHA not loading? Open the official website",
      failure: "Could not return to the form. Try again.",
      restartFailure: "Could not cancel the current sign-in. Close the dialog and reload HA.",
    },
  };

  class EvoluteLoginField extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._busy = false;
      this._disabled = false;
      this._onFlowUpdate = this._onFlowUpdate.bind(this);
      // Keyboard activation of recovery controls must not submit HA's form.
      this.shadowRoot.addEventListener("keydown", (event) => event.stopPropagation());
    }

    set hass(value) { this._hass = value; this._render(); }
    get hass() { return this._hass; }
    set selector(value) { this._selector = value; this._render(); }
    get selector() { return this._selector; }
    set disabled(value) { this._disabled = Boolean(value); this._updateDisabled(); }
    get disabled() { return this._disabled; }

    connectedCallback() {
      window.addEventListener("flow-update", this._onFlowUpdate, true);
      this._render();
    }

    disconnectedCallback() {
      window.removeEventListener("flow-update", this._onFlowUpdate, true);
    }

    get _config() { return this._selector?.evolute_login; }
    get _words() { return words[this._hass?.language?.startsWith("ru") ? "ru" : "en"]; }

    _render() {
      if (!this.isConnected || !this._hass || !this._config) return;
      const { flow_id: flowId, mode } = this._config;
      if (!/^[a-zA-Z0-9_-]+$/.test(flowId) || this._hass.user?.is_admin !== true) {
        this.shadowRoot.replaceChildren();
        this._renderKey = undefined;
        return;
      }
      const renderKey = `${flowId}:${mode}:${this._hass.language}`;
      // HA updates hass frequently. Preserve the iframe, CAPTCHA and typed phone.
      if (renderKey === this._renderKey) return;
      this._renderKey = renderKey;
      this.toggleAttribute("hidden", mode === "status");
      const t = this._words;
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; color: var(--primary-text-color); }
          :host([hidden]) { display: none; }
          iframe { display: block; width: 100%; height: min(54vh, 510px); min-height: 300px;
            border: 1px solid var(--divider-color, #ccc); border-radius: 8px; background: white; }
          button { font: inherit; color: var(--primary-color, #03a9f4); cursor: pointer;
            background: none; border: 1px solid currentColor; border-radius: 8px; padding: 10px 14px; }
          button:disabled { opacity: .5; cursor: default; }
          details, p { margin: 12px 0 0; line-height: 1.5; }
          summary { cursor: pointer; }
          a { color: var(--primary-color, #03a9f4); }
          #error { color: var(--error-color, #db4437); }
          [hidden] { display: none; }
        </style>
        ${mode === "request" ? `
          <div id="official"></div>
          <p><a href="https://app.evassist.ru/login" target="_blank" rel="noopener noreferrer">${t.fallback}</a></p>
          <details><summary>${t.recovery}</summary><p id="recovery-help"></p>
            <p><button type="button" id="restart">${t.restart}</button></p>
          </details>
        ` : mode === "actions" ? `<button type="button" id="again">${t.again}</button>` : ""}
        <p id="error" role="alert" hidden></p>`;

      if (mode === "request") {
        const frame = document.createElement("iframe");
        const isolated = "credentialless" in frame;
        if (isolated) frame.credentialless = true;
        frame.title = t.title;
        frame.referrerPolicy = "no-referrer";
        frame.setAttribute("sandbox", "allow-scripts allow-forms allow-same-origin");
        frame.src = "https://app.evassist.ru/login";
        this.shadowRoot.getElementById("official").append(frame);
        this.shadowRoot.getElementById("recovery-help").textContent = isolated ? t.isolated : t.shared;
      }
      this.shadowRoot.getElementById("again")?.addEventListener("click", () => this._requestAgain());
      this.shadowRoot.getElementById("restart")?.addEventListener("click", () => this._restart());
      this._updateDisabled();
    }

    _updateDisabled() {
      const disabled = this._busy || this._disabled;
      for (const button of this.shadowRoot.querySelectorAll("button")) button.disabled = disabled;
    }

    _error(message) {
      const error = this.shadowRoot.getElementById("error");
      error.textContent = message;
      error.hidden = !message;
    }

    get _canAct() {
      return this.isConnected && !this._busy && !this._disabled
        && this._hass?.user?.is_admin === true && /^[a-zA-Z0-9_-]+$/.test(this._config?.flow_id);
    }

    async _requestAgain() {
      if (!this._canAct || this._config.mode !== "actions") return;
      this._busy = true;
      this._updateDisabled();
      this._error("");
      try {
        const stepPromise = this._hass.callApi("POST",
          `config/config_entries/flow/${this._config.flow_id}`, { evassist: "request_again" });
        // Native menu steps use the same event. HA owns the returned form,
        // validation, cancellation and all later submissions.
        this.dispatchEvent(new CustomEvent("flow-update", {
          bubbles: true, composed: true, detail: { stepPromise },
        }));
        await stepPromise;
      } catch {
        this._error(this._words.failure);
      } finally {
        this._busy = false;
        this._updateDisabled();
      }
    }

    async _restart() {
      if (!this._canAct || this._config.mode !== "request") return;
      this._busy = true;
      this._updateDisabled();
      this._error("");
      try {
        await this._hass.callApi("DELETE", `config/config_entries/flow/${this._config.flow_id}`);
        // A new top-level document creates a fresh credentialless storage nonce.
        // Replacing only the iframe would reuse the old EVAssist session.
        window.location.replace(settingsUrl);
      } catch {
        this._error(this._words.restartFailure);
        this._busy = false;
        this._updateDisabled();
      }
    }

    async _onFlowUpdate(event) {
      if (this._hass?.user?.is_admin !== true) return;
      const flowId = this._config?.flow_id;
      try {
        const step = await (event.detail?.step || event.detail?.stepPromise);
        if (step?.handler !== "evolute" || step.flow_id !== flowId || this._navigating) return;
        if (step.type !== "create_entry" && !(step.type === "abort"
          && ["reauth_successful", "reconfigure_successful"].includes(step.reason))) return;
        this._navigating = true;
        // Let HA finish processing the result before leaving the native dialog.
        setTimeout(() => window.location.replace(settingsUrl), 0);
      } catch {
        // The native dialog displays errors from its own submissions.
      }
    }
  }

  customElements.define(elementName, EvoluteLoginField);
})();
