# Backend / DevOps MVP — Interactive Model Compression Demo

## 1. Цель

Необходимо реализовать backend и инфраструктурную часть MVP интерактивного демо для исследования влияния изменения параметров модели.

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
Black Box
    |
    | expensive experiment
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
````

---

# 2. Ключевой архитектурный принцип

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

Таким образом, дорогостоящий black-box experiment выполняется offline, а интерактивная модель работает быстро.

---

# 3. Ответственность Backend / DevOps

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

# 4. Input от Black Box

Black box предоставляет experiment JSON.

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

Backend должен валидировать этот формат.

---

# 5. BE-001 — Backend skeleton

Использовать:

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

# 6. BE-002 — Experiment JSON validation

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

# 7. BE-003 — Experiment Store

Для MVP хранить experiments локально:

```text
data/
└── experiments/
    ├── exp_001.json
    ├── exp_002.json
    └── ...
```

Experiment Store должен поддерживать несколько experiments.

Это необходимо не только для истории, но и для будущего развития surrogate model.

Текущий predictor может использовать один baseline experiment, однако архитектура не должна предполагать, что experiment всегда будет только один.

---

# 8. BE-004 — Baseline model

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

---

# 9. BE-005 — Model configuration

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

# 10. BE-006 — Model API

Реализовать:

```http
GET /api/model
```

Endpoint должен возвращать frontend:

* model_id;
* список параметров;
* baseline;
* UI range;
* metric definitions;
* metric direction;
* необходимые ограничения.

Frontend не должен хардкодить эти данные.

---

# 11. BE-007 — Metric normalization

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

# 12. BE-008 — Sensitivity Predictor

Это центральная математическая задача MVP.

Необходимо реализовать predictor, который оценивает изменение metrics при изменении параметров без повторного запуска black box.

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

---

# 13. Predictor model

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

Конкретная математическая реализация может быть адаптирована под реально доступные sensitivity данные black box.

Главное требование — модель должна быть:

* детерминированной;
* explainable;
* ограниченной физическими constraints;
* anchored в baseline.

---

# 14. BE-009 — Baseline anchoring

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

---

# 15. BE-010 — Different models for different metrics

Не использовать одну математическую формулу бездумно для всех metrics.

### Quality

Для:

* accuracy;
* F1;
* других quality metrics.

Использовать sensitivity model.

### Memory

Если доступны:

* parameter count;
* quantization bits;
* group size;
* overhead;

memory желательно считать аналитически.

### Latency

Latency может использовать sensitivity/surrogate model.

Архитектура должна позволять впоследствии создать отдельный predictor для latency.

---

# 16. BE-011 — Prediction constraints

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

---

# 17. BE-012 — Prediction support

Backend должен оценивать, насколько текущая configuration покрыта известными экспериментальными данными.

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

Если configuration находится далеко от известных experiments, backend должен вернуть `low` и frontend должен получить возможность показать extrapolation warning.

---

# 18. BE-013 — Prediction API

Основной endpoint:

```http
POST /api/predict
```

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

---

# 19. BE-014 — Prediction persistence

Каждый prediction, созданный через:

```http
POST /api/predict
```

должен записываться в InfluxDB.

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

Это означает, что изменение slider'а пользователя становится datapoint'ом, который затем может отображаться в Grafana.

---

# 20. BE-015 — Actual / Predicted separation

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

Не смешивать prediction с actual data.

Prediction не является результатом запуска black box.

---

# 21. BE-016 — Prediction metadata

Каждая prediction запись должна содержать достаточно информации для последующей визуализации и анализа.

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

# 22. BE-017 — Actual data ingestion

Существующий сценарий:

```bash
python ingest.py comparison.json
```

должен использоваться для загрузки actual experiment data в InfluxDB.

Поток:

```text
comparison.json
        |
        v
ingest.py
        |
        v
InfluxDB
        |
        v
Grafana
```

