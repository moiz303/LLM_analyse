# Frontend — техническая документация

> **Рабочая ветка:** `frontend` — вся разработка интерфейса ведётся в этой ветке репозитория.

Интерактивное демо для исследования влияния параметров сжатия модели на её
характеристики. Документация описывает архитектуру, контракты API и требования
к UI frontend-части проекта.

> **Важно:** все контракты API в этом документе соответствуют фактической
> реализации backend в репозитории (`backend/app`). Backend уже написан,
> протестирован и отлажен — frontend стыкуется с ним как есть, без ожиданий
> других форматов ответов. Актуальное описание API также приведено в
> `README.md`, раздел «API».

---

## 1. Назначение и границы ответственности

Пользователь должен иметь возможность:

1. увидеть базовую конфигурацию модели;
2. изменить отдельные параметры через UI;
3. отправить новую конфигурацию на backend;
4. получить prediction изменённых характеристик модели;
5. увидеть результат prediction в интерфейсе;
6. видеть Grafana Dashboard с историей/визуализацией результатов.

Границы ответственности (что frontend **не** делает):

* не выполняет вычисления модели самостоятельно;
* не работает напрямую с InfluxDB;
* не использует Grafana API;
* не хранит credentials InfluxDB/Grafana.

Вся логика расчёта влияния параметров находится на backend.

---

## 2. Архитектура

Общий поток данных:

```text
                         BLACK BOX (Kaggle)
                             |
                             | experiment data
                             v
                      +--------------+
                      |   BACKEND    |
                      |              |
                      |   Predictor  |
                      +------+-------+
                             |
                +------------+-------------+
                |                          |
                v                          v
           InfluxDB                   REST API
                |                          |
                v                          v
             Grafana                 FRONTEND
                |                          |
                | iframe                   |
                +----------->--------------+
```

Frontend взаимодействует только с:

1. Backend REST API.
2. Grafana Dashboard через iframe.

Frontend не должен знать, каким образом backend:

* хранит experiments;
* рассчитывает prediction;
* получает sensitivity;
* работает с InfluxDB;
* пишет данные в Grafana;
* получает данные от black box.

---

## 3. Стек и структура проекта

Используемый стек:

* React;
* TypeScript;
* Vite.

Для графиков frontend может использовать Plotly, ECharts или другую
согласованную charting library.

Рекомендуемая структура:

```text
frontend/
├── src/
│   ├── api/
│   │   ├── model.ts
│   │   ├── prediction.ts
│   │   └── experiments.ts
│   │
│   ├── components/
│   │   ├── ParameterPanel/
│   │   ├── MetricCards/
│   │   ├── SensitivityChart/
│   │   ├── PredictionChart/
│   │   ├── ExperimentHistory/
│   │   ├── GrafanaDashboard/
│   │   └── ...
│   │
│   ├── pages/
│   ├── types/
│   ├── App.tsx
│   └── main.tsx
│
├── .env.example
├── package.json
└── vite.config.ts
```

Конкретная структура может быть изменена, если она соответствует архитектуре проекта.

---

## 4. Окружение и подготовка

Frontend-разработчику необходимо:

```bash
git clone <repository>
cp .env.example .env        # необходимо заполнить INFLUXDB_TOKEN и при необходимости задать недефолтные пароли на Grafana и InfluxDB
docker compose up -d --build
```

Ingest actual-данных (`comparison.json -> InfluxDB`) выполняется
**автоматически** при старте backend-контейнера. Отдельно запускать
`ingest.py` не нужно (он требуется только для ручной перезагрузки файлов).

Также это описано в `README.md`, раздел «Быстрый старт», рекомендован к ознакомлению.

После этого инфраструктура доступна локально (стандартные значения из `.env.example`):

```text
InfluxDB -> http://localhost:8086
Grafana  -> http://localhost:3000
Backend  -> http://localhost:8000
Frontend -> http://localhost:5173
```

Настройка credentials и `.env` выполняется согласно README проекта.

Frontend-разработчик не должен вручную:

