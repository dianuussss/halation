"""Эталонная (reference) реализация скоринга, кредитной политики и ранжирования ленты.

Назначение — оракул для автотестов и проверки seed: по нему посчитаны все ожидаемые
баллы и исходы в docs/. Это НЕ продакшн-код: dev реализует ту же логику в сервисе,
а тест `expected_outcomes` сравнивает результаты сервиса с этим модулем.
Источник правил: config/scoring_rules.yaml, config/products.yaml, config/feed_rules.yaml.
"""
from __future__ import annotations
import datetime as dt, json, math, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
RULES = yaml.safe_load((ROOT / "config/scoring_rules.yaml").read_text())
PRODUCTS = {p["code"]: p for p in yaml.safe_load((ROOT / "config/products.yaml").read_text())["products"]}
POLICY = RULES["policy"]
FACTORS = {f["code"]: f for f in RULES["scorecard"]["factors"]}


# ---------------------------------------------------------------- платежи и нагрузка
def annuity(amount: float, rate_pct: float, months: int) -> float:
    r = rate_pct / 100 / 12
    return amount * r / (1 - (1 + r) ** -months)


def monthly_payment(product: str, amount: float, rate_pct: float, months: int) -> float:
    if PRODUCTS[product]["payment_model"] == "INTEREST_ONLY":
        return amount * rate_pct / 100 / 12          # [ДОПУЩЕНИЕ] проценты на весь лимит
    return annuity(amount, rate_pct, months)


def debt_load(fin: dict, product: str, amount: float, rate: float, months: int) -> float:
    return (fin["existing_debt_payments"] + monthly_payment(product, amount, rate, months)) / (fin["revenue"] / 12)


def class_rate(product: str, risk_class: str) -> float:
    return PRODUCTS[product]["base_rate"] + RULES["rate_markup_pp"].get(risk_class, 0)


# ---------------------------------------------------------------- скоринг
def _band(code: str, idx: int):
    b = FACTORS[code]["bands"][idx]
    return b["points"], b["client"], b["expert"]


def _okved_in(okved: str, prefixes) -> bool:
    return any(okved == p or okved.startswith(p) for p in prefixes)


def stop_factors(reg: dict, tb: dict, bki: dict, as_of: dt.date) -> list[str]:
    sf = []
    if reg["status"] in ("LIQUIDATING", "LIQUIDATED", "BANKRUPTCY"):
        sf.append("SF-01")
    if bki and bki.get("current_overdue_days", 0) > 90:
        sf.append("SF-02")
    if _age_months(reg["registration_date"], as_of) < 3:
        sf.append("SF-03")
    if tb and any(p.get("disqualified") for p in tb.get("persons", [])):
        sf.append("SF-04")
    return sf


def _age_months(date_str: str, as_of: dt.date) -> int:
    d = dt.date.fromisoformat(date_str)
    return (as_of.year - d.year) * 12 + as_of.month - d.month - (1 if as_of.day < d.day else 0)


def score(app: dict, reg: dict, bki: dict, as_of: dt.date) -> dict:
    """app: {financials, request{product,amount,term}, anketa{...}, bank_client_months}"""
    fin, req = app["financials"], app["request"]
    factors = []

    def add(code, idx, value):
        pts, client, expert = _band(code, idx)
        factors.append(dict(code=code, value=value, points=pts, clientText=client, expertText=expert))

    age_y = _age_months(reg["registration_date"], as_of) / 12
    add("AGE", 0 if age_y < 1 else (1 if age_y <= 3 else 2), round(age_y, 1))
    rev = fin["revenue"]
    add("REVENUE", 0 if rev < 10e6 else (1 if rev <= 60e6 else 2), rev)
    trend = (rev - fin["revenue_prev_year"]) / fin["revenue_prev_year"]
    add("REVENUE_TREND", 0 if trend < -0.2 else (1 if trend <= 0.2 else 2), round(trend, 3))
    load = debt_load(fin, req["product"], req["amount"], PRODUCTS[req["product"]]["base_rate"], req["term"])
    add("DEBT_LOAD", 0 if load > 0.5 else (1 if load >= 0.3 else 2), round(load, 3))
    if not bki["has_history"]:
        add("CREDIT_HISTORY", 0, "no_history")
    elif bki["worst_overdue_12m"] >= 30:
        add("CREDIT_HISTORY", 1, bki["worst_overdue_12m"])
    elif bki["worst_overdue_12m"] >= 1:
        add("CREDIT_HISTORY", 2, bki["worst_overdue_12m"])
    else:
        add("CREDIT_HISTORY", 3, 0)
    add("BKI_INQUIRIES", 0 if bki["inquiries_30d"] > 5 else 1, bki["inquiries_30d"])
    ind = FACTORS["INDUSTRY"]
    okv = reg["okved"]
    add("INDUSTRY", 0 if _okved_in(okv, ind["high_risk_okved_prefixes"]) else
        (2 if _okved_in(okv, ind["low_risk_okved_prefixes"]) else 1), okv)
    anketa = app.get("anketa", {})
    diffs = [f for f in FACTORS["DISCREPANCY"]["compared_fields"] if f in anketa and anketa[f] != reg.get(f)]
    add("DISCREPANCY", 0 if diffs else 1, diffs)
    add("BANK_CLIENT", 0 if app.get("bank_client_months", 0) > 6 else 1, app.get("bank_client_months", 0))

    total = RULES["scorecard"]["base"] + sum(f["points"] for f in factors)
    rc = next(k for k, v in sorted(RULES["risk_classes"].items(), key=lambda kv: -kv[1]) if total >= v)
    return dict(score=total, riskClass=rc, rulesVersion=RULES["rules_version"], factors=factors, debtLoad=load)


