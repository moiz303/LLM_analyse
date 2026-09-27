# Backend / DevOps — техническая документация

> **Рабочая ветка:** `backend` — вся разработка серверной и инфраструктурной
> части ведётся в этой ветке репозитория.

Backend и инфраструктурная часть MVP интерактивного демо для исследования
влияния изменения параметров модели. Документация описывает архитектуру,
контракты данных, API, конвейер InfluxDB/Grafana и требования к тестированию.

---

## 1. Назначение и место в системе

Backend является связующим слоем между:

- black box compressor;
- экспериментальными данными;
- baseline model;
- параметрами и их sensitivity;
- surrogate/prediction algorithm;
- frontend;
- InfluxDB;
- Grafana.

Основная идея:

```text
Black Box (Kaggle)
    |
    | expensive experiment (~12 hours)
    v
Backend
    |
    +--> Experiment Store
    |
    +--> Baseline / Model Configuration
    |
    +--> Predictor
    |
    +--> InfluxDB
    |       |
    |       v
    |    Grafana
    |
    +--> REST API
            |
            v
         Frontend
```

---

## 2. Ключевой архитектурный принцип

Black box не должен запускаться при каждом изменении параметров пользователем.

Black box является источником реальных экспериментальных данных.

Интерактивный цикл работает следующим образом:

```text
User changes parameter
        |
        v
Frontend
        |
        | POST /api/predict
        v
Backend
        |
        v
Predictor
        |
        +------------+
        |            |
        v            v
   API response   InfluxDB
                      |
                      v
                   Grafana
```

Таким образом, дорогостоящий black-box experiment выполняется offline,
а интерактивная модель работает быстро.

---

## 3. Ответственность Backend / DevOps

Backend / DevOps отвечает за:

1. приём и валидацию experiment JSON;
2. хранение experiments;
3. формирование model configuration;
4. хранение baseline;
5. обработку critical parameters;
6. обработку sensitivity information;
7. prediction algorithm;
8. prediction API;
9. запись prediction в InfluxDB;
10. запись actual experiment data в InfluxDB;
11. разделение actual/predicted;
12. Grafana;
13. Grafana provisioning;
14. InfluxDB provisioning;
15. Docker Compose;
16. backend container;
17. CORS;
18. tests;
19. API documentation;
20. developer setup documentation.

Frontend и black box считаются отдельными контрактами.

---

## 4. Контракт входных данных от Black Box