`ingest.py` не должен запускаться при каждом prediction.

---

# 23. BE-018 — Единственный experiment contract

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

# 24. BE-019 — InfluxDB

InfluxDB используется как хранилище временных рядов для Grafana.

Основные данные:

```text
actual experiment results
predicted results
```

InfluxDB не должен быть API для frontend.

Frontend не должен напрямую подключаться к InfluxDB.

---

# 25. BE-020 — Grafana infrastructure

Docker Compose должен поднимать:

```text
backend
influxdb
grafana
```

Grafana должна быть доступна:

```text
http://localhost:3000
```

InfluxDB:

```text
http://localhost:8086
```

Backend должен быть доступен по URL, указанному в README.

---

# 26. BE-021 — Environment configuration

Использовать существующий `.env.example`:

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

---

# 27. BE-022 — InfluxDB provisioning

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

---

# 28. BE-023 — Grafana provisioning

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

---

# 29. BE-024 — Grafana datasource

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

---

# 30. BE-025 — Grafana Dashboard

Dashboard должен отображать данные, записанные backend.

Минимально необходимо предусмотреть:

### Actual

Результаты реальных black-box experiments.

### Predicted

Результаты surrogate predictions.

### Baseline

Исходную точку.

### History

Историю изменений configuration/prediction.

### Metrics

Минимально:

* accuracy;
* F1;
* latency;
* memory.

---

# 31. BE-026 — Actual vs Predicted visualization

Grafana должна визуально различать:

```text
Actual
```

и:

```text
Predicted
```

Например:

```text
Accuracy

actual:
●──────●──────●

predicted:
○────○────○────○
```

Конкретный дизайн dashboard определяется BE/DevOps, но semantics должны быть сохранены.

---

# 32. BE-027 — Grafana embedding

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

---

# 33. BE-028 — Backend Dockerization

Backend должен иметь Dockerfile.

Docker Compose должен позволять запустить backend вместе с:

```text
InfluxDB
Grafana
```

Backend должен получать конфигурацию через environment variables.

Secrets не должны быть hardcoded в Python code.

---

# 34. BE-029 — Docker networking

Backend, InfluxDB и Grafana должны находиться в одной Docker network.

Внутри Docker network использовать service names.

Например:

```text
backend -> http://influxdb:8086
grafana -> http://influxdb:8086
```

Frontend, запущенный отдельно через Vite, использует host-facing URL:

```text
http://localhost:<backend-port>
http://localhost:3000
```

---

# 35. BE-030 — CORS

Backend должен разрешать frontend origin для локальной разработки.

Например:

```text
http://localhost:5173
```

CORS не должен без необходимости разрешать любой origin.

---

# 36. BE-031 — Health endpoint

Реализовать:

```http
GET /health
```

Минимальный response:

```json
{
  "status": "ok"
}
```

Endpoint используется для проверки доступности backend.

---

# 37. BE-032 — API documentation

FastAPI должен предоставлять OpenAPI/Swagger.

Минимальные endpoint'ы:

```http
GET  /api/model
POST /api/predict
GET  /health
```

Опционально:

```http
GET /api/experiments
GET /api/experiments/{experiment_id}
```

Но frontend MVP не должен зависеть от этих endpoint'ов.

---

# 38. BE-033 — Unit tests

Необходимо покрыть:

## Experiment validation

```text
valid experiment -> accepted
invalid experiment -> rejected
missing required field -> rejected
invalid metric -> rejected
```

## Predictor

```text
baseline -> baseline result
parameter change -> expected metric change
multiple parameter changes -> combined result
```

## Constraints

```text
accuracy >= 0
accuracy <= 1
f1 >= 0
f1 <= 1
latency >= 0
memory >= 0
```

## API

```text
GET /api/model -> 200
POST /api/predict -> 200
invalid request -> 4xx
GET /health -> 200
```

## Persistence

