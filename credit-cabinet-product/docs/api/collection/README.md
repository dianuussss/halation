# Коллекция запросов (Bruno)
Спецификация для dev: коллекция повторяет тест-сценарии из [test_scenarios](../../testing/test_scenarios.md) и проходит целиком на свежем seed (`POST /admin/demo/reset` первым запросом).

```
collection/
├── bruno.json
├── environments/local.bru          # baseUrl=http://localhost:8080/api/v1, mocksUrl=http://localhost:8090
├── 00_setup/                       # reset демо, логин всех 6 учёток → переменные token_*
├── E2E-01_happy_path_needs_info_counteroffer/   # anna / C1
├── E2E-02_auto_reject/                          # igor / C2
├── E2E-03_manual_review_approve/                # marina / C3 + expert
├── E2E-04_expert_info_request/                  # sidorov / C4 + expert
├── E2E-05_alternative_product/                  # sidorov / C7
└── NEG/                            # NEG-01 … NEG-12, по файлу на сценарий
```

Правила:
- Каждый запрос содержит пример тела и `assert` на HTTP-код, `status`, `version` и ключевые поля (например, `offer.amount == 3000000` для C1).
- Автоматические переходы ждём циклом `GET /applications/{id}` с таймаутом 30 с (при `DEMO_STEP_DELAY_MS=0` в CI — 5 с).
- Ожидаемые числа берутся из `tools/reference/expected_outcomes.py --json`, а не вписываются руками.
- Секреты не храним: пароль демо-учёток — переменная окружения `DEMO_PASSWORD`.
