"""Проверка таблицы «шаг демо → лента» (docs/product/news_feed_rules.md, §6).
python3 tools/reference/feed_demo.py  — печатает топ ленты на каждом шаге демо."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import engine as E

ANNA = dict(okved="56.10", revenue=18_000_000, legal_form="ИП", role="owner", risk_class=None)
IGOR = dict(okved="49.41", revenue=120_000_000, legal_form="ООО", role="ceo", risk_class="D")
MARINA = dict(okved="31.01", revenue=45_000_000, legal_form="ООО", role="accountant", risk_class="A")
SIDOROV = dict(okved="43.39", revenue=8_000_000, legal_form="ИП", role="owner", risk_class="C")

STEPS = [
    ("1 Анна, нет заявок", dict(ANNA, application_status=None, product=None)),
    ("2 Анна, SCORING", dict(ANNA, application_status="SCORING", product="EXPRESS", risk_class="B")),
    ("3 Анна, NEEDS_INFO", dict(ANNA, application_status="NEEDS_INFO", product="EXPRESS")),
    ("4 Анна, APPROVED_WITH_CHANGES", dict(ANNA, application_status="APPROVED_WITH_CHANGES", product="EXPRESS", risk_class="B")),
    ("5 Анна, DISBURSED", dict(ANNA, application_status="DISBURSED", product="EXPRESS", risk_class="B")),
    ("6 Игорь, REJECTED", dict(IGOR, application_status="REJECTED", product="EXPRESS")),
    ("доп. Марина, MANUAL_REVIEW", dict(MARINA, application_status="MANUAL_REVIEW", product="INVEST")),
    ("доп. Сидоров, нет заявок", dict(SIDOROV, application_status=None, product=None, risk_class=None)),
]

if __name__ == "__main__":
    for name, ctx in STEPS:
        print(f"\n== {name}")
        for i, c in enumerate(E.feed(ctx), 1):
            print(f"  {i}. [{c['type']}{'📌' if c['pinned'] else ''}] {c['title']}  (score {c['score']}) — {c['reason']}")
