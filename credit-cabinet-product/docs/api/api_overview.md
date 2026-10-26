# API: обзор контракта (D11, часть 1)
Статус: готов к ревью dev · Версия: 1.0 · Обновлено: 2026-10-24
Связано с: R-05, R-15, R-20, R-25 · [state_machine](../process/state_machine.md) · [data_model](../architecture/data_model.md) · `openapi.yaml` (dev генерирует по этому документу) · коллекция [`collection/`](collection/README.md)

## Решение в одном абзаце
REST + JSON, база `/api/v1`, JWT в `Authorization: Bearer`. Каждый эндпоинт, меняющий статус, соответствует ровно одному переходу state machine, возвращает новый `status` и `version` и отклоняет недопустимый переход `409 INVALID_TRANSITION`. Клиентское и банковское представления заявки — **разные DTO**: клиент никогда не получает баллы, классы риска и внутренние коды. Внешние источники — отдельный сервис моков со своим контрактом, чтобы замена мока на реальную интеграцию не меняла основной API. PM отвечает за смысл, поля и ошибки; dev — за типы, коды и `openapi.yaml`.

## 1. Общие правила

| Тема | Правило |
| --- | --- |
| Аутентификация | `POST /auth/login` → JWT (TTL 8 ч), роли в claims; RBAC на каждом эндпоинте |
| Доступ к данным | Клиент — только заявки компаний из своих Membership (`403` иначе); эксперт/админ — все |
| Идемпотентность | `Idempotency-Key` обязателен для `submit`, `info-response`, `offer/accept`, `sign`, `decision`; повтор возвращает сохранённый ответ |
| Конкурентность | Изменяющие запросы принимают `If-Match: <version>`; несовпадение → `409 VERSION_CONFLICT` |
| Асинхронность | `submit` и `info-response` → `202 Accepted`; дальнейшие статусы — через SSE `GET /applications/{id}/stream` или polling `GET /applications/{id}` |
| Трассировка | Каждый ответ содержит заголовок `X-Trace-Id`; он же в теле ошибки и логах |
| Валидация | Ошибки полей → `422 VALIDATION_ERROR` с `details[]` |
| Документация | Swagger UI: `/api/docs`, спецификация: `/api/openapi.json` |

## 2. Эндпоинты

| Метод и путь | Назначение | Роль | Переход | Ключевые ответы |
| --- | --- | --- | --- | --- |
| `POST /auth/login` | Вход, выдача JWT | Все | — | 200, 401, 429 |
| `GET /me` | Профиль, роль, компании и роль в них | Все | — | 200 |
| `GET /products` | Каталог продуктов | Клиент | — | 200 |
| `POST /products/recommend` | Подбор по цели, сумме, сроку | Клиент | — | 200 (список с `reason`), 422 |
| `POST /products/{code}/calculate` | Платёж и переплата по базовой ставке | Клиент | — | 200, 422 |
| `GET /companies/lookup?inn=` | Реквизиты из `[MOCK ЕГРЮЛ/ЕГРИП]` | Клиент | — | 200, 404, 422 |
| `GET /companies/{id}` | Профиль компании | Клиент | — | 200, 403 |
| `POST /applications` | Создать черновик | Клиент | T0 | 201 |
| `PATCH /applications/{id}` | Автосохранение черновика | Клиент | — | 200, 409, 422 |
| `POST /applications/{id}/documents` | Загрузка файла (multipart) | Клиент | — | 201, 413, 415, 409 |
| `DELETE /applications/{id}/documents/{docId}` | Удалить файл (только DRAFT/NEEDS_INFO) | Клиент | — | 204, 409 |
| `POST /applications/{id}/submit` | Отправка | Клиент | T1 | 202, 409 `DUPLICATE`, 422 |
| `GET /applications` | Список заявок клиента | Клиент | — | 200 |
| `GET /applications/{id}` | Карточка (клиентское представление) | Клиент | — | 200, 403, 404 |
| `GET /applications/{id}/events` | Таймлайн (клиентские тексты) | Клиент, эксперт | — | 200 |
| `GET /applications/{id}/stream` | SSE: изменения статуса | Клиент | — | 200 `text/event-stream` |
| `GET /applications/{id}/info-request` | Открытый запрос информации | Клиент | — | 200, 404 |
| `POST /applications/{id}/info-response` | Ответ на запрос | Клиент | T6 | 202, 422, 409 |
| `GET /applications/{id}/offer` | Оффер, «вы просили / мы предлагаем», объяснение | Клиент | — | 200, 404 |
| `POST /applications/{id}/offer/accept` | Принять оффер | Клиент | T18 | 200, 409 `OFFER_EXPIRED` |
| `POST /applications/{id}/offer/decline` | Отказаться (в т.ч. на подписании) | Клиент | T19 / T24 | 200, 409 |
| `GET /applications/{id}/signing` | Договор-заглушка и код подписи | Клиент | — | 200, 409 |
| `POST /applications/{id}/sign` | Подписать кодом | Клиент | T21 | 200, 422 `SIGN_CODE_INVALID`, 409 |
| `POST /applications/{id}/cancel` | Отзыв заявки | Клиент | T22 | 200, 409 |
| `GET /loans/{id}` · `GET /applications/{id}/loan` | Кредит и график | Клиент | — | 200, 404 |
| `GET /feed` | Персональная лента с `reason` | Клиент | — | 200 |
| `POST /feed/{cardId}/seen` | Отметить показ | Клиент | — | 204 |
| `GET /notifications` · `POST /notifications/{id}/read` | In-app уведомления | Клиент | — | 200, 204 |
| `GET /backoffice/applications` | Очередь: фильтры `status`, `product`, `riskClass`, `inn`, сортировка `sla` | Эксперт, админ | — | 200, 403 |
| `GET /backoffice/applications/{id}` | Полная карточка: анкета, обогащение, скоринги, документы, события, рекомендованный оффер | Эксперт, админ | — | 200 |
| `GET /backoffice/documents/{docId}` | Скачать файл | Эксперт, админ | — | 200 |
| `POST /backoffice/applications/{id}/decision` | Решение эксперта | Эксперт | T16a/b/c | 200, 409, 422 |
| `POST /backoffice/applications/{id}/info-request` | Запрос информации | Эксперт | T17 | 201, 409, 422 |
| `GET /backoffice/audit` | Журнал (фильтры `applicationNumber`, `actor`, период) | Админ | — | 200 |
| `GET /backoffice/metrics` | Дашборд (Should) | Админ | — | 200 |
| `GET /backoffice/feed-preview?userId=` | Лента «глазами клиента» (Should) | Админ | — | 200 |
| `POST /admin/demo/reset` | Сброс демо | Админ | — | 200; 404 при `DEMO_MODE=false` |
| `GET /health` · `GET /ready` | Живость и готовность (БД, моки) | — | — | 200, 503 |