* устанавливать Grafana;
* создавать Grafana datasource;
* подключать InfluxDB к Grafana;
* создавать Grafana Dashboard;
* выполнять provisioning;
* создавать InfluxDB bucket.

Вся эта инфраструктура является ответственностью BE/DevOps.

---

## 5. Переменные окружения

Frontend не должен хардкодить URL backend и Grafana.

Необходимо предусмотреть:

```env
VITE_API_URL=http://localhost:8000
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Значения соответствуют стандартным портам из `.env.example` корневой папки
(`BACKEND_PORT=8000`, `GRAFANA_PORT=3000`) и README (раздел «Адреса сервисов»).
CORS на backend уже настроен под dev-адрес Vite:
`http://localhost:5173` и `http://127.0.0.1:5173`.

В Git не должны попадать:

* Grafana password;
* InfluxDB password;
* InfluxDB token;
* другие secrets.

Frontend не должен получать credentials InfluxDB или Grafana.

---

## 6. Обзор Backend API

В MVP frontend использует следующие endpoint'ы:

```http
GET  /api/model
POST /api/predict
POST /api/reset
GET  /health
```

Дополнительно, для истории экспериментов (см. раздел 10):

```http
GET  /api/experiments
```

`GET /api/experiments/{experiment_id}` и `POST /api/experiments` существуют
на backend, но frontend MVP от них не зависит.

Swagger/OpenAPI на backend намеренно отключены (`/docs` недоступен) —
ориентируйтесь на контракты из этого документа и README.

---

## 7. Контракты API

### 7.1. GET /api/model

Используется для получения конфигурации модели и текущего состояния.

**Формат ответа (фактическая реализация backend):** `parameters` и `metrics`
— это **массивы объектов**, а не словари. Имя параметра/метрики находится
в поле `name`.

Пример:

```json
{
  "model_id": "gemma_quantization_demo",
  "parameters": [
    {
      "name": "param_a",
      "baseline": 0.82,
      "ui_range": { "min": 0.7, "max": 0.9 },
      "valid_range": { "min": null, "max": null },
      "critical": true,
      "sensitivity": {
        "accuracy_top1": 0.025,
        "f1_macro": 0.022,
        "latency_ms": 0.1,
        "memory_mb": 0.08
      }
    },
    {
      "name": "param_b",
      "baseline": 0.47,
      "ui_range": { "min": 0.2, "max": 0.8 },
      "valid_range": { "min": null, "max": null },
      "critical": true,
      "sensitivity": { "accuracy_top1": 0.018, "f1_macro": 0.016 }
    },
    {
      "name": "param_c",
      "baseline": 1.15,
      "ui_range": { "min": 0.8, "max": 1.5 },
      "valid_range": { "min": null, "max": null },
      "critical": false,
      "sensitivity": { "latency": 0.08, "memory": 0.06 }
    }
  ],
  "current_configuration": {
    "param_a": 0.82,
    "param_b": 0.47,
    "param_c": 1.15
  },
  "baseline": {
    "configuration": { "param_a": 0.82, "param_b": 0.47, "param_c": 1.15 },
    "metrics": {
      "accuracy_top1": 0.7589,
      "f1_macro": 0.7498,
      "latency_ms": 12.8,
      "memory_mb": 128.0
    }
  },
  "metrics": [
    {
      "name": "accuracy_top1",
      "full": 0.7613,
      "compressed": 0.7589,
      "absolute_delta": -0.0024,
      "relative_delta": -0.00315,
      "direction": "higher_is_better",
      "kind": "quality",
      "definition": { "direction": "higher_is_better", "kind": "quality" }
    },
    {
      "name": "latency_ms",
      "full": 45.2,
      "compressed": 12.8,
      "absolute_delta": -32.4,
      "relative_delta": -0.7168,
      "direction": "lower_is_better",
      "kind": "latency",
      "definition": { "direction": "lower_is_better", "kind": "latency" }
    }
  ],
  "metadata": {
    "full_model": "gemma_full_fp16",
    "compressed_model": "gemma_nf4",
    "experiment_id": "exp_001",
    "timestamp": "2026-09-15T10:00:00+00:00"
  },
  "constraints": {
    "quality_metrics": "[0, 1]",
    "latency_metrics": ">= 0",
    "memory_metrics": ">= 0",
    "unknown_parameters": "rejected",
    "missing_parameters": "rejected"
  }
}
```

