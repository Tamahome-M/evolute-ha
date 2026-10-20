// Keep the official login page on its own origin; never read its cookies or DOM.
const LOGIN_URL = "https://app.evassist.ru/login";
const INTEGRATIONS_URL = "/config/integrations";
const PANEL_ELEMENT = "evolute-login-panel-v2";

const TEXT = {
  ru: {
    title: "Вход в Evolute",
    back: "Настройки интеграций",
    loading: "Загрузка настройки…",
    request: "1. Запросите СМС",
    requestHelp: "Введите номер {phone} в форме ниже, пройдите капчу и запросите СМС. Когда сообщение придёт, нажмите «СМС получено» над формой. Код на странице EVAssist не вводите.",
    received: "СМС получено — ввести код в HA",
    requestAgain: "Запросить новую СМС",
    recovery: "Уже ввёл код на сайте или вижу автомобили",
    recoveryHelp: "Код, введённый на сайте EVAssist, уже использован. Перезапустите форму входа и запросите новый код.",
    sessionHelp: "Если снова видны автомобили, нажмите значок выхода на левой панели сайта рядом с настройками, затем запросите СМС заново.",
    restart: "Перезапустить форму EVAssist",
    restarted: "Страница EVAssist открыта заново. Запросите новый СМС-код.",
    finish: "2. Введите код в Home Assistant",
    codeHelp: "Введите код здесь — интеграция получит сессию и найдёт автомобиль. Если код уже использован на сайте, запросите новую СМС кнопкой ниже.",
    code: "СМС-код для {phone}",
    signIn: "Войти",
    working: "Подключение…",
    fallback: "Если встроенная страница не работает, откройте официальный сайт",
    fallbackHelp: "Запросите СМС в приватном окне, вернитесь и нажмите «СМС получено». Код на сайте вводить не нужно.",
    car: "Выберите автомобиль",
    connect: "Подключить",
    retry: "Повторить загрузку автомобилей",
    done: "Автомобиль подключён к Home Assistant.",
    recovered: "Вход выполнен. Подключение автомобиля обновлено.",
    admin: "Для настройки нужен вход под администратором Home Assistant.",
    unavailable: "Эта настройка закрыта или уже завершена. Откройте Evolute в настройках интеграций и начните вход заново.",
    failed: "Не удалось продолжить настройку. Проверьте соединение и повторите попытку.",
    invalid_code: "Введите 4 цифры из СМС.",
    invalid_auth: "Код неверный, истёк или уже использован. Проверьте код или нажмите «Запросить новую СМС».",
    rate_limited: "Слишком много запросов. Подождите и попробуйте снова.",
    cannot_connect: "Не удалось связаться с EVAssist. Повторите попытку.",
    session_expired: "Сессия истекла. Запросите новый СМС-код.",
    invalid_car: "Выберите автомобиль из списка.",
    already_configured: "Этот автомобиль уже подключён.",
    no_cars: "В этом аккаунте нет автомобилей.",
    wrong_account: "В этом аккаунте нет нужного автомобиля. Войдите в аккаунт с доступом к нему.",
    entry_removed: "Подключение интеграции было удалено.",
  },
  en: {
    title: "Sign in to Evolute",
    back: "Integration settings",
    loading: "Loading setup…",
    request: "1. Request an SMS",
    requestHelp: "Enter {phone} below, complete the CAPTCHA and request an SMS. When it arrives, press 'SMS received' above the form. Do not enter the code on the EVAssist page.",
    received: "SMS received — enter the code in HA",
    requestAgain: "Request another SMS",
    recovery: "I entered the code on the website or see my cars",
    recoveryHelp: "A code entered on the EVAssist website has already been used. Restart the login form and request another code.",
    sessionHelp: "If cars are still shown, use the sign-out icon in the website's left sidebar beside settings, then request another SMS.",
    restart: "Restart the EVAssist form",
    restarted: "The EVAssist page has been reopened. Request another SMS code.",
    finish: "2. Enter the code in Home Assistant",
    codeHelp: "Enter the code here so the integration can sign in and find your car. If you used the code on the website, request another SMS with the button below.",
    code: "SMS code for {phone}",
    signIn: "Sign in",
    working: "Connecting…",
    fallback: "If the embedded page does not work, open the official website",
    fallbackHelp: "Request an SMS in a private window, return and press 'SMS received'. Do not enter the code on the website.",
    car: "Choose your car",
    connect: "Connect",
    retry: "Retry loading cars",
    done: "Your car is connected to Home Assistant.",
    recovered: "Sign-in successful. Your car connection has been updated.",
    admin: "Sign in as a Home Assistant administrator to continue setup.",
    unavailable: "This setup was closed or has already finished. Open Evolute in integration settings and start signing in again.",
    failed: "Unable to continue setup. Check your connection and try again.",
    invalid_code: "Enter the 4 digits from the SMS.",
    invalid_auth: "The code is incorrect, expired or already used. Check the code or press 'Request another SMS'.",
    rate_limited: "Too many requests. Wait and try again.",
    cannot_connect: "Cannot connect to EVAssist. Try again.",
    session_expired: "Your session expired. Request another SMS code.",
    invalid_car: "Choose a car from the list.",
    already_configured: "This car is already connected.",
    no_cars: "No cars were found in this account.",
    wrong_account: "This account does not have access to the car. Sign in to the account that does.",
    entry_removed: "The integration entry was removed.",
  },
};

class EvoluteLoginPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._step = null;
    this._busy = false;
    this._started = false;
    this._smsStage = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._start();
  }

  connectedCallback() {
    this._start();
  }

  _text(key, phone = "") {
    const language = this._hass?.language?.startsWith("ru") ? "ru" : "en";
    return (TEXT[language][key] || TEXT[language].failed).replace("{phone}", phone);
  }

  async _start() {
    if (!this.isConnected || !this._hass || this._started) return;
    this._started = true;
    this._build();
    if (!this._hass.user?.is_admin) {
      this._message("admin");
      return;
    }
    const flowId = new URLSearchParams(window.location.search).get("flow_id");
    if (!flowId || !/^[a-zA-Z0-9_-]+$/.test(flowId)) {
      this._message("unavailable");
      return;
    }
    this._apiPath = `config/config_entries/flow/${encodeURIComponent(flowId)}`;
    try {
      this._accept(await this._hass.callApi("GET", this._apiPath));
    } catch {
      this._message("unavailable");
    }
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, sans-serif); }
        * { box-sizing: border-box; }
        header, main { max-width: 800px; margin: auto; padding: 20px; }
        header { border-bottom: 1px solid var(--divider-color, #ddd); }
        h1 { font-size: 24px; margin: 12px 0 0; }
        h2 { font-size: 19px; margin-top: 0; }
        p { line-height: 1.5; }
        a { color: var(--primary-color, #03a9f4); }
        .columns { display: grid; grid-template-columns: 1fr; gap: 24px; }
        section { padding: 20px; border: 1px solid var(--divider-color, #ddd); border-radius: 12px; background: var(--card-background-color, white); }
        iframe { width: 100%; height: 580px; border: 0; background: white; border-radius: 8px; }
        label { display: block; margin: 16px 0 8px; }
        input, select, button { font: inherit; padding: 12px; border-radius: 8px; }
        input, select { width: 100%; color: inherit; background: var(--secondary-background-color, #fafafa); border: 1px solid var(--divider-color, #bbb); }
        input { font-size: 22px; letter-spacing: 6px; }
        button { margin-top: 16px; border: 0; background: var(--primary-color, #03a9f4); color: var(--text-primary-color, white); cursor: pointer; }
        button:disabled { opacity: .6; cursor: wait; }
        button.secondary { background: transparent; color: var(--primary-color, #03a9f4); border: 1px solid var(--divider-color, #ddd); }
        #received { margin: 0 0 16px; width: 100%; }
        #entry form { max-width: 480px; }
        details { margin: 16px 0; }
        summary { cursor: pointer; color: var(--primary-color, #03a9f4); }
        .help { font-size: 14px; color: var(--secondary-text-color, #666); }
        [role="alert"] { color: var(--error-color, #db4437); line-height: 1.5; }
        [hidden] { display: none !important; }
        @media (max-width: 700px) {
          .columns { grid-template-columns: 1fr; }
          header, main { padding: 12px; }
          section { padding: 16px; }
          iframe { height: 500px; }
        }
      </style>
      <header><a href="${INTEGRATIONS_URL}" id="back"></a><h1></h1></header>
      <main>
        <p id="status" role="status"></p>
        <p id="error" role="alert" hidden></p>
        <div class="columns" hidden>
          <section id="official">
            <h2 id="request-title"></h2><p id="instructions"></p>
            <button id="received" type="button"></button>
            <div id="frame"></div>
            <details id="recovery">
              <summary id="recovery-title"></summary>
              <p id="recovery-help"></p><p class="help" id="session-help"></p>
              <button id="restart" type="button" class="secondary"></button>
            </details>
            <a href="${LOGIN_URL}" target="_blank" rel="noopener noreferrer" id="fallback"></a>
            <p class="help" id="fallback-help"></p>
          </section>
          <section id="entry">
            <h2 id="form-title"></h2>
            <p id="code-help"></p>
            <form>
              <div id="code-field"><label for="sms-code"></label>
                <input id="sms-code" name="sms_code" type="text" inputmode="numeric"
                  autocomplete="one-time-code" pattern="[0-9]{4}" minlength="4" maxlength="4" required>
              </div>
              <div id="car-field" hidden><label for="car-id"></label><select id="car-id" name="car_id"></select></div>
              <button id="submit" type="submit"></button>
            </form>
            <button id="request-again" type="button" class="secondary"></button>
          </section>
        </div>
      </main>`;
    for (const [id, key] of Object.entries({
      back: "back", "request-title": "request", "session-help": "sessionHelp",
      fallback: "fallback", "fallback-help": "fallbackHelp",
      received: "received", "recovery-title": "recovery", "recovery-help": "recoveryHelp",
      restart: "restart", "code-help": "codeHelp", "request-again": "requestAgain",
    })) this._element(id).textContent = this._text(key);
    this.shadowRoot.querySelector("h1").textContent = this._text("title");
    this._element("status").textContent = this._text("loading");
    this.shadowRoot.querySelector("label[for='car-id']").textContent = this._text("car");
    this.shadowRoot.querySelector("form").addEventListener("submit", (event) => {
      event.preventDefault();
      this._submit();
    });
    this._element("received").addEventListener("click", () => {
      if (this._busy || this._step !== "sms") return;
      this._element("status").hidden = true;
      this._element("error").hidden = true;
      this._showSmsStage("code");
      this._element("sms-code").focus();
    });
    for (const id of ["restart", "request-again"]) {
      this._element(id).addEventListener("click", () => this._restartRequest());
    }
  }

  _element(id) {
    return this.shadowRoot.getElementById(id);
  }

  _message(key) {
    this.shadowRoot.querySelector(".columns").hidden = true;
    this._element("status").hidden = false;
    this._element("status").textContent = this._text(key);
    // Drop the third-party page once authentication has finished.
    this._element("frame").replaceChildren();
    this._element("sms-code").value = "";
    this._step = null;
    this._smsStage = null;
    this._element("error").hidden = true;
  }

  _accept(result) {
    if (result.handler !== "evolute") {
      this._message("unavailable");
      return;
    }
    if (result.type === "create_entry") {
      this._message("done");
      return;
    }
    if (result.type === "abort") {
      this._message(["reauth_successful", "reconfigure_successful"].includes(result.reason)
        ? "recovered" : result.reason);
      return;
    }
    if (result.type !== "form" || !["sms", "select_car"].includes(result.step_id)) {
      this._message("unavailable");
      return;
    }
    this._step = result.step_id;
    const sms = this._step === "sms";
    this._element("status").hidden = true;
    this.shadowRoot.querySelector(".columns").hidden = false;
    this._element("code-field").hidden = !sms;
    this._element("sms-code").value = "";
    this._element("car-field").hidden = sms;
    this._element("form-title").textContent = this._text(sms ? "finish" : "car");
    this._element("code-help").hidden = !sms;
    this._element("request-again").hidden = !sms;
    if (sms) {
      const phone = result.description_placeholders?.phone_number || "";
      this._element("instructions").textContent = this._text("requestHelp", phone);
      this.shadowRoot.querySelector("label[for='sms-code']").textContent = this._text("code", phone);
      this._showSmsStage(this._smsStage || "request");
    } else {
      this._smsStage = null;
      this._element("official").hidden = true;
      this._element("entry").hidden = false;
      this._element("frame").replaceChildren();
      const field = result.data_schema?.find((item) => item.name === "car_id");
      const options = field?.options || [];
      this._element("car-field").hidden = options.length === 0;
      this._element("car-id").replaceChildren(...options.map(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        return option;
      }));
    }
    const error = Object.values(result.errors || {})[0];
    this._element("error").hidden = !error;
    this._element("error").textContent = error ? this._text(error) : "";
    this._setBusy(false);
  }

  _setBusy(busy) {
    this._busy = busy;
    const button = this._element("submit");
    button.disabled = busy;
    button.textContent = this._text(busy ? "working" : this._step === "sms"
      ? "signIn" : this._element("car-id").options.length ? "connect" : "retry");
    for (const id of ["received", "restart", "request-again"]) {
      this._element(id).disabled = busy;
    }
    this._element("sms-code").disabled = busy || this._step !== "sms" || this._smsStage !== "code";
    this._element("car-id").disabled = busy || this._step !== "select_car";
  }

  _showSmsStage(stage) {
    this._smsStage = stage;
    const request = stage === "request";
    this._element("official").hidden = !request;
    this._element("entry").hidden = request;
    if (request) {
      this._element("sms-code").value = "";
      if (!this._element("frame").firstChild) {
        const frame = document.createElement("iframe");
        frame.title = this._text("request");
        frame.src = LOGIN_URL;
        frame.referrerPolicy = "no-referrer";
        frame.setAttribute("sandbox", "allow-scripts allow-forms allow-same-origin");
        this._element("frame").append(frame);
      }
    } else {
      // Remove the website's code form before focusing Home Assistant's field.
      this._element("frame").replaceChildren();
    }
    this._setBusy(this._busy);
  }

  _restartRequest() {
    if (this._busy || this._step !== "sms") return;
    this._element("frame").replaceChildren();
    this._element("error").hidden = true;
    this._showSmsStage("request");
    this._element("status").textContent = this._text("restarted");
    this._element("status").hidden = false;
  }

  async _submit() {
    if (this._busy || !this._step) return;
    if (this._step === "sms" && this._smsStage !== "code") return;
    const data = {};
    if (this._step === "sms") {
      const code = this._element("sms-code").value.trim();
      if (!/^[0-9]{4}$/.test(code)) {
        this._element("error").textContent = this._text("invalid_code");
        this._element("error").hidden = false;
        return;
      }
      data.sms_code = code;
      this._element("sms-code").value = "";
    } else if (this._element("car-id").options.length) {
      data.car_id = this._element("car-id").value;
    }
    this._setBusy(true);
    try {
      this._accept(await this._hass.callApi("POST", this._apiPath, data));
    } catch (error) {
      if (error?.status_code === 404) {
        this._message("unavailable");
      } else {
        this._element("error").textContent = this._text("failed");
        this._element("error").hidden = false;
      }
    } finally {
      this._setBusy(false);
    }
  }
}

if (!customElements.get(PANEL_ELEMENT)) {
  customElements.define(PANEL_ELEMENT, EvoluteLoginPanel);
}
