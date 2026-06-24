# Evolute для Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Нативная интеграция автомобилей **Evolute** (evassist.ru) для Home Assistant.  
Работает **без аддонов и прокси** — напрямую обращается к `app.evassist.ru`.

> 💡 Для дашборда есть отдельная карточка **[Evolute Card](https://github.com/Tamahome-M/evolute-card)** — см. раздел [«Карточка для дашборда»](#карточка-для-дашборда).

---

## Возможности

| Тип | Объекты |
|-----|---------|
| 🔢 Сенсоры | Заряд батареи, запас хода (батарея + топливо), одометр, все температуры (улица / салон / батарея / ОЖ), напряжение 12В АКБ, обороты, климат (скорость вентилятора, цель / текущая t°), скорость GPS, высота, курс, спутники, VIN, модель, год, цвет |
| 🔴 Бинарные сенсоры | Зажигание, онлайн, все 4 двери, багажник, замок, климат, обогрев лобового стекла, фары, предпрогрев (запущен / доступен), припаркован |
| 🔒 Замок | Центральный замок (lock/unlock из HA) |
| 🔘 Кнопки | Обогрев вкл/выкл, охлаждение вкл/выкл, предпрогрев вкл/выкл, открыть/закрыть багажник, сигнал и фары (поиск) |
| 🎚️ Числа | Параметры предпрогрева: целевая температура, длительность, подогрев 4 сидений и руля |
| 📍 Трекер | GPS-позиция автомобиля на карте HA |

---

## Установка через HACS

[![Open your Home Assistant instance and open the Evolute repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tamahome-M&repository=evolute-ha&category=integration)

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

## Карточка для дашборда

Для красивой панели управления автомобилем есть отдельная карточка —
**[Evolute Card](https://github.com/Tamahome-M/evolute-card)**. Она ставится
отдельно через HACS (тип **Dashboard**) и сама находит ваш автомобиль —
ничего настраивать руками не нужно:

```yaml
type: custom:evolute-card
show_map: true
```

[![Open your Home Assistant instance and open the Evolute Card repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Tamahome-M&repository=evolute-card&category=dashboard)

Подробности и параметры — в [README карточки](https://github.com/Tamahome-M/evolute-card).

---

## Конфигурация

Все настройки задаются через UI при добавлении интеграции:

| Параметр | Описание | По умолчанию |
|----------|----------|-------------|
| Car ID | ID автомобиля из evassist.ru | — |
| Access Token | Cookie `evy-platform-access` | — |
| Refresh Token | Cookie `evy-platform-refresh` | — |
| Интервал опроса | Как часто обновлять данные (сек) | 120 |