Black box предоставляет experiment JSON
(источник — Kaggle notebook, см. `README.md`, раздел «Ссылки»:
<https://www.kaggle.com/code/flyin123/gemmaq5>).

Пример:

```json
{
  "experiment_id": "exp_001",
  "meta": {
    "full_model": "model_fp16",
    "compressed_model": "model_nf4",
    "timestamp": "2026-09-15T10:00:00Z"
  },
  "configuration": {
    "param_a": 0.82,
    "param_b": 0.47,
    "param_c": 1.15
  },
  "critical_parameters": {
    "param_a": {
      "critical": true,
      "baseline": 0.82,
      "min": 0.70,
      "max": 0.90
    }
  },
  "metrics": [
    {
      "param": "accuracy_top1",
      "full": 0.7613,
      "compressed": 0.7589
    },
    {
      "param": "f1_macro",
      "full": 0.7542,
      "compressed": 0.7498
    },
    {
      "param": "latency_ms",
      "full": 45.2,
      "compressed": 12.8
    },
    {
      "param": "memory_mb",
      "full": 512,
      "compressed": 128
    }
  ],
  "per_class": []
}
```

Backend должен валидировать этот формат (см. также `gemma_documentation.md` —
формат выходного JSON black box как единого контракта).

---

## 5. Стек и структура проекта

Используется:

* Python;
* FastAPI;
* Pydantic;
* pytest.

Рекомендуемая структура:

```text
backend/
├── app/
│   ├── api/
│   │   ├── model.py
│   │   ├── predict.py
│   │   └── health.py
│   │
│   ├── models/
│   │   ├── experiment.py
│   │   ├── model_config.py
│   │   └── prediction.py
│   │
│   ├── predictors/
│   │   ├── base.py
│   │   └── sensitivity.py
│   │
│   ├── services/
│   │   ├── experiment_store.py
│   │   ├── model_service.py
│   │   ├── prediction_service.py
│   │   └── influx_service.py
│   │
│   └── main.py
│
├── tests/
├── data/
│   ├── experiments/
│   └── model.json
│
├── Dockerfile
└── requirements.txt
```

Структура может быть изменена, если сохраняется логическое разделение ответственности.

---

## 6. Валидация experiment JSON

Создать Pydantic models для experiment JSON.

Необходимо валидировать:

* experiment_id;
* metadata;
* timestamp;
* full model;
* compressed model;
* configuration;
* critical parameters;
* metrics;
* per_class.

Проверять типы и допустимые диапазоны.

Например:

```text
accuracy ∈ [0, 1]
f1 ∈ [0, 1]
latency >= 0
memory >= 0
```

Некорректные experiment JSON не должны попадать в Experiment Store или InfluxDB.

---

## 7. Three-Tier Data Architecture

Backend четко разделяет три типа данных:

1. **Source of Truth (`comparison.json`)**:
   - Файл `comparison.json` является ИСХОДНИКОМ.
   - Содержит эталонные данные Full Model и Compressed Model.
   - Используется ТОЛЬКО для операции "Reset to baseline".
   - Никогда не перезаписывается системой автоматически.

2. **User Buffer (`model.json`)**:
   - Файл `model.json` является БУФЕРОМ ОБМЕНА.
   - При старте копирует данные из `comparison.json`.
   - Сюда сохраняются ЛЮБЫЕ изменения, внесенные пользователем через UI.
   - Именно этот файл читается `GET /api/model` для отображения текущего состояния sliders
     (в ответе это поле `current_configuration`).
   - Перезаписывается при каждом успешном `POST /api/predict` (backend сохраняет
     туда последнюю предсказанную конфигурацию). При первом обращении, если файла
     нет, он создаётся копией `comparison.json`.

3. **Experiment History (`experiments/`)**:
   - Папка `experiments/` хранит ПРОГОНЫ (snapshots).
   - Каждый файл `exp_XXX.json` — это зафиксированная конфигурация + результат prediction.
   - Используется для расчёта prediction support (близость текущей конфигурации
     к известным экспериментам) и отображения истории. Сам sensitivity-предиктор
     строится по `comparison.json` (Source of Truth), а не по snapshots.
   - Не влияет на текущее состояние sliders напрямую.

---

## 8. Baseline model и логика Reset

Baseline определяется на основании black-box experiment.

Baseline должен содержать:

```text
configuration
metrics
model metadata
```

Например:

```text
param_a = 0.82
param_b = 0.47
param_c = 1.15
```

и:

```text
accuracy = 0.7589
f1 = 0.7498
latency = 12.8
memory = 128
```

Baseline compressed metrics являются фактической точкой, относительно которой работает predictor.

### Логика операции "Reset to baseline"

Операция должна работать строго по алгоритму:

1. Прочитать `data/comparison.json` (Source of Truth).
2. Извлечь configuration и metrics compressed model.
3. Перезаписать `data/model.json` этими значениями.
4. Вернуть frontend обновленную модель.
5. Выполнить prediction для новой конфигурации (должна совпасть с baseline compressed metrics).

ВАЖНО: Reset НЕ должен обращаться к `experiments/` или последнему состоянию `model.json`.
Он всегда возвращает систему к исходному "якорю" из `comparison.json`. Также возвращает
`model.json` к состоянию `comparison.json`.

---

## 9. Model configuration

Создать отдельную конфигурацию модели.

Например:

```json
{
  "model_id": "demo_model_v1",
  "parameters": {
    "param_a": {
      "baseline": 0.82,
      "ui_min": 0.70,
      "ui_max": 0.90,
      "sensitivity": {
        "accuracy_top1": 1.0,
        "f1_macro": 0.95
      }
    }
  },
  "metrics": {
    "accuracy_top1": {
      "direction": "higher_is_better"
    },
    "f1_macro": {
      "direction": "higher_is_better"
    },
    "latency_ms": {
      "direction": "lower_is_better"
    },
    "memory_mb": {
      "direction": "lower_is_better"
    }
  }
}
```

Важно различать:

```text
valid_range
```

и:

```text
ui_range
```

UI range не должен автоматически считаться физически допустимым диапазоном.

---

## 10. Metric normalization

Внутри backend привести metrics к единой модели.

Для каждой metric хранить/рассчитывать:

```text
full
compressed
absolute_delta
relative_delta
direction
```

Например:

```json
{
  "name": "accuracy_top1",
  "full": 0.7613,
  "compressed": 0.7589,
  "absolute_delta": -0.0024,
  "relative_delta": -0.00315,
  "direction": "higher_is_better"
}
```

Для latency и memory:

```text
direction = lower_is_better
```

---

## 11. Sensitivity Predictor

Это центральная математическая задача MVP.

Необходимо реализовать predictor, который оценивает изменение metrics при
изменении параметров без повторного запуска black box.

Интерфейс:

```python
class Predictor:
    def predict(self, configuration: dict):
        ...
```

MVP implementation:

```python
class SensitivityPredictor(Predictor):
    ...
```

### Модель предиктора

Для baseline configuration:

```text
p_i^0
```

и текущей configuration:

```text
p_i
```

рассчитывается normalized deviation.

Например:

```text
x_i = (p_i - p_i^0) /
      max(p_i^0 - ui_min, ui_max - p_i^0)
```

Далее применяется penalty/sensitivity model.

Для разных сторон диапазона допускается различная чувствительность:

```text
D_i(x) =
    alpha_i^- * |x|^(k_i^-)   if x < 0

    alpha_i^+ * |x|^(k_i^+)   if x >= 0
```

Для quality metrics:

```text
D_accuracy =
    sum(w_i * D_i)
```

и:

```text
accuracy_pred =
    accuracy_compressed - D_accuracy
```

Конкретная математическая реализация может быть адаптирована под реально
доступные sensitivity данные black box.

Главное требование — модель должна быть:

* детерминированной;
* explainable;
* ограниченной физическими constraints;
* anchored в baseline.

### Baseline anchoring

Обязательное свойство predictor:

```text
predict(baseline_configuration)
    ==
compressed_actual_metrics
```

То есть:

```text
D_i(0) = 0
```

Например:

```text
Baseline:
accuracy = 0.7589

predict(baseline)
    ↓
accuracy = 0.7589
```

Это должно быть покрыто unit test.

### Раздельные модели для разных метрик

Не использовать одну математическую формулу бездумно для всех metrics.

**Quality** (accuracy, F1 и другие quality metrics) — использовать sensitivity model.

**Memory** — если доступны parameter count, quantization bits, group size,
overhead, memory желательно считать аналитически.

**Latency** — может использовать sensitivity/surrogate model. Архитектура
должна позволять впоследствии создать отдельный predictor для latency.

### Prediction constraints

Backend не должен возвращать физически невозможные значения.

Обязательные constraints:

```text
0 <= accuracy <= 1
0 <= F1 <= 1
latency >= 0
memory >= 0
```

Также необходимо валидировать:

* неизвестные parameters;
* отсутствующие parameters;
* неправильные types;
* значения вне допустимого диапазона.

### Prediction support

Backend должен оценивать, насколько текущая configuration покрыта известными
экспериментальными данными.

Для MVP допустимо использовать distance до ближайших известных experiment configurations.

Результат:

```json
{
  "score": 0.81,
  "level": "high"
}
```

Возможные levels:

```text
high
medium
low
```

`support` не является статистической вероятностью правильности prediction.

Не выдавать:

```text
72% probability of being correct
```

без соответствующей статистической модели.

Если configuration находится далеко от известных experiments, backend должен
вернуть `low` и frontend должен получить возможность показать extrapolation warning.

### Расширяемость архитектуры

MVP predictor — `SensitivityPredictor`. Но API и внутренняя архитектура должны
позволять в будущем использовать:

```text
SensitivityPredictor
InterpolationPredictor
GaussianProcessPredictor
MLSurrogatePredictor
```

Frontend не должен знать, какой predictor используется. Frontend получает:

```text
prediction_mode
```

например:

```text
sensitivity_model
interpolation
surrogate_ml
```

---

## 12. REST API

### GET /api/model

Endpoint должен возвращать frontend:

* model_id;
* список параметров;
* baseline;
* UI range;
* metric definitions;
* metric direction;
* необходимые ограничения.

Реализация: конфигурация из `comparison.json` + `current_configuration`
из `data/model.json` (User Buffer). Подробный контракт ответа описан в
`frontend_documentation.md` (раздел «Контракты API»).

Frontend не должен хардкодить эти данные.

### POST /api/predict

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

Backend выполняет:

```text
validate request
        ↓
load model
        ↓
load baseline
        ↓
run predictor
        ↓
validate prediction
        ↓
write prediction to InfluxDB
        ↓
return prediction
```

Response:

```json
{
  "prediction_mode": "sensitivity_model",
  "prediction": {
    "accuracy_top1": 0.7421,
    "f1_macro": 0.7350,
    "latency_ms": 13.2,
    "memory_mb": 124.5
  },
  "baseline": {
    "accuracy_top1": 0.7589,
    "f1_macro": 0.7498,
    "latency_ms": 12.8,
    "memory_mb": 128
  },
  "support": {
    "score": 0.81,
    "level": "high"
  }
}
```

Frontend не должен самостоятельно повторять prediction calculation.

### POST /api/reset

Читает `comparison.json` → пишет в `model.json` → возвращает baseline
в формате `PredictionResponse` (см. раздел 8, «Логика операции Reset to baseline»).

### GET /health

Минимальный response:

```json
{
  "status": "ok"
}
```

Endpoint используется для проверки доступности backend.

### Опциональные endpoints

```http
GET  /api/experiments              -> Список прогонов из data/experiments/ (для истории в UI)
GET  /api/experiments/{id}         -> Доступ к конкретному эксперименту из списка по id
POST /api/experiments              -> Создание эксперимента
```

Frontend MVP не должен зависеть от этих endpoint'ов.

### API documentation

FastAPI предоставляет OpenAPI/Swagger-описание; в текущей MVP-сборке публичный
`/docs` намеренно отключён — каноническими контрактами считаются
`frontend_documentation.md` и README, раздел «API».

---

## 13. Persistence и разделение actual/predicted

### Prediction persistence

Каждый prediction, созданный через `POST /api/predict`, должен записываться в InfluxDB.

Поток:

```text
Frontend
    |
    | POST /api/predict
    v
Backend
    |
    v
Predictor
    |
    +---------------> Frontend response
    |
    v
InfluxDB
    |
    v
Grafana
```

Это означает, что изменение slider'а пользователя становится datapoint'ом,
который затем может отображаться в Grafana.

### Actual / Predicted separation

Необходимо явно различать:

```text
actual
```

и:

```text
predicted
```

данные.

Например:

```text
result_type = actual
```

для реального black-box experiment.

И:

```text
result_type = predicted
```

для surrogate prediction.

Не смешивать prediction с actual data. Prediction не является результатом запуска black box.

### Source of truth semantics

Необходимо явно разделять:

**Actual** — фактически измерено black box:

```text
source:
black box
```

**Predicted** — рассчитано backend predictor:

```text
source:
surrogate model
```

Prediction никогда не должна выдаваться за результат реального black-box запуска.

### Prediction metadata

Каждая prediction запись должна содержать достаточно информации для последующей
визуализации и анализа.

Минимально:

```text
timestamp
model_id
result_type
prediction_mode
```

Configuration:

```text
param_a
param_b
param_c
...
```

Metrics:

```text
accuracy
f1
latency
memory
...
```

Support:

```text
support_score
support_level
```

---

## 14. Ingestion и единый experiment contract

### Actual data ingestion

Существующий сценарий:

```bash
python backend/ingest.py comparison.json
```

должен использоваться для загрузки actual experiment data в InfluxDB.

Поток:

```text
comparison.json
        |
        v
backend/ingest.py
        |
        v
InfluxDB
        |
        v
Grafana
```

`ingest.py` не должен запускаться при каждом prediction. В текущей сборке
ingest выполняется автоматически при старте backend-контейнера; ручной запуск
нужен только для перезагрузки файлов.

### Единственный experiment contract

Не создавать отдельные несовместимые форматы для:

```text
black box
backend
ingest.py
InfluxDB
```

По возможности использовать один canonical experiment JSON.

Желаемый поток:

```text
Black Box
    |
    v
Experiment JSON
    |
    +--------> Backend validation/store
    |
    +--------> ingest.py -> InfluxDB
```

Это уменьшает риск рассинхронизации схем.

---

## 15. Инфраструктура: InfluxDB, Grafana, Docker

### InfluxDB

InfluxDB используется как хранилище временных рядов для Grafana.

Основные данные:

```text
actual experiment results
predicted results
```

InfluxDB не должен быть API для frontend. Frontend не должен напрямую подключаться к InfluxDB.

### Docker Compose

Docker Compose должен поднимать:

```text
backend
influxdb
grafana
frontend
```

Сервисы по умолчанию доступны:

```text
Grafana:  http://localhost:3000
InfluxDB: http://localhost:8086
Backend:  http://localhost:<backend_port>
Frontend: http://localhost:5173
```

### Environment configuration

Используется существующий `.env.example`:

```env
# === ports ===
INFLUXDB_PORT=8086
GRAFANA_PORT=3000

# === INFLUXDB ===
INFLUXDB_USERNAME=admin
INFLUXDB_PASSWORD=admin
INFLUXDB_ORG=mlops
INFLUXDB_BUCKET=model_comparison
INFLUXDB_TOKEN=
INFLUXDB_RETENTION=365d

# === Grafana ===
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

Credentials и token должны задаваться локально и не попадать в Git.
README должен описывать, какие значения необходимо заполнить.

### InfluxDB provisioning

Настроить:

```text
Organization:
mlops

Bucket:
model_comparison

Retention:
365d
```

InfluxDB должен быть готов принимать данные после запуска Docker Compose.


> ВАЖНО!  
> Файл provisioning/datasources/influxdb.yml требует отдельной настройки:  
> Необходимо задать datasources.secureJsonData.token, совпадающий с INFLUXDB_TOKEN.


### Grafana provisioning

Использовать существующую структуру:

```text
provisioning/
├── dashboards/
│   ├── dashboard.yml
│   └── model_comparison.json
└── datasources/
    └── influxdb.yml
```

Grafana должна автоматически:

1. создать/configure datasource;
2. подключиться к InfluxDB;
3. загрузить Dashboard;
4. сохранить Dashboard при перезапуске.

Frontend не должен выполнять эти действия вручную.

### Grafana datasource

Datasource должен указывать на InfluxDB через Docker network.

Например:

```text
http://influxdb:8086
```

Не использовать внутри Grafana:

```text
http://localhost:8086
```

поскольку `localhost` внутри Grafana container указывает на сам Grafana container.

Datasource должен быть настроен через provisioning.

### Grafana Dashboard

Dashboard должен отображать данные, записанные backend.

Минимально необходимо предусмотреть:

* **Actual** — результаты реальных black-box experiments;
* **Predicted** — результаты surrogate predictions;
* **Baseline** — исходную точку;
* **History** — историю изменений configuration/prediction;
* **Metrics** — минимально: accuracy, F1, latency, memory.

Grafana должна визуально различать Actual и Predicted, например:

```text
Accuracy

actual:
●──────●──────●

predicted:
○────○────○────○
```

Конкретный дизайн dashboard определяется BE/DevOps, но semantics должны быть сохранены.

### Grafana embedding

Grafana Dashboard должен быть доступен frontend через iframe.

Необходимо разрешить embedding согласно используемой версии Grafana.

Например, для соответствующей конфигурации:

```ini
[security]
allow_embedding = true
```

После этого Dashboard должен открываться через URL вида:

```text
http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Конкретный URL должен быть указан в README и передан frontend через:

```env
VITE_GRAFANA_DASHBOARD_URL=...
```

### Backend Dockerization

Backend должен иметь Dockerfile. Docker Compose должен позволять запустить
backend вместе с InfluxDB и Grafana. Backend должен получать конфигурацию через
environment variables. Secrets не должны быть hardcoded в Python code.

### Docker networking

Backend, InfluxDB и Grafana должны находиться в одной Docker network.
Внутри Docker network использовать service names.

Например:

```text
backend -> http://influxdb:8086
grafana -> http://influxdb:8086
```

Frontend, запущенный отдельно через Vite, использует host-facing URL:

```text
http://localhost:<backend_port>
http://localhost:3000
```

### CORS

Backend должен разрешать frontend origin для локальной разработки.

Например:

```text
http://localhost:5173
```

CORS не должен без необходимости разрешать любой origin.

---

## 16. Тестирование

### Unit tests

Необходимо покрыть:

**Experiment validation**

```text
valid experiment -> accepted
invalid experiment -> rejected
missing required field -> rejected
invalid metric -> rejected
```

**Predictor**

```text
baseline -> baseline result
parameter change -> expected metric change
multiple parameter changes -> combined result
```

**Constraints**

```text
accuracy >= 0
accuracy <= 1
f1 >= 0
f1 <= 1
latency >= 0
memory >= 0
```

**API**

```text
GET /api/model -> 200
POST /api/predict -> 200
invalid request -> 4xx
GET /health -> 200
```

**Persistence**

```text
POST /api/predict
    |
    +-> prediction calculated
    |
    +-> prediction written to InfluxDB
```

### Integration tests

Необходимо проверить полный pipeline.

**Actual pipeline**

```text
experiment JSON
        |
        v
validation
        |
        v
Experiment Store
        |
        v
InfluxDB
        |
        v
Grafana
```

**Interactive pipeline**

```text
POST /api/predict
        |
        v
Predictor
        |
        +----> HTTP response
        |
        v
InfluxDB
        |
        v
Grafana
```

Основной критерий: после вызова `/api/predict` prediction должна:

1. быть рассчитана;
2. вернуться frontend;
3. попасть в InfluxDB;
4. стать доступной Grafana.

---

## 17. Developer setup (README)

README должен описывать полный локальный сценарий.

Минимально:

```bash
git clone <repository>

# configure .env

docker-compose up -d --build
```

После запуска:

```text
InfluxDB:
http://localhost:8086

Grafana:
http://localhost:3000

Backend:
http://localhost:<backend_port>
```

README должен содержать:

* описание `.env`;
* необходимые credentials;
* запуск Docker Compose;
* запуск ingest.py;
* Grafana URL;
* Backend URL;
* Swagger URL;
* описание основных API;
* описание архитектуры;
* описание actual/predicted semantics.

---

## 18. Целевой сценарий работы MVP

### Initial setup

```text
docker-compose up -d
```

Запускаются:

```text
Backend
InfluxDB
Grafana
Frontend
```

Затем (ПРИ НЕОБХОДИМОСТИ ОБНОВЛЕНИЯ ДАННЫХ, при первом запуске не требуется):

```text
python ingest.py comparison.json
```

Actual experiment data попадает в InfluxDB. Grafana показывает full и compressed data.

### Interactive flow

Пользователь открывает frontend.

Frontend получает `GET /api/model` и строит sliders.

Пользователь меняет:

```text
param_a:
0.82 -> 0.76
```

Frontend отправляет `POST /api/predict`.

Backend:

```text
validate configuration
        |
        v
calculate prediction
        |
        +--------------------+
        |                    |
        v                    v
HTTP response           InfluxDB
                             |
                             v
                          Grafana
```

Frontend получает prediction и показывает её непосредственно.
Grafana получает тот же prediction через InfluxDB и отображает его в dashboard.

---

## 19. Definition of Done

Backend/DevOps MVP считается готовым, если:

* [x] Backend запускается в Docker;
* [x] InfluxDB запускается в Docker;
* [x] Grafana запускается в Docker;
* [x] Docker networking настроен;
* [x] `.env` используется для configuration;
* [x] credentials не hardcoded;
* [x] experiment JSON валидируется;
* [ ] experiments сохраняются;
* [x] несколько experiments поддерживаются;
* [x] baseline configuration доступна;
* [x] baseline metrics доступны;
* [x] critical parameters доступны;
* [ ] model configuration сформирована;
* [x] `/api/model` работает;
* [x] sensitivity predictor работает;
* [x] baseline prediction совпадает с actual compressed result;
* [x] predictions физически валидны;
* [ ] prediction support рассчитывается;
* [x] `/api/predict` работает;
* [ ] prediction записывается в InfluxDB;
* [x] actual data записывается в InfluxDB;
* [x] actual/predicted разделены;
* [ ] Grafana datasource provisioned;
* [ ] Grafana Dashboard provisioned;
* [x] Grafana показывает full model;
* [x] Grafana показывает compressed (baseline) model;
* [x] Grafana показывает историю;
* [x] Grafana доступна на localhost:3000;
* [x] Grafana Dashboard можно встроить через iframe;
* [x] CORS настроен;
* [x] `/health` работает;
* [x] unit tests проходят;
* [x] integration test проходит;
* [x] README содержит полный setup.