Особенности, которые frontend обязан учитывать:

* `parameters` — массив; строить UI итериацией по элементам, идентификатор — `parameter.name`.
* Диапазон slider берётся из `ui_range.min` / `ui_range.max`;
  `valid_range.min/max` могут быть `null` — это физический (более широкий)
  диапазон, не путать с UI-диапазоном.
* `metrics` — массив; направление метрики — `metric.direction`
  (`higher_is_better` / `lower_is_better`), тип — `metric.kind`
  (`quality` / `latency` / `memory` / `generic`).
* `full` / `compressed` / `absolute_delta` / `relative_delta` в элементе
  `metrics` — это сравнение **полной и сжатой модели** (фактические измерения
  baseline-эксперимента); эти значения неизменны при движении sliders.
* `current_configuration` — текущие значения параметров из буфера backend
  (`data/model.json`); именно их нужно подставить в sliders при загрузке
  страницы (буфер переживает перезагрузку страницы и обновляется на backend
  при каждом `POST /api/predict`).
* `baseline.configuration` — значения baseline (позиции «якоря») каждого параметра;
  `baseline.metrics` — эталонные compressed-метрики.
* `sensitivity` у параметра — словарь `metric_name -> число` либо объект с
  полями `lower` / `upper` / `power_lower` / `power_upper` (ключами могут быть
  имена метрик либо сокращённые kind-имена вроде `latency` / `memory`);
  используется только для ранжирования и деталей в UI. Повторных расчётов
  на frontend делать нельзя.

Frontend не должен хардкодить список параметров и метрик.

### 7.2. POST /api/predict

Request:

```json
{
  "parameters": {
    "param_a": 0.76,
    "param_b": 0.47,
    "param_c": 1.15
  }
}
```

Важно: backend валидирует запрос строго —

* тело содержит **только** поле `parameters` (неизвестные поля тела → HTTP 422);
* все параметры из `parameters` ответа `GET /api/model` должны присутствовать
  в запросе (пропущенный параметр → HTTP 422);
* неизвестное имя параметра → HTTP 422;
* значение вне `[ui_range.min, ui_range.max]` → HTTP 422.

Поэтому при каждом движении slider отправляйте **полный** объект конфигурации
(все параметры сразу), а не только изменившийся.

Response:

```json
{
  "prediction_mode": "sensitivity_model",
  "model_id": "gemma_quantization_demo",
  "prediction": {
    "accuracy_top1": 0.7464,
    "f1_macro": 0.7388,
    "latency_ms": 13.44,
    "memory_mb": 133.12
  },
  "baseline": {
    "accuracy_top1": 0.7589,
    "f1_macro": 0.7498,
    "latency_ms": 12.8,
    "memory_mb": 128.0
  },
  "configuration": {
    "param_a": 0.76,
    "param_b": 0.47,
    "param_c": 1.15
  },
  "support": {
    "score": 0.8268,
    "level": "high",
    "nearest_experiment_id": "exp_001",
    "distance": 0.1732
  },
  "metrics": [
    {
      "name": "accuracy_top1",
      "full": 0.7613,
      "compressed": 0.7589,
      "absolute_delta": -0.0024,
      "relative_delta": -0.00315,
      "direction": "higher_is_better",
      "kind": "quality",
      "definition": { "direction": "higher_is_better", "kind": "quality" }
    }
  ],
  "persisted": true
}
```

Отличия от «наивного» ожидания, которые важно учесть:

* помимо `prediction` / `baseline` / `support` приходят дополнительные поля:
  `model_id`, `configuration`, `metrics`, `persisted` — лишние поля можно
  игнорировать, но типы в `types/` лучше описать полностью;