```text
POST /api/predict
    |
    +-> prediction calculated
    |
    +-> prediction written to InfluxDB
```

---

# 39. BE-034 — Integration test

Необходимо проверить полный pipeline.

## Actual pipeline

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

## Interactive pipeline

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

Основной критерий:

После вызова `/api/predict` prediction должна:

1. быть рассчитана;
2. вернуться frontend;
3. попасть в InfluxDB;
4. стать доступной Grafana.

---

# 40. BE-035 — README / Developer setup

README должен описывать полный локальный сценарий.

Минимально:

```bash
git clone <repository>

# configure .env

docker-compose up -d

python ingest.py comparison.json
```

После запуска:

```text
InfluxDB:
http://localhost:8086

Grafana:
http://localhost:3000

Backend:
http://localhost:<backend-port>

Swagger:
http://localhost:<backend-port>/docs
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

# 41. BE-036 — Final MVP flow

Полностью рабочая система должна поддерживать следующий сценарий.

## Initial setup

```text
docker-compose up -d
```

Запускаются:

```text
Backend
InfluxDB
Grafana
```

Затем:

```text
python ingest.py comparison.json
```

Actual experiment data попадает в InfluxDB.

Grafana показывает baseline/actual data.

---

## Interactive flow

Пользователь открывает frontend.

Frontend получает:

```http
GET /api/model
```

и строит sliders.

Пользователь меняет:

```text
param_a:
0.82 -> 0.76
```

Frontend отправляет:

```http
POST /api/predict
```

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

# 42. BE-037 — Source of truth

Необходимо явно разделять:

### Actual

Фактически измерено black box.

```text
source:
black box
```

### Predicted

Рассчитано backend predictor.

```text
source:
surrogate model
```

Prediction никогда не должна выдаваться за результат реального black-box запуска.

---

# 43. BE-038 — Architecture extensibility

MVP predictor — `SensitivityPredictor`.

Но API и внутренняя архитектура должны позволять в будущем использовать:

```text
SensitivityPredictor
InterpolationPredictor
GaussianProcessPredictor
MLSurrogatePredictor
```

Frontend не должен знать, какой predictor используется.

Frontend получает:

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

# 44. BE-039 — MVP Definition of Done

Backend/DevOps MVP считается готовым, если:

* [ ] Backend запускается в Docker;
* [ ] InfluxDB запускается в Docker;
* [ ] Grafana запускается в Docker;
* [ ] Docker networking настроен;
* [ ] `.env` используется для configuration;
* [ ] credentials не hardcoded;
* [ ] experiment JSON валидируется;
* [ ] experiments сохраняются;
* [ ] несколько experiments поддерживаются;
* [ ] baseline configuration доступна;
* [ ] baseline metrics доступны;
* [ ] critical parameters доступны;
* [ ] model configuration сформирована;
* [ ] `/api/model` работает;
* [ ] sensitivity predictor работает;
* [ ] baseline prediction совпадает с actual compressed result;
* [ ] predictions физически валидны;
* [ ] prediction support рассчитывается;
* [ ] `/api/predict` работает;
* [ ] prediction записывается в InfluxDB;
* [ ] actual data записывается в InfluxDB;
* [ ] actual/predicted разделены;
* [ ] Grafana datasource provisioned;
* [ ] Grafana Dashboard provisioned;
* [ ] Grafana показывает actual;
* [ ] Grafana показывает predicted;
* [ ] Grafana показывает baseline;
* [ ] Grafana показывает историю;
* [ ] Grafana доступна на localhost:3000;
* [ ] Grafana Dashboard можно встроить через iframe;
* [ ] `ingest.py comparison.json` работает;
* [ ] CORS настроен;
* [ ] `/health` работает;
* [ ] Swagger/OpenAPI доступен;
* [ ] unit tests проходят;
* [ ] integration test проходит;
* [ ] README содержит полный setup.
