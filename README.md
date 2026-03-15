# FastAPI URL Shortener

Сервис сокращения ссылок на `FastAPI` с регистрацией, статистикой, TTL и кэшированием в `Redis`.

## Что реализовано

Обязательные функции:
- `POST /links/shorten` - создание короткой ссылки.
- `GET /links/{short_code}` - редирект на оригинальный URL.
- `PUT /links/{short_code}` - обновление ссылки.
- `DELETE /links/{short_code}` - удаление ссылки.
- `GET /links/{short_code}/stats` - статистика по ссылке.
- `POST /links/shorten` с `custom_alias` - кастомный alias с проверкой уникальности.
- `GET /links/search?original_url=...` - поиск ссылки по оригинальному URL.
- `POST /links/shorten` с `expires_at` - срок жизни ссылки.

Дополнительные функции:
- `POST /links/cleanup/inactive` - удаление неиспользуемых ссылок по `N` дням.
- `GET /links/expired/history` - история истекших ссылок.
- `POST /links/cleanup/expired` - принудительная очистка истекших ссылок.

Регистрация и доступ:
- `POST /auth/register`
- `POST /auth/login`
- `PUT /links/{short_code}` и `DELETE /links/{short_code}` доступны только владельцу ссылки.

Кэширование:
- кэшируются редирект, статистика и поиск;
- при обновлении и удалении ссылки кэш инвалидируется.

## Стек

- `FastAPI`
- `SQLAlchemy`
- `SQLite` по умолчанию для локального запуска
- `PostgreSQL` для deploy
- `Redis`
- `JWT`

## Локальный запуск

### Без Docker

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Приложение будет доступно по адресу:
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

По умолчанию используется локальная база:
- `sqlite:///./shortener.db`

Если `Redis` не запущен, приложение все равно работает. Просто будет сообщение:
- `Redis unavailable, cache disabled`

### Через Docker

```bash
docker compose up --build
```

## Переменные окружения

Пример есть в [.env.example](c:\Users\vital\Documents\Мага\2 сем\pyhton\fastAPI\.env.example).

Основные переменные:
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BASE_URL`
- `DEFAULT_INACTIVE_DAYS`
- `CACHE_TTL_SECONDS`

Примечание:
- локально `BASE_URL` можно не задавать;
- тогда `short_url` будет собираться автоматически из текущего адреса запроса;
- на `Render` лучше задать `BASE_URL` явно.

## Как тестировать в Swagger

Важное различие:
- `short_code` - это только код, например `my-link-1`
- `short_url` - это полная короткая ссылка, например `http://127.0.0.1:8000/links/my-link-1`

Если endpoint ожидает `short_code`, не нужно вставлять полный URL.

Пример:
- правильно: `my-link-1`
- неправильно: `http://127.0.0.1:8000/links/my-link-1`

Еще один важный момент:
- `GET /links/{short_code}` делает реальный HTTP redirect;
- в Swagger UI такой endpoint может показывать `TypeError: NetworkError when attempting to fetch resource`;
- это не обязательно ошибка API;
- редирект лучше проверять обычным открытием `short_url` в браузере.

## Рекомендуемый сценарий проверки

### 1. Регистрация

`POST /auth/register`

```json
{
  "email": "test@example.com",
  "password": "secret123"
}
```

Ожидаемо:
- `201 Created`
- в ответе есть `id` и `email`

### 2. Логин

`POST /auth/login`

```json
{
  "email": "test@example.com",
  "password": "secret123"
}
```

Ожидаемо:
- `200 OK`
- в ответе есть `access_token`

### 3. Создание короткой ссылки

`POST /links/shorten`

```json
{
  "original_url": "https://example.com/page",
  "custom_alias": "my-link-1"
}
```

Ожидаемо:
- `201 Created`
- в ответе есть:
  - `short_code`
  - `short_url`
  - `original_url`

Пример ответа:

```json
{
  "short_code": "my-link-1",
  "short_url": "http://127.0.0.1:8000/links/my-link-1",
  "original_url": "https://example.com/page",
  "created_at": "2026-03-15T20:47:55.996716",
  "expires_at": null,
  "owner_id": null
}
```

### 4. Проверка редиректа

Открой в браузере:

```text
http://127.0.0.1:8000/links/my-link-1
```

Ожидаемо:
- браузер перекинет на `https://example.com/page`

### 5. Проверка статистики

`GET /links/{short_code}/stats`

В поле `short_code` вставить:

```text
my-link-1
```

Ожидаемо:
- `click_count` увеличен
- `last_used_at` заполнен

### 6. Поиск по оригинальному URL

`GET /links/search`

Параметр:

```text
original_url=https://example.com/page
```

Ожидаемо:
- `found: true`
- вернутся `short_code` и `short_url`

### 7. Авторизация в Swagger

После логина нажмите `Authorize` и вставьте токен.

Если Swagger не добавляет префикс сам, используйте:

```text
Bearer <access_token>
```

### 8. Обновление ссылки

`PUT /links/{short_code}`

Параметр `short_code`:

```text
my-link-1
```

Тело:

```json
{
  "original_url": "https://example.com/new-page",
  "expires_at": "2030-12-31T23:59:00Z"
}
```

Ожидаемо:
- `200 OK`
- ссылка обновлена

### 9. Удаление ссылки

`DELETE /links/{short_code}`

Параметр:

```text
my-link-1
```

Ожидаемо:
- `204 No Content`

После этого:
- `GET /links/my-link-1` должен вернуть `404`

## Примеры curl

### Регистрация

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"user@example.com\",\"password\":\"secret123\"}"
```

### Логин

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"user@example.com\",\"password\":\"secret123\"}"
```

### Создание короткой ссылки

```bash
curl -X POST http://127.0.0.1:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d "{\"original_url\":\"https://example.com/page\",\"custom_alias\":\"my-link-1\"}"
```

### Поиск ссылки

```bash
curl "http://127.0.0.1:8000/links/search?original_url=https://example.com/page"
```

## Deploy на Render

В проекте есть [render.yaml](c:\Users\vital\Documents\Мага\2 сем\pyhton\fastAPI\render.yaml) для `Blueprint Deploy`.

Что поднимается:
- web service
- PostgreSQL
- Redis

После deploy:
1. задайте `BASE_URL` равным публичному адресу сервиса на `Render`;
2. проверьте `GET /health`;
3. проверьте `POST /links/shorten` и редирект по `short_url`.

Если деплой без Blueprint, нужны:
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `BASE_URL`

## Что я успел проверить

Ручная проверка по текущей сессии:
- корневой маршрут `/` работает;
- `POST /auth/register` после замены схемы хеширования больше не падает из-за `bcrypt`;
- `POST /links/shorten` создает ссылку и возвращает корректный `short_url`;
- `GET /links/{short_code}` реально редиректит в браузере.

Что не было прогнано автоматически из терминала:
- полный набор интеграционных тестов;
- локальный запуск через `docker compose`;
- deploy на `Render`.