* `configuration` в ответе — та конфигурация, для которой считался prediction
  (полезно для синхронизации sliders с последним подтверждённым состоянием);
* `support` содержит не только `score` и `level`, но и
  `nearest_experiment_id` и `distance` (могут быть использованы в UI);
* `support.nearest_experiment_id` может быть `null`;
* ключи словарей `prediction` и `baseline` совпадают с `name` элементов массива `metrics`;
* `baseline` в ответе — всегда фактические измеренные compressed-метрики,
  даже когда `prediction` пересчитан;
* `prediction_mode` в MVP всегда `"sensitivity_model"`, но завязывать логику
  UI на конкретное значение не следует.

Frontend должен отображать prediction, не выполняя повторных вычислений.

### 7.3. POST /api/reset

Тело запроса не требуется.

Поведение backend:

1. принудительно перечитывает конфигурацию из `comparison.json`
   (Source of Truth, а не из текущего буфера);
2. перезаписывает буфер `data/model.json` исходными данными;
3. выполняет prediction для baseline-конфигурации;
4. возвращает **тот же формат, что и `POST /api/predict`** (`PredictionResponse`).

Важно для frontend: `/api/reset` **не возвращает** заново `GET /api/model`.
После успешного reset frontend должен:

* установить все sliders в значения `response.configuration`
  (это baseline-конфигурация);
* обновить prediction-панель по ответу reset (для baseline предсказанные
  метрики точно равны baseline-метрикам);
* опционально выполнить повторный `GET /api/model`, если нужно обновить прочий UI.

Это гарантирует, что пользователь всегда может вернуться к проверенной точке
отсчета, даже если `data/model.json` был поврежден или изменен вручную.

### 7.4. GET /api/experiments

Ответ — **массив** объектов:

```json
[
  {
    "experiment_id": "exp_001",
    "timestamp": "2026-09-15T10:00:00Z",
    "configuration": { "param_a": 0.82, "param_b": 0.47, "param_c": 1.15 },
    "metrics": {
      "accuracy_top1": 0.7589,
      "f1_macro": 0.7498,
      "latency_ms": 12.8,
      "memory_mb": 128.0
    },
    "model_id": "gemma_quantization_demo"
  }
]
```

Особенности:

* `metrics` здесь — словарь `name -> compressed` (в отличие от массива в `GET /api/model`);
* `timestamp` приходит в ISO-формате, но у отдельных snapshots может
  отсутствовать — UI должен допускать отсутствие даты;
* список может быть пустым (пока эксперименты не загружены);
* записи упорядочены по имени файла.

### 7.5. GET /health

Используется для проверки доступности backend
(например, для индикатора статуса системы в UI).

---

## 8. Компоненты и поведение UI

### 8.1. Parameter Panel

На основании `/api/model` автоматически создать UI для каждого элемента массива `parameters`.

Для каждого параметра показать:

* название (`name`);
* slider с `min = ui_range.min`, `max = ui_range.max`;
* minimum;
* maximum;
* текущий value (из `current_configuration[name]`);
* baseline (`baseline`);
* delta относительно baseline.

Пример:

```text
Parameter A

min ─────────●──────────── max
             |
            0.76

Baseline: 0.82
Current:  0.76
Delta:   -0.06
```

Список параметров не должен быть зашит в React-коде.

### 8.2. Реактивность sliders

При изменении slider необходимо отправлять новую configuration на backend
(`POST /api/predict`, см. раздел 7.2).

Ползунки должны быть РЕАКТИВНЫМИ:

* изменение значения slider МГНОВЕННО триггерит `POST /api/predict`;
* пользователь видит изменение метрик и графиков в реальном времени при движении ползунка;
* loading state ("Calculating...") обязателен во время ожидания ответа от predict.

Debounce для реакции slider-ов:

```text
100–300 ms
```

Рекомендуется около 200 ms.

Дополнительно рекомендуется отменять/игнорировать устаревшие ответы
(AbortController или проверка последовательности запроса), чтобы при быстром
движении ползунка на экран не попал «опоздавший» ответ.

