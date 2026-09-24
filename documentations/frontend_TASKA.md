# Frontend MVP — Interactive Model Compression Demo

## 1. Цель

Необходимо реализовать frontend интерактивного демо для исследования влияния изменения параметров модели на её характеристики.

Пользователь должен иметь возможность:

1. увидеть базовую конфигурацию модели;
2. изменить отдельные параметры через UI;
3. отправить новую конфигурацию на backend;
4. получить prediction изменённых характеристик модели;
5. увидеть результат prediction в интерфейсе;
6. видеть Grafana Dashboard с историей/визуализацией результатов.

Frontend не выполняет вычисления модели самостоятельно.

Frontend не работает напрямую с InfluxDB.

Frontend не использует Grafana API.

Вся логика расчёта влияния параметров находится на backend.

---

# 2. Архитектура

Общий поток данных:

```text
                         BLACK BOX
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
````

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

# 3. Подготовка окружения

Frontend-разработчику необходимо:

```bash
git clone <repository>
docker compose up -d
python ingest.py comparison.json
```

Также это описано в `README.md`, рекомендовано к ознакомлению с ним, раздел `QUICKSTART` 

После этого инфраструктура должна быть доступна локально:

```text
InfluxDB -> http://localhost:8086
Grafana  -> http://localhost:3000
Backend  -> URL, указанный в README
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

# 4. Frontend stack

Использовать:

* React;
* TypeScript;
* Vite.

Для графиков frontend может использовать Plotly, ECharts или другой согласованный charting library.

---

# 5. Рекомендуемая структура

```text
frontend/
├── src/
│   ├── api/
│   │   ├── model.ts
│   │   └── prediction.ts
│   │
│   ├── components/
│   │   ├── ParameterPanel/
│   │   ├── MetricCards/
│   │   ├── SensitivityChart/
│   │   ├── PredictionChart/
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

# 6. Environment variables

Frontend не должен хардкодить URL backend и Grafana.

Необходимо предусмотреть:

```env
VITE_API_URL=http://localhost:<backend-port>
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Конкретный Grafana URL должен быть предоставлен BE/DevOps.

В Git не должны попадать:

* Grafana password;
* InfluxDB password;
* InfluxDB token;
* другие secrets.

Frontend не должен получать credentials InfluxDB или Grafana.

---

# 7. Backend API

В MVP frontend использует следующие endpoint'ы:

```http
GET /api/model
POST /api/predict
GET /health
```

`GET /api/experiments` не является обязательным для frontend.

История actual/predicted результатов отображается через Grafana.

---

# 8. GET /api/model

Endpoint:

```http
GET /api/model
```

Используется для получения конфигурации модели.

Frontend не должен хардкодить список параметров.

Пример:

```json
{
  "model_id": "demo_model_v1",
  "parameters": {
    "param_a": {
      "baseline": 0.82,
      "ui_min": 0.70,
      "ui_max": 0.90
    },
    "param_b": {
      "baseline": 0.47,
      "ui_min": 0.30,
      "ui_max": 0.70
    },
    "param_c": {
      "baseline": 1.15,
      "ui_min": 0.80,
      "ui_max": 1.40
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

---

# 9. Parameter Panel

На основании `/api/model` автоматически создать UI для каждого параметра.

Для каждого параметра показать:

* название;
* slider;
* minimum;
* maximum;
* текущий value;
* baseline;
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

---

# 10. Parameter changes

При изменении slider необходимо отправлять новую configuration на backend.

Endpoint:

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

Ползунки должны быть РЕАКТИВНЫМИ.
- Изменение значения slider МГНОВЕННО триггерит `POST /api/predict`.
- Кнопка «Применить» НЕ РЕАЛИЗУЕТСЯ.
- Пользователь видит изменение метрик и графиков в реальном времени при движении ползунка.
- Loading state ("Calculating...") обязателен во время ожидания ответа от predict.

Debounce для реакции slider-ов

```text
100–300 ms
```

Рекомендуется около 200 ms.

---

# 11. Prediction response

Backend возвращает prediction.

Пример:

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

Frontend должен отображать prediction, не выполняя повторных вычислений.

---

# 12. Metric Cards

Для основных metrics создать отдельные карточки:

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
0.7421

Baseline
0.7589

Delta
-0.0168
```

