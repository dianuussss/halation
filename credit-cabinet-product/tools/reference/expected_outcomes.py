"""Пересчёт ожидаемых исходов для seed-компаний (самопроверка PM, разд. 15 ТЗ).

python3 tools/reference/expected_outcomes.py [--as-of 2026-10-24] [--json]
Результат сверяется с таблицей в docs/testing/test_data.md; dev использует тот же
вывод (--json) как эталон в автотесте сервиса скоринга.
"""
import argparse, datetime as dt, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import engine as E

S = E.ROOT / "seed"


def load():
    comp = json.loads((S / "companies.json").read_text())
    reg = json.loads((S / "mock_registry.json").read_text())
    tb = json.loads((S / "mock_transparent_business.json").read_text())
    bki = json.loads((S / "mock_bki.json").read_text())
    return comp, reg, tb, bki


def run(as_of):
    comp, reg, tb, bki = load()
    rows = []
    for c in comp:
        r = reg.get(c["inn"])
        b = bki.get(c["inn"])
        b = None if (b is None or b["mode"] != "OK") else b
        app = dict(financials=c["financials"], request=c["request"], bank_client_months=c["bank_client_months"],
                   anketa={**{k: r[k] for k in ("name", "address", "okved", "director")}, **c["anketa_overrides"]} if r else {})
        res = E.decide(app, r, tb.get(c["inn"]), b, as_of)
        rows.append((c["id"], res))
        if c["id"] == "C1":   # E2E-09: авто-одобрение «как есть» (T12)
            app9 = dict(app, request={**c["request"], "amount": 3_000_000})
            rows.append(("C1 (3 млн, E2E-09)", E.decide(app9, r, tb.get(c["inn"]), b, as_of)))
        if c["id"] == "C4":   # после ответа на запрос эксперта: адрес подтверждён по реестру
            app2 = dict(app, anketa={**app["anketa"], "address": r["address"]})
            rows.append(("C4 (повторный скоринг)", E.decide(app2, r, tb.get(c["inn"]), b, as_of)))
    return rows


def fmt(rows):
    for cid, r in rows:
        sr = r.get("scoring")
        line = f"{cid:24} "
        if sr:
            pts = " ".join(f"{f['code']}={f['points']:+d}" for f in sr["factors"] if f["points"])
            line += f"score={sr['score']} class={sr['riskClass']} load={sr['debtLoad']:.1%} | {pts}\n{'':25}"
        line += f"→ {r['outcome']} ({r.get('transition')}) reason={r.get('reason')} step={r.get('step')}"
        off = r.get("offer") or r.get("recommendedOffer")
        if off:
            line += (f"\n{'':25}offer: {off['productCode']} {off['amount']:,} ₽ / {off['termMonths']} мес @ {off['rate']}% "
                     f"PMT={off['monthlyPayment']:,} overpay={off['totalOverpayment']:,} change={off['changes']} "
                     f"load_after={off['debtLoadAfter']:.1%}")
        if sr:
            line += f"\n{'':25}client top-3: {E.top_client_factors(sr)}"
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-10-24")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = run(dt.date.fromisoformat(a.as_of))
    if a.json:
        print(json.dumps({k: v for k, v in rows}, ensure_ascii=False, indent=1, default=str))
    else:
        fmt(rows)
