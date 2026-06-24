/*! Evolute Card — universal Lovelace card for the Evolute (evassist) integration.
 *  Auto-discovers the Evolute device and matches entities by translation_key,
 *  so it works regardless of car model, language or auto-generated entity_ids.
 *  No build step, no dependencies. MIT License.
 */
const EVOLUTE_CARD_VERSION = "1.2.0";

// translation_key -> role. These keys come from the integration's entity
// descriptions and are stable across installs and locales.
const KEYS = {
  // sensors
  odometer: "odometer",
  battery_pct: "battery_pct",
  remains_mileage: "remains_mileage",
  fuel_pct: "fuel_pct",
  remains_mileage_fuel: "remains_mileage_fuel",
  coolant_temp: "coolant_temp",
  voltage_12v: "voltage_12v",
  outside_temp: "outside_temp",
  inboard_temp: "inboard_temp",
  data_time: "sensor_time",
  vin: "vin",
  // binary sensors
  online: "online",
  trunk: "trunk",
  prepare_running: "prepare_running",
  // controls
  lock: "central_lock",
  trunk_open: "trunk_open",
  trunk_close: "trunk_close",
  blink: "blink",
  prepare_on: "prepare_on",
  prepare_off: "prepare_off",
  // prepare params (numbers)
  p_temp: "prepare_temp",
  p_duration: "prepare_duration",
  p_fl: "prepare_seat_fl",
  p_fr: "prepare_seat_fr",
  p_rl: "prepare_seat_rl",
  p_rr: "prepare_seat_rr",
  p_wheel: "prepare_wheel",
  // tracker
  tracker: "tracker",
};

const UNAVAILABLE = new Set(["unavailable", "unknown", "none", "", undefined, null]);

class EvoluteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._deviceId = null;
    this._map = {};      // role -> entity_id
    this._sig = "";      // render signature to skip redundant repaints
    this._built = false;
    this._mapEl = null;
  }

  setConfig(config) {
    this._config = config || {};
    this._deviceId = null;
    this._sig = "";
    // Runtime open-state of the prepare panel; seeded from config, then driven
    // by the user. Persisted across re-renders so it doesn't collapse on click.
    this._prepOpen = !!this._config.prepare_open;
  }

  getCardSize() {
    return this._config.show_map ? 8 : 5;
  }

  static getStubConfig() {
    return { show_map: true };
  }

  set hass(hass) {
    this._hass = hass;
    if (!hass) return;
    this._resolve();
    this._render();
  }

  // ---- discovery -----------------------------------------------------------

  _evoluteEntities() {
    const ents = this._hass.entities || {};
    return Object.values(ents).filter((e) => e && e.platform === "evolute");
  }

  _resolve() {
    const all = this._evoluteEntities();
    if (!all.length) {
      this._deviceId = null;
      this._map = {};
      return;
    }
    // choose device
    let deviceId = this._config.device || null;
    if (!deviceId) {
      const devs = [...new Set(all.map((e) => e.device_id).filter(Boolean))];
      deviceId = devs[0] || null;
    }
    this._deviceId = deviceId;
    // build translation_key -> entity_id for this device
    const map = {};
    for (const e of all) {
      if (deviceId && e.device_id !== deviceId) continue;
      if (e.translation_key) map[e.translation_key] = e.entity_id;
    }
    this._map = map;
  }

  // ---- helpers -------------------------------------------------------------

  _eid(role) { return this._map[KEYS[role]]; }

  _st(role) {
    const id = this._eid(role);
    return id ? this._hass.states[id] : undefined;
  }

  _val(role) {
    const s = this._st(role);
    return s ? s.state : undefined;
  }

  _num(role, digits) {
    const v = Number(this._val(role));
    if (!Number.isFinite(v)) return null;
    return digits == null ? v : v.toFixed(digits);
  }

  _has(role) { return !!this._eid(role); }

  _device() {
    const d = this._hass.devices || {};
    return (this._deviceId && d[this._deviceId]) || null;
  }

  _title() {
    const dev = this._device();
    if (dev) return dev.name_by_user || dev.name || "Evolute";
    return "Evolute";
  }

  _vin() {
    const dev = this._device();
    if (dev && dev.serial_number) return dev.serial_number;
    const v = this._val("vin");
    return UNAVAILABLE.has(v) ? null : v;
  }

  // ---- actions -------------------------------------------------------------

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      detail: { entityId }, bubbles: true, composed: true,
    }));
  }

  _press(role) {
    const id = this._eid(role);
    if (id) this._hass.callService("button", "press", { entity_id: id });
  }

  _lockToggle() {
    const s = this._st("lock");
    if (!s) return;
    const svc = s.state === "locked" ? "unlock" : "lock";
    this._hass.callService("lock", svc, { entity_id: s.entity_id });
  }

  _setNumber(role, value) {
    const id = this._eid(role);
    if (id) this._hass.callService("number", "set_value", { entity_id: id, value });
  }

  _bump(role, dir) {
    const s = this._st(role);
    if (!s) return;
    const a = s.attributes || {};
    const step = Number(a.step) || 1;
    const min = a.min != null ? Number(a.min) : -Infinity;
    const max = a.max != null ? Number(a.max) : Infinity;
    let v = Number(s.state) || 0;
    v = Math.min(max, Math.max(min, v + dir * step));
    this._setNumber(role, v);
  }

  _cycleSeat(role) {
    const s = this._st(role);
    if (!s) return;
    const max = Number((s.attributes || {}).max) || 3;
    let v = Number(s.state) || 0;
    v = v >= max ? 0 : v + 1;
    this._setNumber(role, v);
  }

  // ---- rendering -----------------------------------------------------------

  _signature() {
    // Repaint only when something visible changes.
    const roles = ["odometer", "online", "battery_pct", "remains_mileage",
      "fuel_pct", "remains_mileage_fuel", "coolant_temp", "voltage_12v",
      "outside_temp", "inboard_temp", "data_time", "lock", "trunk", "prepare_running",
      "p_temp", "p_duration", "p_fl", "p_fr", "p_rl", "p_rr", "p_wheel"];
    return this._deviceId + "|" + roles.map((r) => this._val(r)).join(",");
  }

  _render() {
    if (!this._hass) return;

    if (!this._deviceId) {
      this.shadowRoot.innerHTML =
        `<ha-card><div style="padding:16px">Не найдено устройство Evolute.
        Убедитесь, что интеграция установлена, или задайте <code>device:</code> в конфигурации карточки.</div></ha-card>`;
      this._built = false;
      return;
    }

    const sig = this._signature();
    if (this._built && sig === this._sig) {
      this._syncMap();
      return;
    }
    this._sig = sig;

    const num = (r, d) => { const v = this._num(r, d); return v == null ? "—" : v; };
    const online = this._val("online") === "on";
    const dot = online ? "var(--success-color,#5cbc63)" : "var(--disabled-color,#a8a8a8)";

    const hasFuel = this._has("fuel_pct") && !UNAVAILABLE.has(this._val("fuel_pct"));
    const battPct = Math.max(0, Math.min(100, Number(this._val("battery_pct")) || 0));
    const fuelPct = Math.max(0, Math.min(100, Number(this._val("fuel_pct")) || 0));

    const lockS = this._st("lock");
    const locked = lockS && lockS.state === "locked";
    const trunkOpen = this._val("trunk") === "on";
    const preparing = this._val("prepare_running") === "on";

    const cells = [
      ["coolant_temp", "mdi:thermometer-water", num("coolant_temp", 1) + "°C"],
      ["voltage_12v", "mdi:car-battery", num("voltage_12v", 2) + " В"],
      ["outside_temp", "mdi:weather-partly-cloudy", num("outside_temp", 1) + "°C"],
      ["inboard_temp", "mdi:car-seat", num("inboard_temp", 1) + "°C"],
    ].filter(([r]) => this._has(r));

    this.shadowRoot.innerHTML = `
      ${this._styles()}
      <ha-card>
        <div class="wrap">
          <div class="head">
            <div class="odo" data-act="mi" data-role="odometer">
              <span class="dot" style="background:${dot}"></span>
              <ha-icon icon="mdi:counter"></ha-icon>
              <span>${num("odometer", 0)} км</span>
            </div>
            <div class="model">
              <div class="m">${this._escape(this._title())}</div>
              <div class="vin">${this._escape(this._vin() || "—")}</div>
            </div>
          </div>

          <div class="bars">
            ${hasFuel ? this._bar("mdi:fuel", fuelPct) : ""}
            ${this._bar("mdi:lightning-bolt", battPct)}
            ${hasFuel ? this._barVal(num("fuel_pct", 0) + "% / " + num("remains_mileage_fuel", 0) + "км") : ""}
            ${this._barVal(num("battery_pct", 0) + "% / " + num("remains_mileage", 0) + "км")}
          </div>

          ${cells.length ? `<div class="cells">${cells.map(([r, ic, txt]) => `
            <div class="cell" data-act="mi" data-role="${r}">
              <div class="cv">${txt}</div>
              <ha-icon class="cl" icon="${ic}"></ha-icon>
            </div>`).join("")}</div>` : ""}

          <div class="ctrls">
            ${lockS ? this._btn("lock", locked ? "mdi:lock" : "mdi:lock-open-variant",
              locked ? "Закрыт" : "Открыт", locked ? "" : "warn") : ""}
            ${this._has("trunk_open") ? this._btn("trunk",
              "mdi:car-back", trunkOpen ? "Багажник открыт" : "Багажник", trunkOpen ? "warn" : "") : ""}
            ${this._has("blink") ? this._btn("blink", "mdi:car-light-high", "Сигнал и фары", "") : ""}
            ${this._has("prepare_on") ? this._btn("prepare", "mdi:car-clock",
              preparing ? "Предпрогрев…" : "Предпрогрев", preparing ? "active" : "") : ""}
          </div>

          ${this._preparePanel()}

          ${this._dataTimeRow()}
        </div>
        ${this._config.show_map && this._has("tracker") ? `<div class="map" id="evmap"></div>` : ""}
      </ha-card>`;

    this._bind();
    this._built = true;
    this._mapEl = null;   // old map (if any) was destroyed by the innerHTML rebuild
    this._syncMap();
  }

  _bar(icon, pct) {
    return `<div class="bar"><ha-icon icon="${icon}"></ha-icon>
      <div class="track"><div class="fill" style="width:${pct}%"></div></div></div>`;
  }
  _barVal(txt) { return `<div class="barval">${txt}</div>`; }

  _lang() {
    return (this._hass.locale && this._hass.locale.language) || "ru";
  }

  _dataTimeRow() {
    const s = this._st("data_time");
    if (!s || UNAVAILABLE.has(s.state)) return "";
    const d = new Date(s.state);
    if (isNaN(d.getTime())) return "";
    const lang = this._lang();
    const abs = d.toLocaleString(lang, {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
    let rel = "";
    try {
      const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
      const diff = (d.getTime() - Date.now()) / 1000;
      const units = [["year", 31536000], ["month", 2592000], ["day", 86400],
        ["hour", 3600], ["minute", 60], ["second", 1]];
      for (const [u, sec] of units) {
        if (Math.abs(diff) >= sec || u === "second") {
          rel = " (" + rtf.format(Math.round(diff / sec), u) + ")";
          break;
        }
      }
    } catch (e) { /* Intl unavailable — show absolute only */ }
    return `<div class="foot" data-act="mi" data-role="data_time">
      <ha-icon icon="mdi:timeline-clock"></ha-icon>
      <span>Время данных: ${abs}${rel}</span>
    </div>`;
  }

  _btn(role, icon, label, cls) {
    return `<button class="ctrl ${cls}" data-act="ctrl" data-role="${role}">
      <ha-icon icon="${icon}"></ha-icon><span>${label}</span></button>`;
  }

  _preparePanel() {
    if (this._config.hide_prepare) return "";
    if (!this._has("p_temp") && !this._has("p_duration")) return "";
    const stepper = (role, unit) => {
      if (!this._has(role)) return "";
      const v = this._val(role);
      return `<div class="step">
        <button data-act="num" data-role="${role}" data-dir="-1">−</button>
        <span>${UNAVAILABLE.has(v) ? "—" : v}${unit}</span>
        <button data-act="num" data-role="${role}" data-dir="1">+</button>
      </div>`;
    };
    const seat = (role, lbl) => {
      if (!this._has(role)) return "";
      const v = Number(this._val(role)) || 0;
      return `<button class="seat ${v > 0 ? "on" : ""}" data-act="seat" data-role="${role}">
        <ha-icon icon="mdi:car-seat-heater"></ha-icon><span>${lbl}${v > 0 ? " " + v : ""}</span></button>`;
    };
    const wheel = () => {
      if (!this._has("p_wheel")) return "";
      const v = Number(this._val("p_wheel")) || 0;
      return `<button class="seat ${v > 0 ? "on" : ""}" data-act="seat" data-role="p_wheel">
        <ha-icon icon="mdi:steering"></ha-icon><span>Руль</span></button>`;
    };
    return `
      <details class="prep" ${this._prepOpen ? "open" : ""}>
        <summary><ha-icon icon="mdi:tune"></ha-icon> Параметры предпрогрева</summary>
        <div class="prow">
          <div class="plab">Температура</div>${stepper("p_temp", "°C")}
        </div>
        <div class="prow">
          <div class="plab">Длительность</div>${stepper("p_duration", " мин")}
        </div>
        <div class="seats">
          ${seat("p_fl", "ПЛ")}${seat("p_fr", "ПП")}${seat("p_rl", "ЗЛ")}${seat("p_rr", "ЗП")}${wheel()}
        </div>
      </details>`;
  }

  _bind() {
    const det = this.shadowRoot.querySelector("details.prep");
    if (det) det.addEventListener("toggle", () => { this._prepOpen = det.open; });
    this.shadowRoot.querySelectorAll("[data-act]").forEach((el) => {
      const act = el.getAttribute("data-act");
      const role = el.getAttribute("data-role");
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (act === "mi") { const id = this._eid(role); if (id) this._moreInfo(id); }
        else if (act === "num") this._bump(role, Number(el.getAttribute("data-dir")));
        else if (act === "seat") this._cycleSeat(role);
        else if (act === "ctrl") this._ctrl(role);
      });
    });
  }

  _ctrl(role) {
    switch (role) {
      case "lock": this._lockToggle(); break;
      case "trunk":
        this._press(this._val("trunk") === "on" ? "trunk_close" : "trunk_open"); break;
      case "blink": this._press("blink"); break;
      case "prepare":
        this._press(this._val("prepare_running") === "on" ? "prepare_off" : "prepare_on"); break;
    }
  }

  // Lazily create & feed the <ha-map> element (optional).
  _syncMap() {
    if (!this._config.show_map || !this._has("tracker")) { this._mapEl = null; return; }
    const holder = this.shadowRoot.getElementById("evmap");
    if (!holder) return;
    if (!this._mapEl) {
      try {
        this._mapEl = document.createElement("ha-map");
        this._mapEl.style.height = (this._config.map_height || 250) + "px";
        this._mapEl.style.display = "block";
        this._mapEl.style.borderRadius = "0 0 12px 12px";
        this._mapEl.style.overflow = "hidden";
        holder.appendChild(this._mapEl);
      } catch (e) { return; }
    }
    this._mapEl.hass = this._hass;
    this._mapEl.entities = [this._eid("tracker")];
    this._mapEl.autoFit = true;
    if (this._config.map_zoom) this._mapEl.zoom = this._config.map_zoom;
  }

  _escape(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  _styles() {
    return `<style>
      ha-card { overflow: hidden; }
      .wrap { padding: 16px 16px 12px; display: flex; flex-direction: column; gap: 10px; }
      .head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
      .odo { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 24px; font-weight: 600;
             color: var(--primary-text-color); }
      .odo ha-icon { --mdc-icon-size: 24px; color: var(--state-icon-color, var(--primary-color)); }
      .dot { width: 14px; height: 14px; border-radius: 50%; flex: 0 0 auto; }
      .model { text-align: right; line-height: 1.1; }
      .model .m { font-size: 22px; font-weight: 500; color: var(--primary-text-color); }
      .model .vin { font-size: 13px; color: var(--secondary-text-color); }
      .bars { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; align-items: center; }
      .bar { display: flex; align-items: center; gap: 10px; }
      .bar ha-icon { --mdc-icon-size: 20px; color: var(--primary-color); }
      .track { height: 6px; flex: 1; border-radius: 6px; overflow: hidden;
               background: var(--divider-color, #d5d8de); }
      .fill { height: 100%; background: var(--primary-color); }
      .barval { font-size: 20px; font-weight: 500; }
      .cells { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 4px; }
      .cell { cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
      .cv { font-size: 18px; font-weight: 500; color: var(--primary-text-color); }
      .cl { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
      .ctrls { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
      .ctrl { flex: 1 1 auto; min-width: 90px; display: flex; flex-direction: column; align-items: center;
              gap: 4px; padding: 10px 6px; border: none; border-radius: 12px; cursor: pointer;
              background: var(--secondary-background-color, #e6e6e8); color: var(--primary-text-color);
              font-size: 12px; }
      .ctrl ha-icon { --mdc-icon-size: 24px; }
      .ctrl:hover { filter: brightness(0.97); }
      .ctrl.warn ha-icon { color: var(--warning-color, #e08b00); }
      .ctrl.active { background: color-mix(in srgb, var(--primary-color) 22%, transparent); }
      .ctrl.active ha-icon { color: var(--primary-color); }
      .prep { margin-top: 4px; border-top: 1px solid var(--divider-color); padding-top: 6px; }
      .prep summary { cursor: pointer; font-size: 13px; color: var(--secondary-text-color);
                      display: flex; align-items: center; gap: 6px; }
      .prep summary ha-icon { --mdc-icon-size: 18px; }
      .prow { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
      .plab { font-size: 14px; color: var(--primary-text-color); }
      .step { display: flex; align-items: center; gap: 10px; }
      .step button { width: 30px; height: 30px; border-radius: 8px; border: none; cursor: pointer;
                     font-size: 18px; background: var(--secondary-background-color, #e6e6e8);
                     color: var(--primary-text-color); }
      .step span { min-width: 64px; text-align: center; font-weight: 500; }
      .seats { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
      .seat { display: flex; align-items: center; gap: 4px; padding: 6px 10px; border: none;
              border-radius: 10px; cursor: pointer; font-size: 12px;
              background: var(--secondary-background-color, #e6e6e8); color: var(--primary-text-color); }
      .seat.on { background: color-mix(in srgb, var(--warning-color, #e08b00) 28%, transparent); }
      .seat.on ha-icon { color: var(--warning-color, #e08b00); }
      .seat ha-icon { --mdc-icon-size: 18px; }
      .foot { margin-top: 8px; display: flex; align-items: center; gap: 6px; cursor: pointer;
              font-size: 12px; color: var(--secondary-text-color); }
      .foot ha-icon { --mdc-icon-size: 16px; }
      .map { margin: 4px -0 -0; }
    </style>`;
  }
}

if (!customElements.get("evolute-card")) {
  customElements.define("evolute-card", EvoluteCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "evolute-card",
  name: "Evolute Card",
  description: "Панель и управление автомобилем Evolute (интеграция evassist).",
  preview: false,
  documentationURL: "https://github.com/Tamahome-M/evolute-card",
});

console.info(
  `%c EVOLUTE-CARD %c v${EVOLUTE_CARD_VERSION} `,
  "color:#fff;background:#3f8fc7;font-weight:700;border-radius:3px 0 0 3px;padding:2px 4px",
  "color:#3f8fc7;background:#0000;font-weight:700;padding:2px 4px"
);