def top_client_factors(sr: dict, n: int = 3, negative_first: bool = True) -> list[str]:
    fs = [f for f in sr["factors"] if f["clientText"] and f["points"] != 0]
    fs.sort(key=lambda f: (f["points"] if negative_first else -abs(f["points"])))
    return [("−" if f["points"] < 0 else "+") + " " + f["clientText"] for f in fs[:n]]


# ---------------------------------------------------------------- кредитная политика
def _round_down(x: float) -> int:
    step = POLICY["rounding_step"]
    return int(x // step * step)


def _max_amount(fin, product, rate, months) -> int:
    allowance = POLICY["max_debt_load"] * fin["revenue"] / 12 - fin["existing_debt_payments"]
    if allowance <= 0:
        return 0
    one = monthly_payment(product, 1.0, rate, months)
    return _round_down(allowance / one)


def _offer(product, amount, term, rc, change, changes, fin):
    rate = class_rate(product, rc)
    pmt = monthly_payment(product, amount, rate, term)
    over = (pmt * term - amount) if PRODUCTS[product]["payment_model"] == "ANNUITY" else pmt * term
    return dict(productCode=product, amount=int(amount), termMonths=term, rate=rate,
                monthlyPayment=round(pmt), totalOverpayment=round(over), changeType=change, changes=changes,
                debtLoadAfter=round(debt_load(fin, product, amount, rate, term), 3))


def counter_offer(fin: dict, req: dict, rc: str, cap: int | None) -> tuple[str, dict | None, str]:
    """Возвращает (outcome, offer, step) по шагам policy.counter_offer_steps."""
    p, amt, term = req["product"], req["amount"], req["term"]
    prod = PRODUCTS[p]
    rate = class_rate(p, rc)
    cand = min(amt, cap or prod["max_amount"], prod["max_amount"])
    capped = cand < amt
    lim = POLICY["max_debt_load"]
    # FIT_AS_IS
    if debt_load(fin, p, cand, rate, term) <= lim:
        if capped:
            return "APPROVED_WITH_CHANGES", _offer(p, cand, term, rc, "AMOUNT", ["AMOUNT"], fin), "CAP_BY_CLASS"
        return "APPROVED", _offer(p, cand, term, rc, "NONE", [], fin), "FIT_AS_IS"
    # EXTEND_TERM
    if prod["payment_model"] == "ANNUITY":
        for t in range(term + 1, prod["max_term"] + 1):
            if debt_load(fin, p, cand, rate, t) <= lim:
                ch = ["AMOUNT", "TERM"] if capped else ["TERM"]
                return "APPROVED_WITH_CHANGES", _offer(p, cand, t, rc, ch[0], ch, fin), "EXTEND_TERM"
    # ALTERNATIVE_PRODUCT
    for alt in prod["alternatives"]:
        ap = PRODUCTS[alt]
        m = POLICY["matrix"][alt][rc]
        if m["route"] != "AUTO":
            continue
        a_amt = min(amt, m.get("cap", ap["max_amount"]), ap["max_amount"])
        a_term = max(ap["min_term"], min(term, ap["max_term"]))
        if a_amt >= ap["min_amount"] and debt_load(fin, alt, a_amt, class_rate(alt, rc), a_term) <= lim:
            return "APPROVED_WITH_CHANGES", _offer(alt, a_amt, a_term, rc, "PRODUCT", ["PRODUCT"], fin), "ALTERNATIVE_PRODUCT"
    # REDUCE_AMOUNT
    mx = min(_max_amount(fin, p, rate, prod["max_term"]), cand)
    if mx >= prod["min_amount"]:
        ch = ["AMOUNT"] + (["TERM"] if prod["max_term"] != term else [])
        return "APPROVED_WITH_CHANGES", _offer(p, mx, prod["max_term"], rc, "AMOUNT", ch, fin), "REDUCE_AMOUNT"
    return "REJECTED", None, "REJECT:DEBT_LOAD"


def decide(app: dict, reg: dict, tb: dict | None, bki: dict | None, as_of: dt.date) -> dict:
    """Полный автоматический проход: ENRICHING → SCORING → DECISION_PENDING."""
    if reg is None:
        return dict(path="lookup NOT_FOUND → ручной ввод, обогащение неполное → MANUAL_REVIEW", outcome="MANUAL_REVIEW")
    sf = stop_factors(reg, tb, bki if isinstance(bki, dict) else None, as_of)
    if "SF-01" in sf or "SF-03" in sf or "SF-04" in sf:
        return dict(outcome="REJECTED", reason="REGISTRY_STOP", stopFactors=sf, transition="T9 ENRICHING→REJECTED")
    if bki is None:   # источник недоступен после ретраев
        return dict(outcome="MANUAL_REVIEW", reason="INCOMPLETE_DATA", transition="T10 ENRICHING→MANUAL_REVIEW")
    sr = score(app, reg, bki, as_of)
    req = app["request"]
    if "SF-02" in sf:
        return dict(outcome="REJECTED", reason="STOP_FACTOR", stopFactors=sf, scoring=sr, transition="T15")
    m = POLICY["matrix"][req["product"]][sr["riskClass"]]
    res = dict(scoring=sr)
    if m["route"] == "REJECT":
        res.update(outcome="REJECTED", reason="RISK_CLASS_D", transition="T15")
    elif m["route"] == "MANUAL":
        o, off, step = counter_offer(app["financials"], req, sr["riskClass"], None)
        res.update(outcome="MANUAL_REVIEW", reason=m.get("reason", "GREY_ZONE"), transition="T14",
                   recommendedOffer=off, recommendedOutcome=o)
    else:
        o, off, step = counter_offer(app["financials"], req, sr["riskClass"], m.get("cap"))
        res.update(outcome=o, offer=off, step=step,
                   transition={"APPROVED": "T12", "APPROVED_WITH_CHANGES": "T13", "REJECTED": "T15"}[o],
                   reason=None if o != "REJECTED" else "DEBT_LOAD")
    return res


# ---------------------------------------------------------------- лента
FEED = yaml.safe_load((ROOT / "config/feed_rules.yaml").read_text()) if (ROOT / "config/feed_rules.yaml").exists() else None


def _matches(aud: dict, ctx: dict) -> bool:
    for k, v in (aud or {}).items():
        if k == "no_application":
            if v != (ctx.get("application_status") is None):
                return False
        elif k == "okved_prefix":
            if not any(ctx.get("okved", "").startswith(x) for x in v):
                return False
        elif k == "revenue_lt":
            if not ctx.get("revenue") or ctx["revenue"] >= v:
                return False
        elif k == "exclude_risk_class":
            if ctx.get("risk_class") in v:
                return False
        elif k == "exclude_product":
            if ctx.get("product") in v:
                return False
        else:   # application_status, product, decision_outcome, role, legal_form
            if ctx.get(k) not in v:
                return False
    return True


def feed(ctx: dict, seen: set = frozenset(), limit: int | None = None) -> list[dict]:
    cfg = FEED
    pr = cfg["ranking"]["type_priority"]
    out = []
    for card in cfg["cards"]:
        if not _matches(card.get("audience", {}), ctx):
            continue
        aud = card.get("audience", {})
        s = pr[card["type"]] + card.get("priority_boost", 0)
        if "application_status" in aud or "decision_outcome" in aud:
            s += cfg["ranking"]["stage_match"]
        if "okved_prefix" in aud:
            s += cfg["ranking"]["industry_match"]
        s -= card.get("age_days", 0) * cfg["ranking"]["freshness_per_day"]
        if card["id"] in seen:
            s -= cfg["ranking"]["already_seen"]
        out.append(dict(id=card["id"], type=card["type"], title=card["title"], score=s,
                        pinned=card["type"] == "ACTION", reason=card["reason"]))
    out.sort(key=lambda c: (not c["pinned"], -c["score"], c["id"]))
    # не более N карточек одного типа подряд (кроме закреплённых сверху)
    mx = cfg["ranking"]["max_same_type_in_row"]
    res, pool = [], out[:]
    while pool:
        for i, c in enumerate(pool):
            run = res[-mx:]
            if c["pinned"] or len(run) < mx or any(x["type"] != c["type"] for x in run):
                res.append(pool.pop(i))
                break
        else:
            res.append(pool.pop(0))
    return res[: (limit or cfg["ranking"]["max_cards"])]


if __name__ == "__main__":
    print(json.dumps(RULES["rules_version"]))