Автоматические переходы T2–T4, T7–T15, T20, T23 выполняет воркер; HTTP-эндпоинтов для них нет.

## 3. Сервис моков (отдельный контейнер `mocks`)

| Запрос | Ответ 200 (смысл) | Сбои |
| --- | --- | --- |
| `GET /mock/egrul/{inn}` (10 цифр) · `GET /mock/egrip/{inn}` (12 цифр) | `inn, ogrn, name, legal_form, okved, registration_date, status, address, director` | `404` — нет в реестре |
| `GET /mock/transparent-business/{inn}` | `persons[{name, role, disqualified}]`, `address`, `okved` | `404` |
| `GET /mock/bki/{inn}` (заголовок `X-Consent-Id`) | `has_history, worst_overdue_12m, current_overdue_days, inquiries_30d, active_loans` | `404`; `504` после 3 с для ИНН C6 |
| `GET /mock/internal/clients/{inn}` | `bank_client_since` | `404` — не клиент |

Данные — из `seed/mock_*.json`; переопределение режима для демо: `POST /mock/admin/mode {inn, source, mode: OK|TIMEOUT|NOT_FOUND}` (только `DEMO_MODE`).

## 4. Единый формат ошибки

```json
{
  "code": "INVALID_TRANSITION",
  "message": "Нельзя подписать заявку в статусе «Заявку рассматривает специалист»",
  "details": [{"field": "status", "issue": "MANUAL_REVIEW → DISBURSED is not allowed"}],
  "traceId": "4f1c2a9e7b"
}
```

| Код | HTTP | Когда |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | Поле не прошло проверку (ИНН, лимиты, пустой комментарий) |
| `DUPLICATE` | 409 | Активная заявка компании на тот же продукт |
| `INVALID_TRANSITION` | 409 | Переход не из таблицы state machine |
| `VERSION_CONFLICT` | 409 | Устаревшая `version` |
| `OFFER_EXPIRED` | 409 | Оффер истёк |
| `SIGN_CODE_INVALID` | 422 | Неверный код подписи |
| `FILE_TOO_LARGE` / `UNSUPPORTED_MEDIA_TYPE` | 413 / 415 | Загрузка файла |
| `UNAUTHORIZED` / `FORBIDDEN` / `NOT_FOUND` | 401 / 403 / 404 | Доступ |
| `REGISTRY_STOP` | — | Код причины отказа в Decision (не HTTP-ошибка) |
| `SOURCE_UNAVAILABLE` | — | Флаг в карточке эксперта при T10 |
| `RATE_LIMITED` | 429 | Перебор попыток входа |

