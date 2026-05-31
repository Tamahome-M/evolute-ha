/**
 * Evolute Card для Home Assistant
 * Автоматически обнаруживает сущности по translation_key.
 * Использование: type: custom:evolute-card
 */
class EvolUteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entities = {};
    this._deviceId = null;
    this._built = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    this._discover();
    this._built ? this._update() : this._build();
  }

  // -----------------------------------------------------------------------
  // Поиск entity по translation_key (= key из SensorEntityDescription)
  // -----------------------------------------------------------------------
  _discover() {
    const { entities, devices } = this._hass;
    if (!entities || !devices) return;

    // Находим device_id первого устройства Evolute (или из конфига)
    let deviceId = this._config.device_id;
    if (!deviceId) {
      for (const [, entry] of Object.entries(entities)) {
        if (entry.platform === "evolute") { deviceId = entry.device_id; break; }
      }
    }
    if (!deviceId) return;
    this._deviceId = deviceId;

    const find = (key, domain) => {
      for (const [eid, entry] of Object.entries(entities)) {
        if (entry.device_id !== deviceId) continue;
        if (domain && eid.split(".")[0] !== domain) continue;
        if (entry.translation_key === key) return eid;
      }
      return null;
    };

    this._entities = {
      battery_pct:          find("battery_pct",          "sensor"),
      remains_mileage:      find("remains_mileage",      "sensor"),
      fuel_pct:             find("fuel_pct",             "sensor"),
      remains_mileage_fuel: find("remains_mileage_fuel", "sensor"),
      odometer:             find("odometer",             "sensor"),
      coolant_temp:         find("coolant_temp",         "sensor"),
      voltage_12v:          find("voltage_12v",          "sensor"),
      outside_temp:         find("outside_temp",         "sensor"),
      inboard_temp:         find("inboard_temp",         "sensor"),
      car_model:            find("car_model",            "sensor"),
      car_year:             find("car_year",             "sensor"),
      vin:                  find("vin",                  "sensor"),
      online:               find("online",               "binary_sensor"),
      trunk:                find("trunk",                "binary_sensor"),
      central_lock:         find("central_lock",         "lock"),
      trunk_open:           find("trunk_open",           "button"),
      trunk_close:          find("trunk_close",          "button"),
      blink:                find("blink",                "button"),
      prepare_on:           find("prepare_on",           "button"),
      prepare_off:          find("prepare_off",          "button"),
      heating_on:           find("heating_on",           "button"),
      heating_off:          find("heating_off",          "button"),
      cooling_on:           find("cooling_on",           "button"),
      cooling_off:          find("cooling_off",          "button"),
      tracker:              find("tracker",              "device_tracker"),
    };
  }

  // -----------------------------------------------------------------------
  // Хелперы
  // -----------------------------------------------------------------------
  _s(eid)           { return eid ? (this._hass.states[eid] ?? null) : null; }
  _v(eid, fb = "—") { return this._s(eid)?.state ?? fb; }
  _n(eid, d = 0)    { const v = parseFloat(this._v(eid, "")); return isNaN(v) ? "—" : d ? v.toFixed(d) : String(Math.round(v)); }
  _pct(eid)         { return Math.max(0, Math.min(100, parseFloat(this._v(eid, 0)) || 0)); }
  _q(id)            { return this.shadowRoot.getElementById(id); }

  _call(domain, svc, eid) {
    if (eid) this._hass.callService(domain, svc, { entity_id: eid });
  }
  _more(eid) {
    if (!eid) return;
    this.dispatchEvent(new CustomEvent("hass-more-info",
      { detail: { entityId: eid }, bubbles: true, composed: true }));
  }

  // -----------------------------------------------------------------------
  // Первоначальная сборка DOM (один раз)
  // -----------------------------------------------------------------------
  _build() {
    if (!this._deviceId) {
      this.shadowRoot.innerHTML = `
        <ha-card style="padding:16px;font-size:14px;color:var(--secondary-text-color)">
          Устройство Evolute не найдено. Убедитесь, что интеграция настроена.
        </ha-card>`;
      return;
    }

    this.shadowRoot.innerHTML = `
<style>
  :host { display:block }
  ha-card { padding:16px; box-sizing:border-box }
  .hdr  { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px }
  .title{ font-size:22px; font-weight:600; color:var(--primary-text-color) }
  .vin  { font-size:12px; color:var(--secondary-text-color); margin-top:2px }
  .hdr-right { display:flex; flex-direction:column; align-items:flex-end; gap:4px }
  .dot  { width:10px; height:10px; border-radius:50%; margin-top:6px }
  .odo  { display:flex; align-items:center; gap:4px; font-size:14px; font-weight:500;
          cursor:pointer; color:var(--primary-text-color) }
  .odo ha-icon { --mdc-icon-size:18px; color:var(--primary-color,#3b82f6) }
  .bar  { display:flex; align-items:center; gap:10px; margin:7px 0 }
  .bar ha-icon { --mdc-icon-size:18px; color:var(--primary-color,#3b82f6); flex-shrink:0 }
  .track{ flex:1; height:6px; border-radius:6px; background:var(--divider-color,#e0e0e0); overflow:hidden }
  .fill { height:100%; border-radius:6px; background:var(--primary-color,#3b82f6); transition:width .4s }
  .lbl  { font-size:14px; font-weight:500; min-width:114px; text-align:right;
          cursor:pointer; color:var(--primary-text-color); white-space:nowrap }
  .stats{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0 }
  .stat { display:flex; flex-direction:column; align-items:center; gap:3px; cursor:pointer }
  .sval { font-size:16px; font-weight:600; color:var(--primary-text-color) }
  .sico { --mdc-icon-size:20px; color:var(--secondary-text-color) }
  .div  { height:1px; background:var(--divider-color,#e0e0e0); margin:12px 0 }
  .ctrl { display:grid; grid-template-columns:repeat(4,1fr); gap:8px }
  .btn  { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px;
          padding:10px 4px; border-radius:10px; cursor:pointer; border:none;
          background:var(--secondary-background-color,#f5f5f5);
          color:var(--primary-text-color); font-size:11px; font-weight:500;
          font-family:inherit; text-align:center; user-select:none; transition:opacity .15s }
  .btn:active { opacity:.6 }
  .btn ha-icon { --mdc-icon-size:22px }
  .btn.on { background:var(--primary-color,#3b82f6); color:#fff }
  .btn.on ha-icon { color:#fff }
</style>
<ha-card>
  <div class="hdr">
    <div>
      <div class="title" id="t-model"></div>
      <div class="vin"   id="t-vin"></div>
    </div>
    <div class="hdr-right">
      <div class="odo" id="btn-odo">
        <ha-icon icon="mdi:counter"></ha-icon><span id="t-odo"></span>
      </div>
      <div class="dot" id="t-dot"></div>
    </div>
  </div>

  <div class="bar">
    <ha-icon icon="mdi:lightning-bolt"></ha-icon>
    <div class="track"><div class="fill" id="fill-bat"></div></div>
    <div class="lbl" id="btn-bat"></div>
  </div>
  <div class="bar">
    <ha-icon icon="mdi:fuel"></ha-icon>
    <div class="track"><div class="fill" id="fill-fuel"></div></div>
    <div class="lbl" id="btn-fuel"></div>
  </div>

  <div class="stats">
    <div class="stat" id="btn-cool">
      <ha-icon class="sico" icon="mdi:thermometer-water"></ha-icon>
      <span class="sval" id="t-cool"></span>
    </div>
    <div class="stat" id="btn-volt">
      <ha-icon class="sico" icon="mdi:car-battery"></ha-icon>
      <span class="sval" id="t-volt"></span>
    </div>
    <div class="stat" id="btn-out">
      <ha-icon class="sico" icon="mdi:weather-partly-cloudy"></ha-icon>
      <span class="sval" id="t-out"></span>
    </div>
    <div class="stat" id="btn-in">
      <ha-icon class="sico" icon="mdi:car-seat"></ha-icon>
      <span class="sval" id="t-in"></span>
    </div>
  </div>

  <div class="div"></div>

  <div class="ctrl">
    <button class="btn" id="btn-lock">
      <ha-icon id="ico-lock"></ha-icon><span id="lbl-lock"></span>
    </button>
    <button class="btn" id="btn-trunk">
      <ha-icon id="ico-trunk" icon="mdi:car-back"></ha-icon><span id="lbl-trunk"></span>
    </button>
    <button class="btn" id="btn-blink">
      <ha-icon icon="mdi:car-emergency"></ha-icon><span>Поиск</span>
    </button>
    <button class="btn" id="btn-prep">
      <ha-icon icon="mdi:car-clock"></ha-icon><span>Прогрев</span>
    </button>
    <button class="btn" id="btn-heat">
      <ha-icon icon="mdi:heat-wave"></ha-icon><span>Обогрев</span>
    </button>
    <button class="btn" id="btn-cool2">
      <ha-icon icon="mdi:snowflake"></ha-icon><span>Охлажд.</span>
    </button>
    <button class="btn" id="btn-cloff">
      <ha-icon icon="mdi:fan-off"></ha-icon><span>Стоп климат</span>
    </button>
    <button class="btn" id="btn-proff">
      <ha-icon icon="mdi:stop-circle-outline"></ha-icon><span>Стоп прогрев</span>
    </button>
  </div>
</ha-card>`;

    // Обработчики — навешиваются один раз
    const e = this._entities;
    this._q("btn-odo")  ?.addEventListener("click", () => this._more(e.odometer));
    this._q("btn-bat")  ?.addEventListener("click", () => this._more(e.battery_pct));
    this._q("btn-fuel") ?.addEventListener("click", () => this._more(e.fuel_pct));
    this._q("btn-cool") ?.addEventListener("click", () => this._more(e.coolant_temp));
    this._q("btn-volt") ?.addEventListener("click", () => this._more(e.voltage_12v));
    this._q("btn-out")  ?.addEventListener("click", () => this._more(e.outside_temp));
    this._q("btn-in")   ?.addEventListener("click", () => this._more(e.inboard_temp));

    this._q("btn-lock")?.addEventListener("click", () => {
      const locked = this._s(e.central_lock)?.state === "locked";
      this._call("lock", locked ? "unlock" : "lock", e.central_lock);
    });
    this._q("btn-trunk")?.addEventListener("click", () => {
      const open = this._s(e.trunk)?.state === "on";
      this._call("button", "press", open ? e.trunk_close : e.trunk_open);
    });
    this._q("btn-blink") ?.addEventListener("click", () => this._call("button", "press", e.blink));
    this._q("btn-prep")  ?.addEventListener("click", () => this._call("button", "press", e.prepare_on));
    this._q("btn-heat")  ?.addEventListener("click", () => this._call("button", "press", e.heating_on));
    this._q("btn-cool2") ?.addEventListener("click", () => this._call("button", "press", e.cooling_on));
    this._q("btn-cloff") ?.addEventListener("click", () => this._call("button", "press", e.heating_off));
    this._q("btn-proff") ?.addEventListener("click", () => this._call("button", "press", e.prepare_off));

    this._built = true;
    this._update();
  }

  // -----------------------------------------------------------------------
  // Обновление значений без пересборки DOM
  // -----------------------------------------------------------------------
  _update() {
    if (!this._built) return;
    const e = this._entities;

    const online   = this._s(e.online)?.state === "on";
    const locked   = this._s(e.central_lock)?.state === "locked";
    const trunkOn  = this._s(e.trunk)?.state === "on";
    const model    = this._v(e.car_model, "Evolute");
    const year     = this._v(e.car_year, "");
    const vin      = this._v(e.vin, "");

    this._set("t-model",  `${model}${year && year !== "unavailable" ? " (" + year + ")" : ""}`);
    this._set("t-vin",    vin !== "unavailable" ? vin : "");
    this._set("t-odo",    `${this._n(e.odometer)} км`);
    this._css("t-dot",   "background", online ? "#5cbc63" : "#a8a8a8");

    this._css("fill-bat",  "width", `${this._pct(e.battery_pct)}%`);
    this._css("fill-fuel", "width", `${this._pct(e.fuel_pct)}%`);
    this._set("btn-bat",  `${this._n(e.battery_pct)}% / ${this._n(e.remains_mileage)} км`);
    this._set("btn-fuel", `${this._n(e.fuel_pct)}% / ${this._n(e.remains_mileage_fuel)} км`);

    this._set("t-cool", `${this._n(e.coolant_temp, 1)}°C`);
    this._set("t-volt", `${this._n(e.voltage_12v, 2)} В`);
    this._set("t-out",  `${this._n(e.outside_temp, 1)}°C`);
    this._set("t-in",   `${this._n(e.inboard_temp, 1)}°C`);

    this._q("btn-lock")?.classList.toggle("on", !locked);
    this._q("ico-lock")?.setAttribute("icon", locked ? "mdi:lock" : "mdi:lock-open-variant");
    this._set("lbl-lock", locked ? "Закрыт" : "Открыт");

    this._q("btn-trunk")?.classList.toggle("on", trunkOn);
    this._q("ico-trunk")?.setAttribute("icon", trunkOn ? "mdi:car-back" : "mdi:car-back");
    this._set("lbl-trunk", trunkOn ? "Закрыть" : "Багажник");
  }

  _set(id, text)         { const el = this._q(id); if (el) el.textContent = text; }
  _css(id, prop, val)    { const el = this._q(id); if (el) el.style[prop] = val; }

  getCardSize() { return 4; }
  static getStubConfig() { return {}; }
}

customElements.define("evolute-card", EvolUteCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "evolute-card",
  name: "Evolute",
  description: "Карточка управления автомобилем Evolute",
  documentationURL: "https://github.com/Tamahome-M/evolute-ha",
});