### 8.3. Metric Cards

Для основных metrics создать отдельные карточки по элементам массива `metrics`:

* Accuracy;
* F1;
* Latency;
* Memory;
* дополнительные metrics, если backend их предоставляет.

Каждая карточка должна показывать:

```text
Current prediction
Baseline
Delta
```

Например:

```text
Accuracy

Prediction
0.7464

Baseline
0.7589

Delta
-0.0125
```

(значения `prediction` и `baseline` берутся из ответа `/api/predict` по ключу `name` метрики;
delta = `prediction[name] - baseline[name]`).

Направление metric необходимо учитывать (`direction` из элемента `metrics`):

* для accuracy / f1 лучшее значение — больше (`higher_is_better`);
* для latency / memory лучшее значение — меньше (`lower_is_better`).

### 8.4. Baseline и Reset to baseline

Baseline — это исходная конфигурация модели, полученная из backend
(`baseline.configuration` и `baseline.metrics` из `GET /api/model`,
`baseline` из ответа `/api/predict`).

Инвариант:

```text
prediction(baseline) == actual compressed baseline
```

При нахождении всех sliders в baseline:

* prediction должна совпадать с baseline;
* UI должен отображать отсутствие изменения;
* Grafana должна иметь соответствующую baseline/actual точку.

В интерфейсе обязательна кнопка «Reset to baseline», вызывающая
`POST /api/reset` (контракт и поведение — см. раздел 7.3).

### 8.5. Prediction Support

Отобразить `support`, возвращаемый backend (`support.level`: `high` / `medium` / `low`).

Пример:

```text
Prediction support: HIGH
```

или:

```text
Prediction support: LOW

Current configuration is outside the region
well covered by existing experiments.
```

Не называть support статистической вероятностью правильности.

Не использовать формулировки:

```text
72% probability of being correct
```

если backend не предоставляет статистически обоснованный confidence interval.

### 8.6. Actual vs Predicted

Frontend должен явно отличать:

```text
Actual
```

от:

```text
Predicted
```

Actual — результат реального black-box experiment. На уровне API это:

* элементы массива `metrics` (`full` / `compressed` / дельты) — фактические
  измерения baseline-эксперимента;
* записи `GET /api/experiments` — фактические прогоны.

Predicted — результат surrogate model: словарь `prediction` из ответа `/api/predict`.

Prediction не должна визуально выглядеть как фактически измеренный результат.
Если frontend строит собственные prediction charts, необходимо использовать разные визуальные обозначения.

### 8.7. Experiment History

UI: список сохранённых прогонов (данные — `GET /api/experiments`, см. раздел 7.4);
клик по записи устанавливает все sliders в `configuration` эксперимента и
вызывает `POST /api/predict` для этой точки (metrics из записи отображаются
как справочные actual-значения).

---

## 9. Интеграция с Grafana

### 9.1. Границы ответственности

Grafana уже поднимается и настраивается backend/devops частью.

Frontend не должен:

* подключаться к Grafana API;
* получать данные через Grafana API;
* подключаться к InfluxDB;
* знать InfluxDB token;
* создавать datasource;
* создавать Dashboard.

Frontend получает готовый Dashboard URL.

### 9.2. Dashboard URL и компонент

Добавить в `.env.example` и не забыть про `.env`:

```env
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Этот URL актуален при стандартных настройках provisioning (указан в README, раздел «Адреса сервисов»).

Получать его в React:

```tsx
const grafanaUrl = import.meta.env.VITE_GRAFANA_DASHBOARD_URL;
```

Не хардкодить URL в компоненте.

Компонент размещается в:

```text
src/components/GrafanaDashboard/GrafanaDashboard.tsx
```

Минимальная реализация:

```tsx
export function GrafanaDashboard() {
  const url = import.meta.env.VITE_GRAFANA_DASHBOARD_URL;

  return (
    <iframe
      src={url}
      title="Grafana dashboard"
      width="100%"
      height={700}
      frameBorder="0"
    />
  );
}
```

Grafana может требовать авторизацию в самом браузере (учётные данные из `.env`:
`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`). Если iframe показывает
страницу логина Grafana — это ожидаемое поведение, frontend не должен
передавать credentials программно.

### 9.3. Роль Grafana в потоке данных

Grafana является визуальным слоем над результатами, которые записывает backend.

Backend после prediction делает:

```text
POST /api/predict
       |
       v
   Predictor
       |
       +------> response -> Frontend
       |
       +------> InfluxDB
                    |
                    v
                 Grafana
