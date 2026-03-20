# FastAPI URL Shortener

Сервис сокращения ссылок на `FastAPI` с регистрацией, статистикой, TTL, кэшированием в `Redis` и тестовым покрытием для ДЗ по тестированию.

## Функциональность

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

Особенности:
- кастомные alias;
- срок жизни ссылки через `expires_at`;
- ограничение `PUT/DELETE` только для владельца;
- кэш для редиректа, статистики и поиска;
- deploy на `Render`.

## Запуск

### Локально

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Адреса:
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

### Через Docker

```bash
docker compose up --build
```

## Конфигурация

Пример переменных есть в `.env.example`.

Основные env:
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BASE_URL`
- `DEFAULT_INACTIVE_DAYS`
- `CACHE_TTL_SECONDS`

Локально `BASE_URL` можно не задавать. Тогда `short_url` собирается автоматически из текущего host.

## Тестирование

Тесты лежат в папке `tests/` и делятся на:
- юнит-тесты для auth, cache, utility-логики и TTL;
- функциональные тесты для всех основных endpoint-ов через `TestClient`;
- нагрузочный сценарий в `locustfile.py`.

Файлы:
- `tests/conftest.py`
- `tests/test_unit.py`
- `tests/test_api.py`
- `pytest.ini`

### Запуск тестов

```bash
pytest tests
```

### Проверка покрытия

```bash
coverage run -m pytest tests
coverage html
coverage report
```

Последний успешный прогон в проекте:
- `47 passed`
- общее покрытие: `95%`

HTML-отчет уже сгенерирован и лежит в:
- `htmlcov/index.html`

### Нагрузочное тестирование

Пример запуска `Locust`:

```bash
locust -f locustfile.py --host http://127.0.0.1:8000
```

Сценарий проверяет:
- массовое создание коротких ссылок;
- поиск ссылок;
- healthcheck;
- базовую нагрузку на CRUD и кэшируемые endpoint-ы.

## Как проверять API вручную

Важно:
- `short_code` это только код, например `my-link-1`
- `short_url` это полная ссылка, например `http://127.0.0.1:8000/links/my-link-1`

Если endpoint ожидает `short_code`, не нужно вставлять полный URL.

Для `GET /links/{short_code}`:
- в Swagger возможен `TypeError: NetworkError when attempting to fetch resource`
- это нормальная особенность redirect endpoint-а
- сам редирект лучше проверять открытием `short_url` в браузере

### Базовый сценарий ручной проверки

1. `POST /auth/register`
```json
{
  "email": "test@example.com",
  "password": "secret123"
}
```

2. `POST /auth/login`
```json
{
  "email": "test@example.com",
  "password": "secret123"
}
```

3. `POST /links/shorten`
```json
{
  "original_url": "https://example.com/page",
  "custom_alias": "my-link-1"
}
```

4. открыть `short_url` в браузере

5. `GET /links/{short_code}/stats`

6. `GET /links/search?original_url=https://example.com/page`

7. после авторизации в Swagger:
- `PUT /links/{short_code}`
- `DELETE /links/{short_code}`

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

На `Render` `BASE_URL` должен быть равен публичному домену сервиса, например:

```text
https://fastapi-project-3-ftlx.onrender.com
```

## Что было исправлено в рамках ДЗ по тестированию

Во время написания тестов был найден и исправлен дефект:
- в логике TTL происходило сравнение naive/aware datetime в `delete_if_expired()`;
- это ломало проверку истекших ссылок на SQLite;
- после исправления сценарии с `expires_at` покрыты тестами и проходят стабильно.
