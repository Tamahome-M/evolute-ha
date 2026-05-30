/**
 * Evolute Lovelace Card
 * Автоматически находит все сущности интеграции Evolute.
 * Использование: type: custom:evolute-card
 */

class EvolUteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._deviceId = null;
    this._entities = {};
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    this._discoverEntities();
    this._render();
  }

  // ---------------------------------------------------------------
  // Поиск устройства и сущностей через hass.entities / hass.devices
  // ---------------------------------------------------------------
  _discoverEntities() {
    const hass = this._hass;
    if (!hass.entities || !hass.devices) return;

    // Ищем устройство платформы evolute
    let deviceId = this._config.device_id || null;

    if (!deviceId) {
      // Находим первое устройство, у которого есть entity от интеграции evolute
      for (const [entity_id, entry] of Object.entries(hass.entities)) {
        if (entry.platform === "evolute") {
          deviceId = entry.device_id;
          break;
        }
      }
    }

    if (!deviceId) return;
    this._deviceId = deviceId;

    // Собираем все entity этого устройства по уникальному суффиксу
    const map = {};
    for (const [entity_id, entry] of Object.entries(hass.entities)) {
      if (entry.device_id !== deviceId) continue;
      const domain = entity_id.split(".")[0];
      // Ключ — translation_key или unique_id суффикс
      const key = entry.translation_key || entry.unique_id?.split("_").slice(-2).join("_") || entity_id;
      map[entity_id] = { domain, key, entry };
    }

    // Находим нужные entity по translation_key (задаётся в entity_description.key)
    const find = (keys, domain) => {
      if (!Array.isArray(keys)) keys = [keys];
      for (const [eid, { entry, domain: d }] of Object.entries(map)) {
        if (domain && d !== domain) continue;
        if (keys.includes(entry.translation_key)) return eid;
      }
      return null;
    };

    this._entities = {
      battery_pct:     find("battery_pct", "sensor"),
      remains_mileage: find("remains_mileage", "sensor"),
      fuel_pct:        find("fuel_pct", "sensor"),
      remains_mileage_fuel: find("remains_mileage_fuel", "sensor"),
      odometer:        find("odometer", "sensor"),
      coolant_temp:    find("coolant_temp", "sensor"),
      voltage_12v:     find("voltage_12v", "sensor"),
      outside_temp:    find("outside_temp", "sensor"),
      inboard_temp:    find("inboard_temp", "sensor"),
      car_model:       find("car_model", "sensor"),
      car_year:        find("car_year", "sensor"),
      vin:             find("vin", "sensor"),
      online:          find("online", "binary_sensor"),
      trunk:           find("trunk", "binary_sensor"),
      central_lock:    find("central_lock", "lock"),
      trunk_open:      find("trunk_open", "button"),
      trunk_close:     find("trunk_close", "button"),
      blink:           find("blink", "button"),
      prepare_on:      find("prepare_on", "button"),
      prepare_off:     find("prepare_off", "button"),
      heating_on:      find("heating_on", "button"),
      heating_off:     find("heating_off", "button"),
      cooling_on:      find("cooling_on", "button"),
      cooling_off:     find("cooling_off", "button"),
      tracker:         find("tracker", "device_tracker"),
    };
  }

  // ---------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------
  _state(eid) {
    if (!eid || !this._hass) return null;
    return this._hass.states[eid] || null;
  }

  _val(eid, fallback = "—") {
    const s = this._state(eid);
    return s ? s.state : fallback;
  }

  _numVal(eid, decimals = 0) {
    const v = parseFloat(this._val(eid, ""));
    if (isNaN(v)) return "—";
    return decimals > 0 ? v.toFixed(decimals) : String(Math.round(v));
  }

  _callService(domain, service, eid) {
    this._hass.callService(domain, service, { entity_id: eid });
  }

  _moreInfo(eid) {
    if (!eid) return;
    const ev = new CustomEvent("hass-more-info", {
      detail: { entityId: eid },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(ev);
  }

  // ---------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------
  _render() {
    if (!this._hass || !this._deviceId) {
      this.shadowRoot.innerHTML = `
        <style>
          .placeholder { padding: 16px; font-size: 14px;
            color: var(--secondary-text-color); font-family: var(--paper-font-body1_-_font-family); }
        </style>
        <div class="placeholder">Ищу устройство Evolute…</div>`;
      return;
    }

    const e = this._entities;
    const hass = this._hass;

    const battery  = this._numVal(e.battery_pct);
    const batKm    = this._numVal(e.remains_mileage);
    const fuel     = this._numVal(e.fuel_pct);
    const fuelKm   = this._numVal(e.remains_mileage_fuel);
    const odo      = this._numVal(e.odometer);
    const coolant  = this._numVal(e.coolant_temp, 1);
    const volt     = this._numVal(e.voltage_12v, 2);
    const outTemp  = this._numVal(e.outside_temp, 1);
    const inTemp   = this._numVal(e.inboard_temp, 1);

    const isOnline = this._state(e.online)?.state === "on";
    const isLocked = this._state(e.central_lock)?.state === "locked";
    const trunkOpen = this._state(e.trunk)?.state === "on";

    const model = this._val(e.car_model, "Evolute");
    const year  = this._val(e.car_year, "");

    const batPct  = Math.max(0, Math.min(100, parseFloat(battery) || 0));
    const fuelPct = Math.max(0, Math.min(100, parseFloat(fuel) || 0));

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.06));
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .header {
          display: flex; justify-content: space-between; align-items: center;
          margin-bottom: 14px;
        }
        .title {
          font-size: 20px; font-weight: 600;
          color: var(--primary-text-color);
        }
        .subtitle {
          font-size: 13px; color: var(--secondary-text-color); margin-top: 2px;
        }
        .status-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: ${isOnline ? "#4caf50" : "#9e9e9e"};
          flex-shrink: 0;
        }
        .header-right { display: flex; align-items: center; gap: 8px; }
        .odo {
          font-size: 14px; font-weight: 500;
          color: var(--primary-text-color);
          cursor: pointer;
        }
        .bar-row {
          display: flex; align-items: center; gap: 10px; margin: 6px 0;
        }
        .bar-icon { --mdc-icon-size: 18px; color: var(--primary-color, #3b82f6); flex-shrink: 0; }
        .bar-wrap {
          flex: 1; height: 6px; border-radius: 6px;
          background: var(--divider-color, #e0e0e0); overflow: hidden;
        }
        .bar-fill {
          height: 100%; border-radius: 6px;
          background: var(--primary-color, #3b82f6);
          transition: width 0.4s;
        }
        .bar-label {
          font-size: 14px; font-weight: 500; white-space: nowrap;
          color: var(--primary-text-color); min-width: 100px; text-align: right;
          cursor: pointer;
        }
        .stats {
          display: grid; grid-template-columns: repeat(4, 1fr);
          gap: 10px; margin: 14px 0;
        }
        .stat {
          display: flex; flex-direction: column; align-items: center;
          gap: 4px; cursor: pointer;
        }
        .stat-val {
          font-size: 17px; font-weight: 600;
          color: var(--primary-text-color);
        }
        .stat-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
        .divider {
          height: 1px; background: var(--divider-color, #e0e0e0);
          margin: 12px 0;
        }
        .controls {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
        }
        .btn {
          display: flex; flex-direction: column; align-items: center;
          justify-content: center; gap: 6px;
          padding: 10px 4px; border-radius: 10px; cursor: pointer;
          background: var(--secondary-background-color, #f5f5f5);
          border: none; color: var(--primary-text-color);
          font-size: 11px; font-weight: 500; text-align: center;
          font-family: inherit; transition: opacity .15s;
          user-select: none;
        }
        .btn:active { opacity: 0.6; }
        .btn ha-icon { --mdc-icon-size: 22px; }
        .btn.active {
          background: var(--primary-color, #3b82f6);
          color: #fff;
        }
        .btn.active ha-icon { color: #fff; }
        .no-device {
          padding: 16px; font-size: 14px;
          color: var(--secondary-text-color);
        }
      </style>

      <ha-card class="card">
        <div class="header">
          <div>
            <div class="title">${model}${year ? " " + year : ""}</div>
            <div class="subtitle">${isOnline ? "Онлайн" : "Офлайн"}</div>
          </div>
          <div class="header-right">
            <div class="odo" @click="${() => this._moreInfo(e.odometer)}">
              <ha-icon icon="mdi:counter"></ha-icon> ${odo} км
            </div>
            <div class="status-dot"></div>
          </div>
        </div>

        <!-- Батарея -->
        <div class="bar-row">
          <ha-icon class="bar-icon" icon="mdi:lightning-bolt"></ha-icon>
          <div class="bar-wrap">
            <div class="bar-fill" style="width:${batPct}%"></div>
          </div>
          <div class="bar-label" @click="${() => this._moreInfo(e.battery_pct)}">
            ${battery}% / ${batKm}&nbsp;км
          </div>
        </div>

        <!-- Топливо -->
        <div class="bar-row">
          <ha-icon class="bar-icon" icon="mdi:fuel"></ha-icon>
          <div class="bar-wrap">
            <div class="bar-fill" style="width:${fuelPct}%"></div>
          </div>
          <div class="bar-label" @click="${() => this._moreInfo(e.fuel_pct)}">
            ${fuel}% / ${fuelKm}&nbsp;км
          </div>
        </div>

        <!-- Статы -->
        <div class="stats">
          <div class="stat" @click="${() => this._moreInfo(e.coolant_temp)}">
            <ha-icon class="stat-icon" icon="mdi:coolant-temperature"></ha-icon>
            <span class="stat-val">${coolant}°</span>
          </div>
          <div class="stat" @click="${() => this._moreInfo(e.voltage_12v)}">
            <ha-icon class="stat-icon" icon="mdi:car-battery"></ha-icon>
            <span class="stat-val">${volt}&nbsp;В</span>
          </div>
          <div class="stat" @click="${() => this._moreInfo(e.outside_temp)}">
            <ha-icon class="stat-icon" icon="mdi:weather-partly-cloudy"></ha-icon>
            <span class="stat-val">${outTemp}°</span>
          </div>
          <div class="stat" @click="${() => this._moreInfo(e.inboard_temp)}">
            <ha-icon class="stat-icon" icon="mdi:car-seat"></ha-icon>
            <span class="stat-val">${inTemp}°</span>
          </div>
        </div>

        <div class="divider"></div>

        <!-- Кнопки управления -->
        <div class="controls">

          <!-- Замок -->
          <button class="btn ${isLocked ? "" : "active"}"
            @click="${() => isLocked
              ? this._callService("lock", "unlock", e.central_lock)
              : this._callService("lock", "lock", e.central_lock)}">
            <ha-icon icon="${isLocked ? "mdi:lock" : "mdi:lock-open-variant"}"></ha-icon>
            ${isLocked ? "Закрыт" : "Открыт"}
          </button>

          <!-- Багажник -->
          <button class="btn ${trunkOpen ? "active" : ""}"
            @click="${() => trunkOpen
              ? this._callService("button", "press", e.trunk_close)
              : this._callService("button", "press", e.trunk_open)}">
            <ha-icon icon="mdi:car-back"></ha-icon>
            ${trunkOpen ? "Закрыть" : "Багажник"}
          </button>

          <!-- Мигнуть -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.blink)}">
            <ha-icon icon="mdi:car-light-high"></ha-icon>
            Мигнуть
          </button>

          <!-- Предпрогрев -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.prepare_on)}">
            <ha-icon icon="mdi:car-clock"></ha-icon>
            Прогрев
          </button>

          <!-- Обогрев -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.heating_on)}">
            <ha-icon icon="mdi:heat-wave"></ha-icon>
            Обогрев
          </button>

          <!-- Охлаждение -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.cooling_on)}">
            <ha-icon icon="mdi:snowflake"></ha-icon>
            Охлаж.
          </button>

          <!-- Стоп обогрев/охлаждение -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.heating_off)}">
            <ha-icon icon="mdi:fan-off"></ha-icon>
            Стоп климат
          </button>

          <!-- Стоп прогрев -->
          <button class="btn"
            @click="${() => this._callService("button", "press", e.prepare_off)}">
            <ha-icon icon="mdi:stop-circle-outline"></ha-icon>
            Стоп прогрев
          </button>

        </div>
      </ha-card>
    `;

    // Навешиваем обработчики после рендера
    this._attachHandlers();
  }

  _attachHandlers() {
    const root = this.shadowRoot;
    // Клики по stat
    root.querySelectorAll("[\\@click]") && null; // inline handlers не работают в innerHTML — используем делегирование

    // Заменяем @click на data-action и вешаем один listener
    // Пересоздадим элементы с нормальными обработчиками через delegation
    const e = this._entities;

    const actions = {
      "odo":         () => this._moreInfo(e.odometer),
      "bat-label":   () => this._moreInfo(e.battery_pct),
      "fuel-label":  () => this._moreInfo(e.fuel_pct),
      "stat-cool":   () => this._moreInfo(e.coolant_temp),
      "stat-volt":   () => this._moreInfo(e.voltage_12v),
      "stat-out":    () => this._moreInfo(e.outside_temp),
      "stat-in":     () => this._moreInfo(e.inboard_temp),
    };

    // Inline обработчики в innerHTML не выполняются в Shadow DOM.
    // Поэтому переключаемся на полноценный _renderWithHandlers
    this._renderWithHandlers();
  }

  _renderWithHandlers() {
    // Перерисовка с нормальными обработчиками
    const root = this.shadowRoot;
    if (!this._hass || !this._deviceId) return;

    const e = this._entities;

    const battery  = this._numVal(e.battery_pct);
    const batKm    = this._numVal(e.remains_mileage);
    const fuel     = this._numVal(e.fuel_pct);
    const fuelKm   = this._numVal(e.remains_mileage_fuel);
    const odo      = this._numVal(e.odometer);
    const coolant  = this._numVal(e.coolant_temp, 1);
    const volt     = this._numVal(e.voltage_12v, 2);
    const outTemp  = this._numVal(e.outside_temp, 1);
    const inTemp   = this._numVal(e.inboard_temp, 1);

    const isOnline  = this._state(e.online)?.state === "on";
    const isLocked  = this._state(e.central_lock)?.state === "locked";
    const trunkOpen = this._state(e.trunk)?.state === "on";

    const model  = this._val(e.car_model, "Evolute");
    const year   = this._val(e.car_year, "");
    const batPct  = Math.max(0, Math.min(100, parseFloat(battery) || 0));
    const fuelPct = Math.max(0, Math.min(100, parseFloat(fuel) || 0));

    // ---- HTML ----
    const card = root.querySelector(".card");
    if (!card) return;

    // Обновляем только изменяемые части для производительности
    const titleEl = card.querySelector(".title");
    if (titleEl) titleEl.textContent = `${model}${year ? " " + year : ""}`;

    const subtitleEl = card.querySelector(".subtitle");
    if (subtitleEl) subtitleEl.textContent = isOnline ? "Онлайн" : "Офлайн";

    const dotEl = card.querySelector(".status-dot");
    if (dotEl) dotEl.style.background = isOnline ? "#4caf50" : "#9e9e9e";

    const odoEl = card.querySelector(".odo");
    if (odoEl) odoEl.innerHTML = `<ha-icon icon="mdi:counter"></ha-icon> ${odo} км`;

    const barFills = card.querySelectorAll(".bar-fill");
    if (barFills[0]) barFills[0].style.width = `${batPct}%`;
    if (barFills[1]) barFills[1].style.width = `${fuelPct}%`;

    const barLabels = card.querySelectorAll(".bar-label");
    if (barLabels[0]) barLabels[0].textContent = `${battery}% / ${batKm} км`;
    if (barLabels[1]) barLabels[1].textContent = `${fuel}% / ${fuelKm} км`;

    const statVals = card.querySelectorAll(".stat-val");
    if (statVals[0]) statVals[0].textContent = `${coolant}°`;
    if (statVals[1]) statVals[1].textContent = `${volt} В`;
    if (statVals[2]) statVals[2].textContent = `${outTemp}°`;
    if (statVals[3]) statVals[3].textContent = `${inTemp}°`;

    // Кнопки
    const btns = card.querySelectorAll(".btn");
    if (btns[0]) { // замок
      btns[0].className = `btn${isLocked ? "" : " active"}`;
      btns[0].querySelector("ha-icon").setAttribute("icon",
        isLocked ? "mdi:lock" : "mdi:lock-open-variant");
      btns[0].lastChild.textContent = isLocked ? "Закрыт" : "Открыт";
    }
    if (btns[1]) { // багажник
      btns[1].className = `btn${trunkOpen ? " active" : ""}`;
      btns[1].lastChild.textContent = trunkOpen ? "Закрыть" : "Багажник";
    }
  }

  // Первый полный рендер со всеми элементами и обработчиками
  _render() {
    if (!this._hass) return;

    if (!this._deviceId) {
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }
          .msg { padding: 16px; font-size: 14px;
            color: var(--secondary-text-color);
            font-family: var(--paper-font-body1_-_font-family, sans-serif); }
        </style>
        <ha-card><div class="msg">
          Устройство Evolute не найдено. Убедитесь что интеграция настроена.
        </div></ha-card>`;
      return;
    }

    // Если карточка уже построена — только обновляем значения
    if (this.shadowRoot.querySelector(".card")) {
      this._renderWithHandlers();
      return;
    }

    const e = this._entities;
    const battery  = this._numVal(e.battery_pct);
    const batKm    = this._numVal(e.remains_mileage);
    const fuel     = this._numVal(e.fuel_pct);
    const fuelKm   = this._numVal(e.remains_mileage_fuel);
    const odo      = this._numVal(e.odometer);
    const coolant  = this._numVal(e.coolant_temp, 1);
    const volt     = this._numVal(e.voltage_12v, 2);
    const outTemp  = this._numVal(e.outside_temp, 1);
    const inTemp   = this._numVal(e.inboard_temp, 1);
    const isOnline  = this._state(e.online)?.state === "on";
    const isLocked  = this._state(e.central_lock)?.state === "locked";
    const trunkOpen = this._state(e.trunk)?.state === "on";
    const model  = this._val(e.car_model, "Evolute");
    const year   = this._val(e.car_year, "");
    const batPct  = Math.max(0, Math.min(100, parseFloat(battery) || 0));
    const fuelPct = Math.max(0, Math.min(100, parseFloat(fuel) || 0));

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.06));
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .header { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
        .title { font-size:20px; font-weight:600; color:var(--primary-text-color); }
        .subtitle { font-size:13px; color:var(--secondary-text-color); margin-top:2px; }
        .header-right { display:flex; align-items:center; gap:10px; }
        .status-dot { width:10px; height:10px; border-radius:50%; background:${isOnline ? "#4caf50" : "#9e9e9e"}; }
        .odo { font-size:14px; font-weight:500; color:var(--primary-text-color); cursor:pointer; display:flex; align-items:center; gap:4px; }
        .bar-row { display:flex; align-items:center; gap:10px; margin:7px 0; }
        .bar-icon { --mdc-icon-size:18px; color:var(--primary-color,#3b82f6); flex-shrink:0; }
        .bar-wrap { flex:1; height:6px; border-radius:6px; background:var(--divider-color,#e0e0e0); overflow:hidden; }
        .bar-fill { height:100%; border-radius:6px; background:var(--primary-color,#3b82f6); transition:width .4s; }
        .bar-label { font-size:14px; font-weight:500; white-space:nowrap; color:var(--primary-text-color); min-width:110px; text-align:right; cursor:pointer; }
        .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0; }
        .stat { display:flex; flex-direction:column; align-items:center; gap:4px; cursor:pointer; }
        .stat-val { font-size:17px; font-weight:600; color:var(--primary-text-color); }
        .stat-icon { --mdc-icon-size:20px; color:var(--secondary-text-color); }
        .divider { height:1px; background:var(--divider-color,#e0e0e0); margin:12px 0; }
        .controls { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
        .btn {
          display:flex; flex-direction:column; align-items:center; justify-content:center;
          gap:5px; padding:10px 4px; border-radius:10px; cursor:pointer;
          background:var(--secondary-background-color,#f5f5f5);
          border:none; color:var(--primary-text-color);
          font-size:11px; font-weight:500; font-family:inherit;
          text-align:center; transition:opacity .15s; user-select:none;
        }
        .btn:active { opacity:.6; }
        .btn ha-icon { --mdc-icon-size:22px; }
        .btn.active { background:var(--primary-color,#3b82f6); color:#fff; }
        .btn.active ha-icon { color:#fff; }
      </style>
      <ha-card class="card">
        <div class="header">
          <div>
            <div class="title">${model}${year ? " "+year : ""}</div>
            <div class="subtitle">${isOnline ? "Онлайн" : "Офлайн"}</div>
          </div>
          <div class="header-right">
            <div class="odo" id="btn-odo">
              <ha-icon icon="mdi:counter"></ha-icon>${odo} км
            </div>
            <div class="status-dot"></div>
          </div>
        </div>

        <div class="bar-row">
          <ha-icon class="bar-icon" icon="mdi:lightning-bolt"></ha-icon>
          <div class="bar-wrap"><div class="bar-fill" style="width:${batPct}%"></div></div>
          <div class="bar-label" id="btn-bat">${battery}% / ${batKm} км</div>
        </div>
        <div class="bar-row">
          <ha-icon class="bar-icon" icon="mdi:fuel"></ha-icon>
          <div class="bar-wrap"><div class="bar-fill" style="width:${fuelPct}%"></div></div>
          <div class="bar-label" id="btn-fuel">${fuel}% / ${fuelKm} км</div>
        </div>

        <div class="stats">
          <div class="stat" id="btn-cool">
            <ha-icon class="stat-icon" icon="mdi:coolant-temperature"></ha-icon>
            <span class="stat-val">${coolant}°</span>
          </div>
          <div class="stat" id="btn-volt">
            <ha-icon class="stat-icon" icon="mdi:car-battery"></ha-icon>
            <span class="stat-val">${volt} В</span>
          </div>
          <div class="stat" id="btn-out">
            <ha-icon class="stat-icon" icon="mdi:weather-partly-cloudy"></ha-icon>
            <span class="stat-val">${outTemp}°</span>
          </div>
          <div class="stat" id="btn-in">
            <ha-icon class="stat-icon" icon="mdi:car-seat"></ha-icon>
            <span class="stat-val">${inTemp}°</span>
          </div>
        </div>

        <div class="divider"></div>

        <div class="controls">
          <button class="btn${isLocked ? "" : " active"}" id="btn-lock">
            <ha-icon icon="${isLocked ? "mdi:lock" : "mdi:lock-open-variant"}"></ha-icon>
            <span>${isLocked ? "Закрыт" : "Открыт"}</span>
          </button>
          <button class="btn${trunkOpen ? " active" : ""}" id="btn-trunk">
            <ha-icon icon="mdi:car-back"></ha-icon>
            <span>${trunkOpen ? "Закрыть" : "Багажник"}</span>
          </button>
          <button class="btn" id="btn-blink">
            <ha-icon icon="mdi:car-light-high"></ha-icon><span>Мигнуть</span>
          </button>
          <button class="btn" id="btn-prepare">
            <ha-icon icon="mdi:car-clock"></ha-icon><span>Прогрев</span>
          </button>
          <button class="btn" id="btn-heat-on">
            <ha-icon icon="mdi:heat-wave"></ha-icon><span>Обогрев</span>
          </button>
          <button class="btn" id="btn-cool-on">
            <ha-icon icon="mdi:snowflake"></ha-icon><span>Охлаж.</span>
          </button>
          <button class="btn" id="btn-climate-off">
            <ha-icon icon="mdi:fan-off"></ha-icon><span>Стоп климат</span>
          </button>
          <button class="btn" id="btn-prepare-off">
            <ha-icon icon="mdi:stop-circle-outline"></ha-icon><span>Стоп прогрев</span>
          </button>
        </div>
      </ha-card>`;

    // Обработчики
    const q = (id) => this.shadowRoot.getElementById(id);
    q("btn-odo")?.addEventListener("click", () => this._moreInfo(e.odometer));
    q("btn-bat")?.addEventListener("click", () => this._moreInfo(e.battery_pct));
    q("btn-fuel")?.addEventListener("click", () => this._moreInfo(e.fuel_pct));
    q("btn-cool")?.addEventListener("click", () => this._moreInfo(e.coolant_temp));
    q("btn-volt")?.addEventListener("click", () => this._moreInfo(e.voltage_12v));
    q("btn-out")?.addEventListener("click",  () => this._moreInfo(e.outside_temp));
    q("btn-in")?.addEventListener("click",   () => this._moreInfo(e.inboard_temp));

    q("btn-lock")?.addEventListener("click", () => {
      const locked = this._state(e.central_lock)?.state === "locked";
      this._callService("lock", locked ? "unlock" : "lock", e.central_lock);
    });
    q("btn-trunk")?.addEventListener("click", () => {
      const open = this._state(e.trunk)?.state === "on";
      this._callService("button", "press", open ? e.trunk_close : e.trunk_open);
    });
    q("btn-blink")?.addEventListener("click",       () => this._callService("button", "press", e.blink));
    q("btn-prepare")?.addEventListener("click",     () => this._callService("button", "press", e.prepare_on));
    q("btn-heat-on")?.addEventListener("click",     () => this._callService("button", "press", e.heating_on));
    q("btn-cool-on")?.addEventListener("click",     () => this._callService("button", "press", e.cooling_on));
    q("btn-climate-off")?.addEventListener("click", () => this._callService("button", "press", e.heating_off));
    q("btn-prepare-off")?.addEventListener("click", () => this._callService("button", "press", e.prepare_off));
  }

  getCardSize() { return 4; }

  static getConfigElement() {
    return document.createElement("evolute-card-editor");
  }

  static getStubConfig() {
    return {};
  }
}

// Простой редактор конфига (опционально указать device_id если несколько авто)
class EvolUteCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  get _device_id() { return this._config?.device_id || ""; }

  set hass(hass) {
    if (!this.shadowRoot.querySelector("ha-form")) {
      this.shadowRoot.innerHTML = `
        <style>
          ha-textfield { display:block; width:100%; margin:8px 0; }
          p { font-size:13px; color:var(--secondary-text-color); margin:8px 0 0; }
        </style>
        <p>Оставьте пустым — карточка найдёт Evolute автоматически.<br>
           Укажите device_id если у вас несколько автомобилей.</p>
        <ha-textfield
          label="Device ID (необязательно)"
          .value="${this._device_id}"
          @input="${(e) => this._valueChanged(e)}">
        </ha-textfield>`;
      this.attachShadow({ mode: "open" });
    }
  }

  _valueChanged(e) {
    const config = { ...this._config, device_id: e.target.value || undefined };
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config } }));
  }
}

customElements.define("evolute-card", EvolUteCard);
customElements.define("evolute-card-editor", EvolUteCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "evolute-card",
  name: "Evolute",
  description: "Карточка управления автомобилем Evolute",
  preview: false,
  documentationURL: "https://github.com/Tamahome-M/evolute-ha",
});

console.info(
  "%c EVOLUTE-CARD %c загружена ",
  "color:#fff;background:#1a1a2e;padding:2px 6px;border-radius:4px 0 0 4px;font-weight:bold",
  "color:#1a1a2e;background:#e8e8e8;padding:2px 6px;border-radius:0 4px 4px 0"
);