Направление metric необходимо учитывать.

Для:

```text
accuracy
f1
```

лучшее значение — больше.

Для:

```text
latency
memory
```

лучшее значение — меньше.

---

# 13. Baseline

Baseline — это исходная конфигурация модели, полученная из backend.

Важно:

```text
prediction(baseline) == actual compressed baseline
```

При нахождении всех sliders в baseline:

* prediction должна совпадать с baseline;
* UI должен отображать отсутствие изменения;
* Grafana должна иметь соответствующую baseline/actual точку.

---

# 14. Reset to baseline

Добавить кнопку:

```text
Reset to baseline
```

Кнопка вызывает отдельный endpoint или action, который:
1. Принудительно загружает конфигурацию из `data/comparison.json` (не из текущего состояния!).
2. Устанавливает все sliders в значения baseline compressed model.
3. Триггерит prediction для подтверждения.
4. Обновляет UI до исходного "якорного" состояния.
Это гарантирует, что пользователь всегда может вернуться к проверенной точке отсчета, 
даже если `data/model.json` был поврежден или изменен вручную.

---

# 15. Prediction Support

Отобразить `support`, возвращаемый backend.

Пример:

```text
Prediction support: HIGH
```

или:

```text
Prediction support: MEDIUM
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

---

# 16. Actual vs Predicted

Frontend должен явно отличать:

```text
Actual
```

от:

```text
Predicted
```

Actual — результат реального black-box experiment.

Predicted — результат surrogate model.

Prediction не должна визуально выглядеть как фактически измеренный результат.

Если frontend строит собственные prediction charts, необходимо использовать разные визуальные обозначения.

---

# 17. Grafana integration

Grafana уже поднимается и настраивается backend/devops частью.

Frontend не должен:

* подключаться к Grafana API;
* получать данные через Grafana API;
* подключаться к InfluxDB;
* знать InfluxDB token;
* создавать datasource;
* создавать Dashboard.

Frontend получает готовый Dashboard URL.

---

# 18. Grafana Dashboard URL

Добавить в `.env.example` и не забыть про `.env`:

```env
VITE_GRAFANA_DASHBOARD_URL=http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk
```

Конкретный URL будет предоставлен BE/DevOps.

Получать его в React:

```tsx
const grafanaUrl = import.meta.env.VITE_GRAFANA_DASHBOARD_URL;
```

Не хардкодить URL в компоненте.

---

# 19. GrafanaDashboard component

Создать:

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
      height="700"
      frameBorder="0"
    />
  );
}
```

---

# 20. Grafana role

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

# 21. Grafana layout

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

# 22. Loading states

Предусмотреть:

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

или аналогичный loading indicator.

---

# 23. Error handling

Frontend должен корректно обрабатывать:

```text
Backend unavailable
Prediction failed
Invalid parameter
Grafana unavailable
Invalid configuration
```

Grafana failure не должен ломать prediction UI.

Prediction failure не должен ломать Grafana UI.

---

# 24. Responsive layout

Минимально поддержать:

```text
1920x1080
1366x768
```

Grafana iframe должен адаптироваться к ширине контейнера.

---

# 25. Definition of Done

Frontend MVP считается готовым, если:

* [ ] приложение запускается;
* [ ] frontend получает `/api/model`;
* [ ] параметры строятся динамически;
* [ ] sliders работают;
* [ ] baseline отображается;
* [ ] delta отображается;
* [ ] Reset to baseline работает;
* [ ] изменения параметров отправляются через `/api/predict`;
* [ ] используется debounce;
* [ ] prediction отображается;
* [ ] baseline отображается;
* [ ] support отображается;
* [ ] low support сопровождается warning;
* [ ] actual/predicted явно различаются;
* [ ] Grafana Dashboard встроен через iframe;
* [ ] Grafana URL берётся из environment;
* [ ] frontend не работает напрямую с InfluxDB;
* [ ] frontend не использует Grafana API;
* [ ] frontend не хранит Grafana/InfluxDB credentials;
* [ ] loading/error states реализованы;
* [ ] интерфейс работает на 1920x1080 и 1366x768.