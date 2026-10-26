"""Генератор синтетических seed-данных (docs/testing/test_data.md).

Все ИНН/ОГРН имеют валидную контрольную сумму, но код региона «00» не существует —
идентификаторы гарантированно вымышленные. ФИО, адреса и названия условные.
Запуск: python3 tools/reference/gen_seed.py  → перезаписывает seed/*.json
"""
import json, random, pathlib, bcrypt

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED = ROOT / "seed"
rnd = random.Random(2026)  # детерминизм


def _inn10(body: str) -> str:  # body: 9 digits
    c = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    s = sum(int(body[i]) * c[i] for i in range(9))
    return body + str(s % 11 % 10)


def _inn12(body: str) -> str:  # body: 10 digits
    c1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    n11 = sum(int(body[i]) * c1[i] for i in range(10)) % 11 % 10
    b = body + str(n11)
    c2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    n12 = sum(int(b[i]) * c2[i] for i in range(11)) % 11 % 10
    return b + str(n12)


def _ogrn(body12: str) -> str:
    return body12 + str(int(body12) % 11 % 10)


def _ogrnip(body14: str) -> str:
    return body14 + str(int(body14) % 13 % 10)


def digits(n):
    return "".join(str(rnd.randint(0, 9)) for _ in range(n))


def legal(year):  # ООО: ИНН 10, ОГРН 13 (признак 1, год, регион 00)
    return _inn10("00" + digits(7)), _ogrn("1" + str(year)[2:] + "00" + digits(7))


def ip(year):     # ИП: ИНН 12, ОГРНИП 15 (признак 3)
    return _inn12("00" + digits(8)), _ogrnip("3" + str(year)[2:] + "00" + digits(9))


# ---- Профили компаний: «характер» и ожидаемый исход (см. test_data.md) -------------------
C = []

def add(cid, legal_form, year, **kw):
    inn, ogrn = (ip(year) if legal_form == "ИП" else legal(year))
    C.append(dict(id=cid, legal_form=legal_form, inn=inn, ogrn=ogrn, **kw))

add("C1", "ИП", 2024, name="ИП Зернова Анна Сергеевна («Кофейня Зерно»)", short="Кофейня Зерно",
    okved="56.10", registration_date="2024-04-15", status="ACTIVE",
    address="г. Условный, ул. Кофейная, д. 7", director="Зернова Анна Сергеевна",
    bank_client_months=20,
    financials=dict(revenue=18_000_000, revenue_prev_year=17_000_000, monthly_expenses=1_150_000, existing_debt_payments=200_000),
    request=dict(product="EXPRESS", purpose="WORKING_CAPITAL", amount=4_000_000, term=12),
    documents_on_submit=[],  # декларацию НЕ прикладывает → NEEDS_INFO
    anketa_overrides={}, bki=dict(has_history=True, worst_overdue_12m=0, current_overdue_days=0, inquiries_30d=1,
                                   active_loans=1), persons=[{"name": "Зернова Анна Сергеевна", "role": "ИП", "disqualified": False}])

add("C2", "ООО", 2020, name="ООО «ТрансЛогистик»", short="ТрансЛогистик", okved="49.41",
    registration_date="2020-03-02", status="ACTIVE", address="г. Условный, Промзона-3, стр. 1",
    director="Грузов Игорь Павлович", bank_client_months=0,
    financials=dict(revenue=120_000_000, revenue_prev_year=160_000_000, monthly_expenses=5_900_000, existing_debt_payments=4_800_000),
    request=dict(product="EXPRESS", purpose="WORKING_CAPITAL", amount=5_000_000, term=12),
    documents_on_submit=["TAX_RETURN"], anketa_overrides={},
    bki=dict(has_history=True, worst_overdue_12m=45, current_overdue_days=0, inquiries_30d=7, active_loans=5),
    persons=[{"name": "Грузов Игорь Павлович", "role": "Генеральный директор", "disqualified": False}])

add("C3", "ООО", 2021, name="ООО «Мебельная мастерская»", short="Мебельная мастерская", okved="31.01",
    registration_date="2021-02-10", status="ACTIVE", address="г. Условный, ул. Столярная, д. 3",
    director="Дубов Павел Андреевич", bank_client_months=0,
    financials=dict(revenue=45_000_000, revenue_prev_year=36_000_000, monthly_expenses=2_900_000, existing_debt_payments=300_000),
    request=dict(product="INVEST", purpose="EQUIPMENT", amount=12_000_000, term=48),
    documents_on_submit=["FINANCIAL_STATEMENTS", "PURCHASE_CONTRACT"], anketa_overrides={},
    bki=dict(has_history=True, worst_overdue_12m=0, current_overdue_days=0, inquiries_30d=2, active_loans=1),
    persons=[{"name": "Дубов Павел Андреевич", "role": "Генеральный директор", "disqualified": False},
             {"name": "Счётова Марина Игоревна", "role": "Главный бухгалтер", "disqualified": False}])

add("C4", "ИП", 2025, name="ИП Сидоров Олег Викторович («Сидоров. Ремонт»)", short="Сидоров. Ремонт",
    okved="43.39", registration_date="2025-04-20", status="ACTIVE",
    address="г. Условный, ул. Старая, д. 12", director="Сидоров Олег Викторович", bank_client_months=14,
    financials=dict(revenue=8_000_000, revenue_prev_year=7_500_000, monthly_expenses=380_000, existing_debt_payments=220_000),
    request=dict(product="EXPRESS", purpose="WORKING_CAPITAL", amount=1_000_000, term=12),
    documents_on_submit=["TAX_RETURN"], anketa_overrides={"address": "г. Условный, ул. Новая, д. 5"},
    bki=dict(has_history=False, worst_overdue_12m=0, current_overdue_days=0, inquiries_30d=0, active_loans=0),
    persons=[{"name": "Сидоров Олег Викторович", "role": "ИП", "disqualified": False}])

