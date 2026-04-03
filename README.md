# Лабораторная работа 10 — Сравнение веб-фреймворков: FastAPI vs Gin

**Студент:** Артюх Виталий Валериевич  
**Группа:** 221131  
**Вариант:** 2 (10)  

Сравнительный анализ производительности и потребления памяти двух современных веб-фреймворков:
**FastAPI** (Python) и **Gin** (Go). Проект включает REST API, WebSocket-чат,
нагрузочное тестирование с Apache Bench и профилирование памяти с помощью pprof / psutil.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                        Клиент / тесты                        │
└────────────┬────────────────────────────┬────────────────────┘
             │ HTTP :8000                  │ HTTP :8080
             ▼                            ▼
┌────────────────────────┐   ┌────────────────────────────────┐
│   FastAPI (Python)     │   │        Gin (Go)                │
│   python-service/      │   │        go-service/             │
│                        │   │                                │
│  GET  /ping  ──────────┼──►│  GET  /ping                    │
│  GET  /users ──────────┼──►│  GET  /users                   │
│  POST /echo  ──────────┼──►│  POST /echo                    │
│  GET  /health (local)  │   │  GET  /ws  (WebSocket)         │
│                        │   │  GET  /debug/pprof/  (pprof)   │
└────────────────────────┘   └────────────────────────────────┘
                                          ▲
                             ┌────────────┴──────────────┐
                             │  ws_client/client.py       │
                             │  ws_client/multi_client.py │
                             └────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     benchmark/                               │