```

Frontend не должен ждать обновления Grafana для отображения prediction.
Prediction должна отображаться непосредственно из ответа `/api/predict`.

Grafana используется для:

* истории;
* сравнения;
* визуализации accumulated results;
* actual/predicted series;
* анализа поведения модели.

---

## 10. Макет страницы

В интерфейсе приложения предусмотреть отдельную секцию:

```text
+--------------------------------------------------+
| Model Compression Demo                           |
+--------------------------------------------------+
| Parameters                                       |
|                                                  |
| param_a ─────────●                               |
| param_b ──────●                                  |
| param_c ───────────●                             |
|                                                  |
| [Reset to baseline]                              |
+--------------------------------------------------+
| Predictions                                      |
|                                                  |
| Accuracy | F1 | Latency | Memory                 |
+--------------------------------------------------+
| Prediction support: HIGH                         |
+--------------------------------------------------+
| Experiment history (GET /api/experiments)        |
+--------------------------------------------------+
| Grafana                                          |
|                                                  |
| +----------------------------------------------+ |
| |                                              | |
| |              Grafana Dashboard               | |
| |                                              | |
| +----------------------------------------------+ |
+--------------------------------------------------+
```

---

## 11. Состояния загрузки и обработка ошибок

Loading states — предусмотреть:

* initial model loading;
* prediction loading;
* Grafana loading;
* API errors;
* invalid configuration;
* low prediction support.

Во время prediction желательно показывать состояние:

```text
Calculating...
```

или аналогичный индикатор загрузки.

Error handling — frontend должен корректно обрабатывать:

```text
Backend unavailable
Prediction failed
Invalid parameter
Grafana unavailable
Invalid configuration
```

Backend возвращает HTTP 422 с телом вида
`{"detail": "<текст ошибки>"}` для невалидных конфигураций
(неизвестные/отсутствующие параметры, значения вне диапазона).
Этот `detail` следует показывать пользователю как уведомление об ошибке,
сохраняя предыдущее валидное состояние UI.

Grafana failure не должен ломать prediction UI.
Prediction failure не должен ломать Grafana UI.

---

## 12. Адаптивность

Минимально поддержать:

```text
1920x1080
1366x768
```

Grafana iframe должен адаптироваться к ширине контейнера.

---

## 13. Definition of Done

Frontend MVP считается готовым, если:

* [x] приложение запускается;
* [x] frontend получает `/api/model` (парсит `parameters`/`metrics` как массивы);
* [x] параметры строятся динамически;
* [x] sliders работают;
* [x] baseline отображается;
* [x] delta отображается;
* [x] Reset to baseline работает через `POST /api/reset` и возвращает sliders в baseline;
* [ ] изменения параметров отправляются через `/api/predict` полным набором параметров;
* [x] используется debounce;
* [x] prediction отображается;
* [x] baseline отображается;
* [x] support отображается;
* [x] low support сопровождается warning;
* [x] actual/predicted явно различаются;
* [x] история экспериментов получена из `GET /api/experiments` и позволяет восстановить конфигурацию по клику;
* [x] Grafana Dashboard встроен через iframe;
* [x] Grafana URL берётся из environment;
* [x] frontend не работает напрямую с InfluxDB;
* [x] frontend не использует Grafana API;
* [x] frontend не хранит Grafana/InfluxDB credentials;
* [ ] loading/error states реализованы;
* [ ] интерфейс работает на 1920x1080 и 1366x768.