add("C5", "ООО", 2019, name="ООО «Ромашка-Ликвид»", short="Ромашка-Ликвид", okved="47.19",
    registration_date="2019-06-01", status="LIQUIDATED", address="г. Условный, ул. Полевая, д. 1",
    director="Закрытов Иван Ильич", bank_client_months=0,
    financials=dict(revenue=5_000_000, revenue_prev_year=9_000_000, monthly_expenses=400_000, existing_debt_payments=0),
    request=dict(product="EXPRESS", purpose="WORKING_CAPITAL", amount=1_000_000, term=12),
    documents_on_submit=["TAX_RETURN"], anketa_overrides={},
    bki=dict(has_history=True, worst_overdue_12m=0, current_overdue_days=0, inquiries_30d=0, active_loans=0),
    persons=[{"name": "Закрытов Иван Ильич", "role": "Ликвидатор", "disqualified": False}])

add("C6", "ООО", 2022, name="ООО «Сбойный Источник»", short="Сбойный Источник", okved="46.90",
    registration_date="2022-09-05", status="ACTIVE", address="г. Условный, ул. Сетевая, д. 504",
    director="Таймаутов Глеб Олегович", bank_client_months=0,
    financials=dict(revenue=30_000_000, revenue_prev_year=28_000_000, monthly_expenses=1_900_000, existing_debt_payments=250_000),
    request=dict(product="EXPRESS", purpose="WORKING_CAPITAL", amount=2_000_000, term=12),
    documents_on_submit=["TAX_RETURN"], anketa_overrides={},
    bki="TIMEOUT",
    persons=[{"name": "Таймаутов Глеб Олегович", "role": "Генеральный директор", "disqualified": False}])

add("C7", "ООО", 2022, name="ООО «Сезон-Опт»", short="Сезон-Опт", okved="46.39",
    registration_date="2022-05-16", status="ACTIVE", address="г. Условный, Складской пр., д. 9",
    director="Запасов Роман Евгеньевич", bank_client_months=0,
    financials=dict(revenue=72_000_000, revenue_prev_year=66_000_000, monthly_expenses=2_700_000, existing_debt_payments=2_880_000),
    request=dict(product="EXPRESS", purpose="CASH_GAP", amount=5_000_000, term=6),
    documents_on_submit=["TAX_RETURN"], anketa_overrides={},
    bki=dict(has_history=True, worst_overdue_12m=0, current_overdue_days=0, inquiries_30d=2, active_loans=4),
    persons=[{"name": "Запасов Роман Евгеньевич", "role": "Генеральный директор", "disqualified": False}])

USERS = [
    ("anna@demo.local", "CLIENT", "Зернова Анна Сергеевна", [("C1", "owner")], "Главный демо-путь, лента"),
    ("igor@demo.local", "CLIENT", "Грузов Игорь Павлович", [("C2", "ceo")], "Авто-отказ, лента после отказа"),
    ("marina@demo.local", "CLIENT", "Счётова Марина Игоревна", [("C3", "accountant")], "Ручное рассмотрение, роль бухгалтера"),
    ("sidorov@demo.local", "CLIENT", "Сидоров Олег Викторович",
     [("C4", "owner"), ("C5", "authorized"), ("C6", "authorized"), ("C7", "authorized")], "Негативные и пограничные сценарии"),
    ("expert@demo.local", "EXPERT", "Экспертова Вера Николаевна", [], "Очередь и решения"),
    ("admin@demo.local", "ADMIN", "Админов Лев Борисович", [], "Дашборд, аудит, сброс демо"),
]
DEMO_PASSWORD = "Demo2026!"  # демонстрационный; в seed хранится только bcrypt-хэш


def main():
    SEED.mkdir(exist_ok=True)
    companies = []
    registry, bki, tb = {}, {}, {}
    for c in C:
        companies.append({k: c[k] for k in ("id", "inn", "ogrn", "legal_form", "short", "bank_client_months",
                                             "financials", "request", "documents_on_submit", "anketa_overrides")})
        registry[c["inn"]] = {"inn": c["inn"], "ogrn": c["ogrn"], "name": c["name"], "legal_form": c["legal_form"],
                              "okved": c["okved"], "registration_date": c["registration_date"], "status": c["status"],
                              "address": c["address"], "director": c["director"]}
        tb[c["inn"]] = {"inn": c["inn"], "persons": c["persons"], "address": c["address"], "okved": c["okved"]}
        bki[c["inn"]] = {"mode": "TIMEOUT"} if c["bki"] == "TIMEOUT" else {"mode": "OK", **c["bki"]}
    users = []
    for login, role, name, memberships, purpose in USERS:
        users.append({"login": login, "role": role, "full_name": name,
                      "password_hash": bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode(),
                      "memberships": [{"company": cid, "role": r} for cid, r in memberships], "purpose": purpose})
    dump = lambda name, obj: (SEED / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    dump("companies.json", companies)
    dump("mock_registry.json", registry)
    dump("mock_transparent_business.json", tb)
    dump("mock_bki.json", bki)
    dump("users.json", users)
    print("seed written:", [c["id"] + ":" + c["inn"] for c in C])


if __name__ == "__main__":
    main()
