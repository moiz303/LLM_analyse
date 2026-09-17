# Интерактивное сравнение сжатия модели

![Python](https://img.shields.io/badge/Python-3.11%2B-green)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![Grafana](https://img.shields.io/badge/Grafana-11-orange)
![InfluxDB](https://img.shields.io/badge/InfluxDB-2.7-red)
![Docker](https://img.shields.io/badge/Docker-blue)

---

## О проекте

Проект предназначен для интерактивного сравнения полной ML-модели и её
сжатой версии. Результат исходного чёрного ящика хранится в
`comparison.json`, записывается в InfluxDB и отображается в Grafana.

Тяжёлый эксперимент выполняется отдельно. Backend использует его результат
как baseline, а изменения параметров, выбранные на frontend, обрабатывает
через детерминированный sensitivity-predictor.

Backend предоставляет:

- валидацию конфигурации и экспериментальных данных;
- публичную конфигурацию модели для построения slider-интерфейса;
- быстрые предсказания изменения метрик;
- сохранение истории экспериментов;
- раздельную запись actual и predicted данных в InfluxDB;
- готовый dashboard Grafana для сравнения полной, сжатой, предсказанной и
  исторической информации.

---

## Архитектура

```text
┌────────────────────────────┐
│ comparison.json            │
│ исходный результат         │
│ прогона в Kaggle           │
└─────────────┬──────────────┘
              │
              ├── автоматический ingest при запуске
              │
              ▼
┌────────────────────────────┐
│ FastAPI backend            │
│ валидация и predictor      │
└───────┬──────────────┬─────┘
        │              │
        │              ├── data/model.json
        │              │   текущий buffer пользователя
        │              │
        │              └── data/experiments/*.json
        │                  история экспериментов
        │
        ▼
┌────────────────────────────┐
│ InfluxDB 2.7               │
│ actual и predicted points  │
└─────────────┬──────────────┘
              │ Flux
              ▼
┌────────────────────────────┐
│ Grafana 11                 │
│ datasource и dashboard     │
└────────────────────────────┘
```

Структура запроса от Frontend:

```text
Frontend ── POST /api/predict ──> FastAPI ──> InfluxDB
```

### Уровни данных

Проект намеренно разделяет три уровня хранения:

- `comparison.json` — неизменяемый источник истины для baseline и Reset;
- `data/model.json` — текущий buffer параметров пользователя;
- `data/experiments/` — проверенные snapshots экспериментов и история.

При загрузке исходных данных используется fallback-цепочка:

```text
comparison.json
    ↓ если отсутствует
data/model.json
    ↓ если отсутствует
последний файл из data/experiments/*.json
```

`comparison.json` существует всегда, он всегда имеет наивысший приоритет.

---

## Стек

- **Python 3.11** — backend и ingestion pipeline;
- **FastAPI** — HTTP API;
- **Pydantic** — валидация входных данных и конфигурации;
- **InfluxDB 2.7** — хранение временных рядов;
- **Grafana 11** — визуализация и dashboard;
- **Docker / Docker Compose** — запуск всего локального стека;
- **pytest** — автоматические тесты backend.

---

## Быстрый старт

### Требования

- Docker с Docker Compose;
- доступный Docker daemon;
- файл `comparison.json` в корне проекта.

Python на хост-системе для обычного запуска не требуется: backend и ingest
работают внутри Docker-контейнера.

### Шаги

1. Создайте локальный файл окружения:

   ```bash
   cp .env.example .env
   ```

2. Заполните `.env`.

   Минимально необходимо задать:

   ```env
   INFLUXDB_PASSWORD=admin
   INFLUXDB_TOKEN=<ваш-токен>
   GRAFANA_ADMIN_PASSWORD=admin
   ```

   Полный список переменных приведён ниже в разделе
   [Переменные окружения](#переменные-окружения).

   Токен не нужно вручную копировать в
   `provisioning/datasources/influxdb.yml`: provisioning использует значение
   `${INFLUXDB_TOKEN}` из окружения (отличие о предыдущей версии). Файл `.env` нельзя добавлять в Git.

3. Убедитесь, что `comparison.json` находится в корне проекта. Это
   канонический baseline текущего demo. Для другого эксперимента замените
   файл валидным JSON того же формата.

4. Запустите весь стек:

   ```bash
   docker compose up -d --build
   ```

   После того как InfluxDB станет healthy, backend автоматически:

   1. прочитает и провалидирует `comparison.json`;
   2. сохранит snapshot в `data/experiments/`;
   3. запишет actual-результаты в InfluxDB;
   4. запустит FastAPI.

   Отдельно выполнять `python backend/ingest.py comparison.json` не нужно, эта команда встроена в запуск backend-контейнера (отличие от предыдущей версии).

5. Проверьте статус контейнеров и автоматической загрузки:

   ```bash
   docker compose ps
   docker compose logs backend
   ```

   В логах backend должна появиться строка вида:

   ```text
   Validated and ingested exp_xxx (...)
   ```

### Адреса сервисов

При стандартных значениях из `.env.example`:

- Backend: <http://localhost:8000>
- Health check: <http://localhost:8000/health>
- InfluxDB: <http://localhost:8086>
- Grafana: <http://localhost:3000>
- Dashboard: <http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk>

Frontend может использовать:

```env
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Логин Grafana берётся из `GRAFANA_ADMIN_USER` и
`GRAFANA_ADMIN_PASSWORD`.

### Последующие запуски

Если образы и конфигурация уже собраны:

```bash
docker compose up -d
```

При изменении Dockerfile или Python-кода:

```bash
docker compose up -d --build
```

---

## Структура проекта

```text
.
├── .env.example                         # шаблон переменных окружения
├── .gitignore
├── Dockerfile                           # образ FastAPI backend
├── docker-compose.yml                   # backend + InfluxDB + Grafana
├── comparison.json                      # канонический baseline
├── backend/
│   ├── app/
│   │   ├── api/                         # HTTP-маршруты
│   │   ├── models/                      # Pydantic-контракты
│   │   ├── predictors/                  # predictor и sensitivity-модель
│   │   └── services/                    # storage, prediction, InfluxDB
│   ├── ingest.py                        # валидация и actual ingest
│   ├── requirements.txt
│   └── tests/
├── data/
│   ├── model.json                       # локальный buffer пользователя
│   └── experiments/                     # snapshots экспериментов
└── provisioning/
    ├── datasources/
    │   └── influxdb.yml                 # datasource Grafana
    └── dashboards/
        ├── dashboard.yml                # provider dashboard
        └── model_comparison.json        # dashboard Grafana
```

`data/model.json` и содержимое `data/experiments/` являются runtime-данными и
не должны использоваться как замена `comparison.json`.

---

## Формат `comparison.json`

Файл должен содержать metadata эксперимента, конфигурацию параметров и хотя
бы одну метрику. Пример:

```json
{
  "experiment_id": "exp_001",
  "meta": {
    "full_model": "gemma_full_fp16",
    "compressed_model": "gemma_nf4",
    "timestamp": "2026-09-15T10:00:00Z",
    "model_id": "gemma_quantization_demo"
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
      "min": 0.7,
      "max": 0.9,
      "sensitivity": {
        "accuracy_top1": 0.025,
        "f1_macro": 0.022
      }
    }
  },
  "metrics": [
    {
      "param": "accuracy_top1",
      "full": 0.7613,
      "compressed": 0.7589
    },
    {
      "param": "latency_ms",
      "full": 45.2,
      "compressed": 12.8
    }
  ],
  "per_class": []
}
```

### Основные поля

| Поле | Тип | Назначение |
|---|---|---|
| `experiment_id` | string | Уникальный идентификатор эксперимента |
| `meta.full_model` | string | Имя полной модели |
| `meta.compressed_model` | string | Имя сжатой модели |
| `meta.timestamp` | ISO 8601 | Время actual-точек в InfluxDB |
| `meta.model_id` | string | Идентификатор модели для API и dashboard |
| `configuration` | object | Значения параметров в baseline |
| `critical_parameters` | object | Диапазоны и sensitivity параметров |
| `metrics` | array | Значения полной и сжатой модели |
| `per_class` | array | Необязательные метрики по классам |

Каждый объект в `metrics` содержит:

| Поле | Тип | Назначение |
|---|---|---|
| `param` | string | Название метрики |
| `full` | number | Значение полной модели |
| `compressed` | number | Значение сжатой модели |

Валидация дополнительно проверяет:

- наличие хотя бы одной метрики;
- конечность числовых значений;
- диапазон quality-метрик от `0` до `1`;
- неотрицательность latency и memory;
- непустые имена параметров и моделей;
- корректность timestamp.

`timestamp` должен быть валидным временем ISO 8601, не должен быть временем из
будущего и должен попадать в retention-период InfluxDB.

---

## API

### `GET /health`

Проверка доступности backend:

```json
{
  "status": "ok"
}
```

### `GET /api/model`

Возвращает конфигурацию модели для frontend:

- `model_id`;
- параметры и их baseline;
- UI-диапазоны и физически допустимые диапазоны;
- критичность параметров;
- sensitivity;
- список метрик;
- направление оптимизации;
- baseline полной и сжатой модели.

Frontend не должен дублировать эти значения в собственном коде.

### `POST /api/predict`

Запрашивает prediction для новой конфигурации параметров:

```json
{
  "parameters": {
    "param_a": 0.76,
    "param_b": 0.47,
    "param_c": 1.15
  }
}
```

Backend:

1. проверяет конфигурацию;
2. рассчитывает метрики через sensitivity-predictor;
3. ограничивает prediction физически допустимыми значениями;
4. вычисляет support относительно ближайшего известного эксперимента;
5. обновляет `data/model.json`;
6. пишет predicted-точки в InfluxDB.

`support` показывает степень экстраполяции и не является вероятностью
правильности prediction.

### `POST /api/reset`

Восстанавливает `data/model.json` из исходного `comparison.json` и возвращает
prediction исходной конфигурации. Для baseline compressed-метрики возвращаются
точные измеренные значения.

### `GET /api/experiments`

Возвращает список сохранённых snapshots экспериментов.

### `GET /api/experiments/{experiment_id}`

Возвращает полный snapshot эксперимента.

### `POST /api/experiments`

Проверяет и сохраняет новый canonical experiment, а затем записывает его
actual-метрики в InfluxDB.

Документация Swagger/OpenAPI намеренно отключена. Backend предоставляет только
маршруты, необходимые приложению.

---

## InfluxDB и Grafana

### Actual и predicted данные

Результаты исходного black-box эксперимента записываются как:

```text
result_type=actual
prediction_mode=black_box
```

Интерактивные запросы `/api/predict` записываются как:

```text
result_type=predicted
prediction_mode=sensitivity_model
```

Данные не смешиваются: dashboard может отдельно показывать измеренные,
предсказанные и baseline-значения.

### Measurements

Backend использует два measurement:

| Measurement | Назначение |
|---|---|
| `metric_results` | Детальные значения по каждой метрике |
| `model_results` | Сводные результаты, support и параметры конфигурации |

Типовые теги:

- `model_id`;
- `experiment_id`;
- `result_type`;
- `prediction_mode`;
- `metric`;
- `support_level` для prediction.

Grafana и backend подключаются к InfluxDB по внутреннему адресу
`INFLUXDB_URL`, например `http://influxdb:8086`. Браузер использует
host-facing порты из `.env`.

---

## Переменные окружения

Все переменные задаются в `.env`. Шаблон находится в `.env.example`.

### Порты и внутренние адреса

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `BACKEND_PORT` | Порт backend на хосте | `8000` |
| `INFLUXDB_PORT` | Порт InfluxDB на хосте | `8086` |
| `GRAFANA_PORT` | Порт Grafana на хосте | `3000` |
| `BACKEND_HOST` | Адрес прослушивания backend в контейнере | `0.0.0.0` |
| `BACKEND_CONTAINER_PORT` | Порт backend внутри контейнера | `8000` |
| `INFLUXDB_URL` | Внутренний URL InfluxDB | `http://influxdb:8086` |
| `INFLUXDB_CONTAINER_PORT` | Порт InfluxDB внутри сети Docker | `8086` |
| `GRAFANA_CONTAINER_PORT` | Порт Grafana внутри контейнера | `3000` |

### Backend

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `DATA_DIR` | Каталог runtime-данных | `data` |
| `COMPARISON_PATH` | Путь к source-of-truth | `comparison.json` |
| `FRONTEND_ORIGINS` | Разрешённые frontend origins | localhost:5173 |

### InfluxDB

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `INFLUXDB_USERNAME` | Администратор InfluxDB | `admin` |
| `INFLUXDB_PASSWORD` | Пароль администратора | `admin` |
| `INFLUXDB_ORG` | Организация | `mlops` |
| `INFLUXDB_BUCKET` | Bucket | `model_comparison` |
| `INFLUXDB_TOKEN` | Токен доступа | задаётся локально |
| `INFLUXDB_RETENTION` | Retention policy | `365d` |
| `INFLUXDB_REQUIRED` | Требовать InfluxDB для API-запросов | `false` |

### Grafana

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `GRAFANA_ADMIN_USER` | Логин администратора | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Пароль администратора | `admin` |

Значения с паролями и токенами нельзя коммитить в репозиторий.

---

## Для разработчиков

### Запуск тестов

```bash
pytest -q backend/tests
```

Тесты проверяют:

- валидацию экспериментов;
- обработку отсутствующих и некорректных полей;
- baseline anchoring;
- sensitivity-изменения;
- физические ограничения;
- ошибки API;
- reset;
- сохранение данных через application service boundary.

### Ручной ingest

Обычный запуск выполняет ingest автоматически. Для ручной загрузки файла в
уже работающий контейнер:

```bash
docker compose exec backend \
  python backend/ingest.py comparison.json
```

Скрипт также поддерживает переопределение параметров подключения:

```bash
docker compose exec backend \
  python /app/backend/ingest.py /app/comparison.json \
  --url http://influxdb:8086 \
  --org mlops \
  --bucket model_comparison \
  --token '<токен>'
```

### Изменение dashboard

Канонический файл dashboard:

```text
provisioning/dashboards/model_comparison.json
```

После изменения JSON перезапустите Grafana:

```bash
docker compose restart grafana
```

Если Grafana продолжает использовать старую версию dashboard, можно пересоздать
её volume. Это удалит локальное состояние Grafana, поэтому команду следует
использовать осознанно:

```bash
docker compose down
docker volume ls
docker volume rm <имя_тома_grafana_data>
docker compose up -d
```

---

## Troubleshooting

| Симптом | Возможная причина | Что проверить |
|---|---|---|
| В InfluxDB нет данных после запуска | Не стартовал automatic ingest | `docker compose logs backend` |
| Backend не запускается | InfluxDB ещё не healthy или неверный токен | `docker compose ps`, `docker compose logs influxdb backend` |
| `unauthorized` | Токен в существующем InfluxDB volume не совпадает с `.env` | Проверьте token или пересоздайте volume |
| Ошибка `422` при ingest | Timestamp из будущего или вне retention | Проверьте `meta.timestamp` и `INFLUXDB_RETENTION` |
| Grafana открывается, но dashboard пуст | Неверный временной диапазон | Выберите диапазон, покрывающий timestamp точек |
| InfluxDB UI показывает пусто | Открыты не данные bucket, а другая секция интерфейса | Используйте Data Explorer |
| Grafana не показывает dashboard | Ошибка JSON или provisioning | `docker compose logs grafana` и проверка JSON |
| Grafana игнорирует новый пароль | Grafana уже инициализирована старым volume | Пересоздайте `grafana_data` |

Если credentials изменились после первого запуска, помните: InfluxDB и Grafana
сохраняют первоначальную инициализацию в Docker volumes. Для полного сброса
используйте следующую команду только если удаление локальных данных допустимо:

```bash
docker compose down -v
docker compose up -d --build
```

---

## Лицензия

Проект создан в рамках проектной работы MIEM HSE.

## Ссылки

- Исходный notebook и источник экспериментальных данных:
  <https://www.kaggle.com/code/flyin123/gemma-notebook>