## 5. Примеры запросов (используются в README)

**1. Автозаполнение по ИНН**
```http
GET /api/v1/companies/lookup?inn=001588139913
Authorization: Bearer <token anna>

200 OK
{ "inn": "001588139913", "ogrn": "324008698797301", "name": "ИП Зернова Анна Сергеевна («Кофейня Зерно»)",
  "legalForm": "ИП", "okved": "56.10", "registrationDate": "2024-04-15", "status": "ACTIVE",
  "address": "г. Условный, ул. Кофейная, д. 7", "director": "Зернова Анна Сергеевна", "source": "REGISTRY" }
```

**2. Отправка заявки**
```http
POST /api/v1/applications/7c9e.../submit
Authorization: Bearer <token anna>
Idempotency-Key: 5b0d1f3c-...
If-Match: 4

202 Accepted
{ "id": "7c9e...", "number": 1001, "status": "SUBMITTED", "version": 5,
  "clientStep": {"index": 1, "title": "Заявка принята", "next": "Проверим, всё ли заполнено, — это несколько минут"} }
```

**3. Оффер с контрпредложением (клиентское представление)**
```http
GET /api/v1/applications/7c9e.../offer

200 OK
{ "status": "APPROVED_WITH_CHANGES",
  "requested": {"productCode": "EXPRESS", "amount": 4000000, "termMonths": 12},
  "offer": {"productCode": "EXPRESS", "amount": 3000000, "termMonths": 12, "rate": 24.0,
            "monthlyPayment": 283679, "totalOverpayment": 404145, "changeType": "AMOUNT",
            "expiresAt": "2026-11-03T12:00:00+03:00"},
  "explanation": {"why": "По результатам оценки мы можем сразу одобрить до 3 000 000 ₽",
                  "factors": ["Заметная долговая нагрузка", "Вы давно обслуживаетесь в банке", "Хорошая кредитная история"],
                  "source": "TEMPLATE"} }
```
ИНН/ОГРН в примерах совпадают с [`seed/mock_registry.json`](../../seed/mock_registry.json).

**4. Решение эксперта**
```http
POST /api/v1/backoffice/applications/{id}/decision
{ "outcome": "APPROVED_WITH_CHANGES", "amount": 700000, "termMonths": 18, "rate": 26.0,
  "productCode": "EXPRESS", "reasonCode": null, "comment": "Класс C: снижаем сумму, удлиняем срок" }
```

**5. SSE-событие статуса**
```
event: status
data: {"applicationId":"7c9e...","status":"NEEDS_INFO","version":7,"clientStep":{"index":2,"title":"Нужны уточнения"},"at":"2026-10-24T12:01:09+03:00"}
```

## 6. Клиентское vs банковское представление заявки

| Поле | Клиент (`/applications/{id}`) | Эксперт (`/backoffice/applications/{id}`) |
| --- | --- | --- |
| `status` | ✓ + `clientStep` (6 шагов, тексты) | ✓ технический |
| Анкета, документы | ✓ | ✓ + подсветка расхождений |
| `enrichment[]` | — | ✓ все источники и попытки |
| `scoring[]` | — | ✓ все результаты: баллы, класс, факторы, версия правил |
| Объяснение | `explanation.factors[]` = `clientText` | `factors[]` с `points` и `expertText` |
| `decision.comment`, `reasonCodes` | — | ✓ |
| `recommendedOffer` | — | ✓ (для MANUAL_REVIEW) |
| `events[]` | Клиентские заголовки | Полные: переход, actor, reason |

## 7. Коллекция запросов
Bruno (бесплатный, без аккаунта, файлы в git): `docs/api/collection/`. Папки `E2E-01…E2E-05`, `NEG-01…NEG-12`; окружение `local` (`baseUrl=http://localhost:8080/api/v1`), токены учёток получаются pre-request скриптом логина. Структура и порядок — [collection/README.md](collection/README.md). Прогон в CI: `bru run --env local` (Should).

## Допущения
- [ДОПУЩЕНИЕ] SSE основной канал статусов, polling 3 с — фолбэк (см. [05_decisions](../product/05_decisions.md#d-02)).

## Имитации
- [MOCK] Контракты `/mock/*` упрощены, но сохраняют цель интеграции: что запрашиваем (ИНН, согласие), что получаем, как используем (автозаполнение, стоп-факторы, факторы скоринга).

## Открытые вопросы
- dev: генерация `openapi.yaml` из кода или code-first — без влияния на смысл контракта.

## DoD
- [x] Таблица эндпоинтов покрывает все клиентские/экспертные переходы state machine и все экраны
- [x] Формат ошибок и справочник кодов
- [x] 3+ примера запросов для README
- [ ] `openapi.yaml` сгенерирован dev и сверен с этим документом
