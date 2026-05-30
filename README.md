# Evolute для Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Нативная интеграция автомобилей **Evolute** (evassist.ru) для Home Assistant.  
Работает **без аддонов и прокси** — напрямую обращается к `app.evassist.ru`.

---

## Возможности

| Тип | Объекты |
|-----|---------|
| 🔢 Сенсоры | Заряд батареи, запас хода (батарея + топливо), одометр, все температуры (улица / салон / батарея / ОЖ), напряжение 12В АКБ, обороты, климат (скорость вентилятора, цель / текущая t°), скорость GPS, высота, курс, спутники, VIN, модель, год, цвет |
| 🔴 Бинарные сенсоры | Зажигание, онлайн, все 4 двери, багажник, замок, климат, обогрев лобового стекла, фары, предпрогрев (запущен / доступен), припаркован |
| 🔒 Замок | Центральный замок (lock/unlock из HA) |
| 🔘 Кнопки | Обогрев вкл/выкл, охлаждение вкл/выкл, предпрогрев вкл/выкл, открыть/закрыть багажник, мигнуть фарами |
| 📍 Трекер | GPS-позиция автомобиля на карте HA |

---

## Установка через HACS

1. В HACS нажмите **⋮ → Custom repositories**
2. Введите URL этого репозитория, тип — **Integration**
3. Нажмите **Add**
4. Найдите **Evolute** в списке интеграций, установите
5. Перезапустите Home Assistant
6. **Настройки → Интеграции → Добавить → Evolute**

---

## Ручная установка

Скопируйте папку `custom_components/evolute` в директорию `config/custom_components/` вашего Home Assistant и перезапустите.

---

## Как получить токены и Car ID

### Токены

1. Откройте [app.evassist.ru](https://app.evassist.ru) в браузере и войдите в аккаунт
2. Откройте **DevTools** (F12) → вкладка **Application** → раздел **Cookies** → `https://app.evassist.ru`
3. Скопируйте значения:
   - `evy-platform-access` → поле **Access Token**
   - `evy-platform-refresh` → поле **Refresh Token**

### Car ID

Car ID — это хэш вашего автомобиля. Его можно найти:
- В адресной строке браузера после входа на страницу автомобиля
- Во вкладке **Network** DevTools в запросах к `/car-service/tbox/<ID>/info`

---

## Dashboard карточка

В папке [`lovelace/card.yaml`](lovelace/card.yaml) лежит готовая карточка.

**Требует:** [button-card](https://github.com/custom-cards/button-card) (устанавливается через HACS → Frontend).

### Как добавить

1. Установите **button-card** через HACS → Frontend
2. Скопируйте содержимое `lovelace/card.yaml`
3. В дашборде нажмите **Добавить карточку → Вручную (Manual)** и вставьте YAML
4. Замените все `EVOLUTE_*` на ваши реальные entity_id

### Как найти свои entity_id

Перейдите в **Разработчик → Состояния**, введите в поиск `evolute` — увидите все entity вашей интеграции. Нужные суффиксы:

| Placeholder в карточке | Что это | Пример entity_id |
|---|---|---|
| `EVOLUTE_ONLINE` | Онлайн | `binary_sensor.evolute_i_pro_2022_onlajn` |
| `EVOLUTE_ODOMETER` | Одометр | `sensor.evolute_i_pro_2022_odometr` |
| `EVOLUTE_BATTERY_PCT` | Заряд батареи | `sensor.evolute_i_pro_2022_zaryad_batarei` |
| `EVOLUTE_FUEL_PCT` | Уровень топлива | `sensor.evolute_i_pro_2022_uroven_topliva` |
| `EVOLUTE_REMAINS_MILEAGE` | Запас хода (батарея) | `sensor.evolute_i_pro_2022_zapas_hoda_batareya` |
| `EVOLUTE_REMAINS_MILEAGE_FUEL` | Запас хода (топливо) | `sensor.evolute_i_pro_2022_zapas_hoda_toplivo` |
| `EVOLUTE_COOLANT_TEMP` | Температура ОЖ | `sensor.evolute_i_pro_2022_temperatura_ozh` |
| `EVOLUTE_VOLTAGE_12V` | Напряжение 12В | `sensor.evolute_i_pro_2022_napryazhenie_12v_akb` |
| `EVOLUTE_OUTSIDE_TEMP` | Температура снаружи | `sensor.evolute_i_pro_2022_temperatura_snaruzhi` |
| `EVOLUTE_INBOARD_TEMP` | Температура в салоне | `sensor.evolute_i_pro_2022_temperatura_v_salone` |
| `EVOLUTE_VIN` | VIN | `sensor.evolute_i_pro_2022_vin` |
| `EVOLUTE_CAR_MODEL` | Модель | `sensor.evolute_i_pro_2022_model` |
| `EVOLUTE_CAR_YEAR` | Год | `sensor.evolute_i_pro_2022_god_vypuska` |
| `EVOLUTE_CENTRAL_LOCK` | Замок | `lock.evolute_i_pro_2022_centralnyj_zamok` |
| `EVOLUTE_TRUNK` | Багажник | `binary_sensor.evolute_i_pro_2022_bagazhnik` |
| `EVOLUTE_TRUNK_OPEN` | Кнопка открыть багажник | `button.evolute_i_pro_2022_otkryt_bagazhnik` |
| `EVOLUTE_TRUNK_CLOSE` | Кнопка закрыть багажник | `button.evolute_i_pro_2022_zakryt_bagazhnik` |
| `EVOLUTE_BLINK` | Кнопка мигнуть фарами | `button.evolute_i_pro_2022_mignut_farami` |
| `EVOLUTE_PREPARE_ON` | Кнопка предпрогрев | `button.evolute_i_pro_2022_predprogrev_vkl` |
| `EVOLUTE_LOCATION` | Трекер GPS | `device_tracker.evolute_i_pro_2022_mestopolozhenie` |

Токены **обновляются автоматически** через refresh token при каждом успешном опросе.

Если refresh token тоже протух (бывает после долгого простоя):
1. Откройте **Настройки → Интеграции → Evolute → Настроить**
2. Вставьте свежие токены из браузера
3. Нажмите **Отправить** — перезапуск не требуется

---

## Конфигурация

Все настройки задаются через UI при добавлении интеграции:

| Параметр | Описание | По умолчанию |
|----------|----------|-------------|
| Car ID | ID автомобиля из evassist.ru | — |
| Access Token | Cookie `evy-platform-access` | — |
| Refresh Token | Cookie `evy-platform-refresh` | — |
| Интервал опроса | Как часто обновлять данные (сек) | 120 |
