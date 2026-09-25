# 0\. Общая схема проекта

```text
                         ┌────────────────────┐
                         │      BLACK BOX     │
                         │                    │
                         │  FP16 model        │
                         │       ↓            │
                         │  compression       │
                         │       ↓            │
                         │  critical params   │
                         └─────────┬──────────┘
                                   │
                              result JSON
                                   │
                                   ▼
                         ┌────────────────────┐
                         │      BACKEND       │
                         │                    │
                         │ validation         │
                         │ normalization      │
                         │ sensitivity model  │
                         │ prediction API     │
                         └─────────┬──────────┘
                                   │
                              REST / JSON
                                   │
                                   ▼
                         ┌────────────────────┐
                         │      FRONTEND      │
                         │                    │
                         │ parameter sliders  │
                         │ predictions        │
                         │ charts             │
                         │ actual vs predicted│
                         └────────────────────┘

             ┌─────────────────────────────────────────┐
             │              INFLUXDB                   │
             │      фактически полученные данные       │
             └────────────────────┬────────────────────┘
                                  │
                                  ▼
             ┌─────────────────────────────────────────┐
             │               GRAFANA                   │
             │       мониторинг actual results         │
             └─────────────────────────────────────────┘
```

\---


## BLK-001 — Экспорт конфигурации эксперимента

**Цель:** сделать возможным однозначно восстановить, с какими параметрами был произведён конкретный compression run.

Black box должен предоставить значения всех параметров, использованных при построении `compressed_model`.

Минимальный формат:

```json
{
  "configuration": {
    "parameter_a": 0.82,
    "parameter_b": 0.47,
    "parameter_c": 1.15
  }
}
```

### Требования

* Каждый параметр должен иметь стабильное имя.
* Имя параметра не должно зависеть от конкретного запуска.
* Значение должно быть сериализуемым в JSON.
* Тип значения должен быть определён:

  * integer;
  * float;
  * boolean;
  * categorical/string.
* Если параметр не применялся в конкретной конфигурации — это должно быть явно обозначено, а не заменено произвольным `0`.

### Acceptance criteria

Для любого `experiment_id` backend может ответить:

> Какие значения всех critical parameters использовались в этом эксперименте?

\---

# 3\. BLK-002 — Список critical parameters

Black box должен отдельно сообщать:

```json
{
  "critical_parameters": [
    "parameter_a",
    "parameter_b",
    "parameter_c"
  ]
}
```

Либо, предпочтительно:

```json
{
  "critical_parameters": {
    "parameter_a": {
      "critical": true
    },
    "parameter_b": {
      "critical": true
    },
    "parameter_c": {
      "critical": true
    }
  }
}
```

### Почему отдельно?

Потому что backend не должен самостоятельно пытаться угадать:

> этот параметр critical или нет?

Если именно black box является источником этой информации, он остаётся **source of truth**.

\---

# 4\. BLK-003 — Значение baseline

Для каждого critical parameter желательно сохранить значение, соответствующее полученному `compressed_model`.

То есть:

```json
{
  "parameter_a": {
    "value": 0.82
  }
}
```

Если `configuration` уже содержит это значение, отдельное поле необязательно.

Главное правило:

```text
configuration.parameter_a
             ↓
         baseline
```

не должно быть неоднозначности.

\---

# 5\. BLK-004 — Диапазон параметров

Здесь нужно **не заставлять black box придумывать диапазоны**, если он их не знает.

Если программа имеет допустимый диапазон:

```json
{
  "parameter_a": {
    "min": 0.70,
    "max": 0.90
  }
}
```

его стоит передавать.

Если программа этого не знает — backend/frontend должны использовать отдельно заданный UI range:

```json
{
  "parameter_a": {
    "ui_min": 0.70,
    "ui_max": 0.90
  }
}
```

Это две разные вещи:

```text
valid_range ≠ ui_range
```

\---

# 6\. BLK-005 — Metrics

Текущий формат можно сохранить:

```json
{
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
  ]
}
```

Дополнительно желательно передавать metadata о метрике:

```json
{
  "metric": "accuracy_top1",
  "direction": "higher_is_better"
}
```

Но это можно сделать и на backend.

\---

# 7\. BLK-006 — Per-class

Ничего специально менять не требуется.

Оставить текущий формат:

```json
{
  "per_class": [
    {
      "class": "class_1",
      "full": 0.81,
      "compressed": 0.79
    }
  ]
}
```

Backend должен сохранить возможность его принять, но **MVP UI может его вообще не использовать**.

\---

# 8\. BLK-007 — Уникальный experiment ID

Каждый run должен иметь:

```json
{
  "experiment_id": "exp_20260915_001"
}
```

ID должен быть уникальным.

Это позволит связать:

```text
experiment
    ↓
JSON
    ↓
InfluxDB
    ↓
Grafana
    ↓
surrogate
```

\---

# 9\. BLK-008 — Необходимые дополнительные данные

Вот это **опциональный**, но очень желательный пункт.

Если black box способен отдавать:

* importance;
* sensitivity;
* score;
* ranking;
* допустимый range;
* intermediate evaluation;
* layer/group statistics;
* quantization error;

— **сохранять их**.

Даже если MVP их пока не использует.

Например:

```json
{
  "parameter_analysis": {
    "parameter_a": {
      "importance": 0.91
    },
    "parameter_b": {
      "importance": 0.63
    }
  }
}
```

Это даст вам возможность позже перейти от гипотетического `sensitivity_weight` к данным, полученным непосредственно от black box.

\---

# 10\. Итоговое ТЗ для Black Box

### Обязательно

```text
[ ] experiment_id
[ ] full model identifier
[ ] compressed model identifier
[ ] timestamp
[ ] configuration всех использованных параметров
[ ] список critical parameters
[ ] baseline values
[ ] metrics
[ ] per_class
```

### Желательно

```text
[ ] parameter importance
[ ] parameter sensitivity
[ ] parameter valid ranges
[ ] intermediate parameter analysis
[ ] quantization statistics
```

### Не требуется

```text
[ ] запускать black box из backend
[ ] предоставлять API для frontend
[ ] выполнять real-time evaluation
```

**Black box на MVP остаётся полностью offline.**  
**Также стоит подчеркнуть, что база остаётся работать - black box должен работать точно так же, как и раньше, а этот таск - всего лишь коррекция output.**
