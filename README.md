# FastAPI URL Shortener

API-сервис сокращения ссылок на `FastAPI` с регистрацией, статистикой, TTL, кэшированием в `Redis`, базой `PostgreSQL/SQLite` и тестовым покрытием для ДЗ по тестированию.

## API

Основные endpoint-ы:
- `POST /auth/register`
- `POST /auth/login`
- `POST /links/shorten`
- `GET /links/{short_code}`
- `PUT /links/{short_code}`
- `DELETE /links/{short_code}`
- `GET /links/{short_code}/stats`
- `GET /links/search?original_url=...`

Дополнительные endpoint-ы:
- `POST /links/cleanup/inactive`
- `GET /links/expired/history`
- `POST /links/cleanup/expired`

## Примеры запросов

Регистрация:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"user@example.com\",\"password\":\"secret123\"}"
```

Логин:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"user@example.com\",\"password\":\"secret123\"}"
```

Создание короткой ссылки:

```bash
curl -X POST http://127.0.0.1:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d "{\"original_url\":\"https://example.com/page\",\"custom_alias\":\"my-link-1\"}"
```

Поиск ссылки:

```bash
curl "http://127.0.0.1:8000/links/search?original_url=https://example.com/page"
```

## Запуск

Локально:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Docker:

```bash
docker compose up --build
```

Полезные адреса:
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

Пример env-файла: `.env.example`

Основные переменные:
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BASE_URL`
- `DEFAULT_INACTIVE_DAYS`
- `CACHE_TTL_SECONDS`

## База данных и кэш

- локально по умолчанию используется `SQLite`;
- для deploy используется `PostgreSQL`;
- для кэша используется `Redis/Key Value`;
- модели находятся в `app/models.py`.

## Тестирование

Тесты:
- `tests/test_unit.py`
- `tests/test_api.py`
- `tests/conftest.py`

Нагрузочный сценарий:
- `locustfile.py`

Запуск тестов:

```bash
pytest tests
```

Проверка покрытия:

```bash
coverage run -m pytest tests
coverage report
coverage html
```

Последний успешный результат покрытия приложения `app/`:
- `47 passed`
- `TOTAL 95%`

Текстовая сводка покрытия:

```text
Name              Stmts   Miss  Cover
-------------------------------------
app\__init__.py       0      0   100%
app\auth.py          44      0   100%
app\cache.py         44      7    84%
app\config.py        18      0   100%
app\database.py      19      1    95%
app\main.py         208     13    94%
app\models.py        37      0   100%
app\schemas.py       51      0   100%
-------------------------------------
TOTAL               421     21    95%
```

HTML-отчет:
- `htmlcov/index.html`

Запуск нагрузочного теста:

```bash
locust -f locustfile.py --host http://127.0.0.1:8000
```

## Deploy на Render

В проекте есть `render.yaml`.

Для полного deploy нужны:
- `Web Service`
- `Postgres`
- `Key Value`

В `Environment` web service должны быть:
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BASE_URL`

Пример `BASE_URL`:

```text
https://fastapi-project-3-ftlx.onrender.com
```