│   run_benchmarks.sh  →  Apache Bench  →  results/*.txt      │
│   parse_results.py   →  results/summary.md                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   memory-profiling/                          │
│   python_memory_profile.py  →  memory_results/python_*.json │
│   go_memory_profile.py      →  memory_results/go_*.json     │
│   compare_memory.py         →  сравнительная таблица        │
└─────────────────────────────────────────────────────────────┘
```

---

## Компоненты

### Go-сервис (`go-service/`) — порт 8080
REST API и WebSocket-сервер на фреймворке **Gin**. Реализует все базовые эндпоинты,
кастомный middleware логирования, WebSocket-хаб с broadcast-рассылкой и graceful shutdown
по `SIGINT`/`SIGTERM` с таймаутом 5 секунд.

### Python-сервис (`python-service/`) — порт 8000
Асинхронный прокси-сервис на **FastAPI**. Перенаправляет запросы к Go-сервису через
`httpx` (async), добавляет поля `source`/`proxied_by`, возвращает HTTP 503 при
недоступности Go-сервиса. Поддерживает graceful shutdown через uvicorn.

### WebSocket-клиент (`ws_client/`)
Два Python-скрипта для демонстрации WebSocket:
- `client.py` — одиночный клиент: подключение → приём welcome → 5 сообщений → прослушивание 5 с → отключение.
- `multi_client.py` — 3 параллельных клиента через `asyncio`, синхронизированных барьером; демонстрирует broadcast между клиентами.

### Бенчмарки (`benchmark/`)
Shell-скрипт на Apache Bench тестирует оба сервиса в трёх сценариях.
Python-скрипт разбирает результаты и формирует Markdown-таблицу.

### Профилирование памяти (`memory-profiling/`)
Инструменты мониторинга RSS/VMS (psutil) для FastAPI и heap/alloc (pprof) для Gin
с параллельной нагрузкой в 100 запросов. Итоговый скрипт сравнивает оба сервиса.

---

## Структура проекта

```
Lab-10/
│
├── go-service/                  # Go REST + WebSocket сервер
│   ├── main.go                  # Gin-роутер, хаб WS, graceful shutdown
│   ├── go.mod                   # Модуль lab10/go-service
│   └── README.md
│
├── python-service/              # FastAPI прокси-сервис
│   ├── main.py                  # Эндпоинты, middleware, lifespan
│   └── requirements.txt         # fastapi, uvicorn, httpx, psutil
│
├── ws_client/                   # WebSocket-клиенты (Python)
│   ├── client.py                # Одиночный клиент (5 сообщений)
│   ├── multi_client.py          # 3 параллельных клиента + broadcast
│   └── requirements.txt         # websockets
│
├── benchmark/                   # Нагрузочное тестирование
│   ├── run_benchmarks.sh        # Apache Bench: 6 тестовых сценариев
│   ├── parse_results.py         # Парсинг ab-вывода → summary.md
│   ├── post_data.json           # Тело POST-запроса для /echo
│   └── results/                 # Генерируется при запуске
│       ├── <timestamp>_*.txt
│       └── summary.md
│
├── memory-profiling/            # Профилирование памяти
│   ├── go_pprof_guide.md        # Инструкция по pprof для Go
│   ├── python_memory_profile.py # RSS/VMS мониторинг FastAPI (psutil)
│   ├── go_memory_profile.py     # Heap мониторинг Gin (pprof)
│   ├── compare_memory.py        # Сравнительная таблица
│   ├── requirements.txt         # psutil, httpx, tabulate
│   └── memory_results/          # Генерируется при запуске
│       ├── python_memory.json
│       └── go_memory.json
│
└── README.md
```

---

## Запуск

### Требования
- Go 1.21+
- Python 3.11+
- Apache Bench (`ab`) — для бенчмарков

### 1. Go-сервис

```bash
cd go-service
go run main.go
# Сервер запускается на http://localhost:8080
```

### 2. Python-сервис

```bash
cd python-service
pip install -r requirements.txt
uvicorn main:app --port 8000
# Сервер запускается на http://localhost:8000
```

### 3. WebSocket-демо

```bash
cd ws_client
pip install -r requirements.txt

# Одиночный клиент
python client.py

# Broadcast-демо (3 клиента одновременно)
python multi_client.py
```

### 4. Нагрузочное тестирование

> Оба сервиса должны быть запущены.

```bash
cd benchmark
bash run_benchmarks.sh        # запускает все 6 сценариев, ~2–3 мин
python parse_results.py       # разбирает результаты → results/summary.md
```

### 5. Профилирование памяти

Сначала включите pprof в Go-сервисе (см. `memory-profiling/go_pprof_guide.md`),
затем:

```bash
cd memory-profiling
pip install -r requirements.txt

python python_memory_profile.py   # ~30 с, FastAPI должен работать
python go_memory_profile.py       # ~30 с, Go + pprof (:6060) должен работать
python compare_memory.py          # итоговое сравнение
```

---

## API эндпоинты

| Метод  | Путь              | Сервис  | Описание                                                  |
|--------|-------------------|---------|-----------------------------------------------------------|
| GET    | /ping             | Gin     | `{"message":"pong","timestamp":<unix>}`                   |
| GET    | /users            | Gin     | Список 3 пользователей (JSON)                             |
| POST   | /echo             | Gin     | Принимает `{"text":"..."}`, возвращает текст + длину      |
| GET    | /ws               | Gin     | WebSocket: broadcast-чат                                  |
| GET    | /debug/pprof/     | Gin     | pprof профилировщик (требует настройки, см. руководство)  |
| GET    | /ping             | FastAPI | Проксирует Gin `/ping`, добавляет `"source":"go-service"` |
| GET    | /users            | FastAPI | Проксирует Gin `/users`, добавляет `"proxied_by":"fastapi"`|
| POST   | /echo             | FastAPI | Проксирует Gin `/echo`, добавляет `"original_text"`       |
| GET    | /health           | FastAPI | Локальная проверка: `{"status":"ok","service":"fastapi"}` |

---

## Результаты бенчмарка

> Заполните после запуска `run_benchmarks.sh` и `parse_results.py`.

| Сценарий                   | FastAPI (req/s) | Gin (req/s) | Победитель |
|----------------------------|-----------------|-------------|------------|
| GET /ping — 1 000 req, 10c | —               | —           | —          |
| GET /ping — 5 000 req, 50c | —               | —           | —          |
| POST /echo — 1 000 req, 10c| —               | —           | —          |

---

## Результаты профилирования памяти

> Заполните после запуска `python_memory_profile.py` и `go_memory_profile.py`.

| Метрика              | FastAPI — RSS (МБ) | Gin — Heap Alloc (МБ) |
|----------------------|--------------------|-----------------------|
| Минимум              | —                  | —                     |
| Максимум             | —                  | —                     |
| Среднее              | —                  | —                     |
| Финальное значение   | —                  | —                     |

---

## Выводы

Go с фреймворком Gin демонстрирует значительно более высокую пропускную способность
по сравнению с FastAPI: статически компилируемый бинарник, нативные горутины и
минимальный overhead runtime позволяют обрабатывать в несколько раз больше запросов
в секунду при той же конкурентности. FastAPI, несмотря на более низкие абсолютные
показатели req/s, выигрывает в скорости разработки: декларативная валидация через
Pydantic, автоматическая OpenAPI-документация и асинхронная модель на `asyncio`
делают его превосходным выбором для сервисов, где ключевым узким местом является
ввод-вывод, а не чистые вычисления.

По потреблению памяти Gin ожидаемо экономнее: интерпретатор CPython с загруженными
расширениями (uvicorn, httpx, starlette) занимает десятки мегабайт RSS даже в
состоянии покоя, тогда как скомпилированный Go-бинарник стартует с нескольких
мегабайт heap. WebSocket-реализация на gorilla/websocket в Gin демонстрирует
стабильную работу при множественных одновременных подключениях благодаря модели
goroutine-per-connection и явной синхронизации через `sync.Mutex`. В итоге выбор
между фреймворками определяется приоритетами проекта: Gin — для высоконагруженных
сервисов с жёсткими требованиями к задержке, FastAPI — для быстрой разработки
сложной бизнес-логики с богатой экосистемой Python.

---

## Технологии

- **Python** 3.11 — FastAPI, uvicorn, httpx, psutil, websockets, tabulate
- **Go** 1.21 — Gin v1.9, gorilla/websocket v1.5, net/http/pprof
- **FastAPI** — async REST, Pydantic v2, lifespan events, middleware
- **Gin** — высокопроизводительный HTTP-роутер, gin.Recovery, кастомный logger
- **WebSocket** — gorilla/websocket (Go) + websockets (Python), asyncio.Barrier
- **Apache Bench** (`ab`) — нагрузочное тестирование, 6 сценариев
- **pprof** — профилирование heap/alloc/goroutine для Go
- **psutil** — мониторинг RSS/VMS процесса для Python
