"""Pure, deterministic teaching simulator engine; no official AmplifyME scoring claims."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from importlib.resources import files
from typing import Any

VERSION = "1.0.0"
RULESET = "teammate-scenarios-1"
ASSETS = ("科技股", "医药股", "政府债券", "企业债券", "现金")
INITIAL_NAV_CENTS = 100_000_000  # ¥1,000,000.00
MAX_ROUNDS = 5
TEN_THOUSAND_IN_CENTS = 1_000_000
D = Decimal


def scenarios() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(files("wealthathon").joinpath("scenarios.json").read_text("utf-8")))


SCENARIOS = scenarios()
BY_ID = {s["id"]: s for s in SCENARIOS}
assert len(BY_ID) == len(SCENARIOS)
assert all(set(s["returns"]) == set(ASSETS) for s in SCENARIOS)


def choose_scenario(seed: int, round_no: int) -> dict[str, Any]:
    if not isinstance(seed, int) or seed < 0 or not 1 <= round_no <= MAX_ROUNDS:
        raise ValueError("随机种子或轮次无效")
    fingerprint = hashlib.sha256(f"wealthathon-v1:{seed}:{round_no}".encode()).digest()
    idx = int.from_bytes(fingerprint[:8], "big") % len(SCENARIOS)
    return SCENARIOS[idx]


def parse_wan(text: str) -> int:
    """Parse up to 6 decimal places of 万元 exactly into integer fen (cents)."""
    text = text.strip()
    if not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,6})?", text):
        raise ValueError("金额须为非负数字，万元单位最多保留6位小数")
    cents = D(text) * TEN_THOUSAND_IN_CENTS
    if cents > 9_000_000_000_000:
        raise ValueError("金额超出允许范围")
    return int(cents)


def format_wan(cents: int) -> str:
    if not isinstance(cents, int):
        raise TypeError("金额必须为整数分")
    return f"{D(cents) / TEN_THOUSAND_IN_CENTS:.6f}"


def even_allocation(nav_cents: int) -> dict[str, int]:
    if nav_cents < 0:
        raise ValueError("净值不可为负")
    share, remainder = divmod(nav_cents, len(ASSETS))
    return {asset: share + (1 if i < remainder else 0) for i, asset in enumerate(ASSETS)}


def validate_allocation(alloc: dict[str, int], nav_cents: int) -> None:
    if not isinstance(alloc, dict) or set(alloc) != set(ASSETS):
        raise ValueError("资产项目不完整")
    if not isinstance(nav_cents, int) or nav_cents <= 0:
        raise ValueError("当前资金无效")
    if any(type(v) is not int or v < 0 for v in alloc.values()):
        raise ValueError("资产金额必须是非负整数分")
    if sum(alloc.values()) != nav_cents:
        delta = sum(alloc.values()) - nav_cents
        raise ValueError(f"配置总额必须恰好等于当前净值（相差 {delta / 100:+.2f} 元）")


def clamp(n: Decimal, lo: Decimal = D(0), hi: Decimal = D(100)) -> Decimal:
    return max(lo, min(hi, n))


def round_payload(
    allocation: dict[str, int],
    scenario: dict[str, Any],
    start_nav_cents: int,
    previous_peak_cents: int,
    previous_max_drawdown_pct: str | Decimal,
) -> dict[str, Any]:
    """Calculate all outputs using integer cents and Decimal; caller persists atomically."""
    validate_allocation(allocation, start_nav_cents)
    if not scenario or set(scenario.get("returns", {})) != set(ASSETS):
        raise ValueError("市场情景无效")
    if previous_peak_cents < start_nav_cents or previous_peak_cents <= 0:
        raise ValueError("历史净值峰值不一致")
    returns = {asset: D(str(scenario["returns"][asset])) for asset in ASSETS}
    if any(not r.is_finite() or r < D(-1) for r in returns.values()):
        raise ValueError("资产收益率无效")

    pnl_by_asset = {
        a: int((D(allocation[a]) * returns[a]).quantize(D(1), rounding=ROUND_HALF_UP))
        for a in ASSETS
    }
    end_holdings = {a: allocation[a] + pnl_by_asset[a] for a in ASSETS}
    pnl_cents = sum(pnl_by_asset.values())
    end_nav = start_nav_cents + pnl_cents
    if end_nav <= 0 or end_nav != sum(end_holdings.values()):
        raise ValueError("结算后净值无效")
    peak = max(previous_peak_cents, end_nav)
    dd_pct = (D(peak - end_nav) / D(peak) * D(100))
    max_dd_pct = max(D(previous_max_drawdown_pct), dd_pct)
    round_return_pct = D(pnl_cents) / D(start_nav_cents) * D(100)
    eq = D(allocation["科技股"] + allocation["医药股"]) / D(start_nav_cents)
    corp = D(allocation["企业债券"]) / D(start_nav_cents)
    cash = D(allocation["现金"]) / D(start_nav_cents)
    concentration = D(max(allocation.values())) / D(start_nav_cents)
    risk_score = clamp(D(100) - D(35) * eq - D(25) * corp + D(15) * cash - D(70) * max(D(0), concentration - D("0.35")))
    discipline_score = clamp(D(100) - (D(15) if concentration > D("0.5") else D(0)) - (D(10) if cash < D("0.05") else D(0)))
    performance_score = clamp(D(50) + D(pnl_cents) / D(start_nav_cents) * D(300))
    score = int((D("0.4") * risk_score + D("0.35") * discipline_score + D("0.25") * performance_score).quantize(D(1), rounding=ROUND_HALF_EVEN))
    notes = []
    if returns["企业债券"] <= D("-0.05") and corp > D("0.15"):
        notes.append("企业债冲击较大，复核企业债仓位与信用风险。")
    if returns["政府债券"] < 0 and D(allocation["政府债券"]) / D(start_nav_cents) > D("0.25"):
        notes.append("政府债券也可能因利率上行而下跌。")
    if eq > D("0.6") and min(returns["科技股"], returns["医药股"]) < D("-0.04"):
        notes.append("股票仓位较高，检查行业集中度和相关性。")
    if cash < D("0.05"):
        notes.append("现金比例较低，留意流动性缓冲。")
    if not notes:
        notes.append("核对事前预期与实际收益来源，并复核资产集中度。")
    pct = lambda x: f"{x.quantize(D('0.000001'), rounding=ROUND_HALF_UP):.6f}"
    return {
        "start_nav_cents": start_nav_cents,
        "end_nav_cents": end_nav,
        "pnl_cents": pnl_cents,
        "peak_cents": peak,
        "return_pct": pct(round_return_pct),
        "drawdown_pct": pct(dd_pct),
        "max_drawdown_pct": pct(max_dd_pct),
        "risk_score": pct(risk_score),
        "discipline_score": pct(discipline_score),
        "performance_score": pct(performance_score),
        "score": score,
        "allocation": dict(allocation),
        "asset_pnl": pnl_by_asset,
        "end_holdings": end_holdings,
        "notes": notes,
    }


def allocation_risk(alloc: dict[str, int], nav_cents: int) -> list[str]:
    if nav_cents <= 0 or set(alloc) != set(ASSETS):
        return ["请先输入有效配置"]
    q = lambda x: f"{D(x) / D(nav_cents) * 100:.1f}%"
    eq = alloc["科技股"] + alloc["医药股"]
    bond = alloc["政府债券"] + alloc["企业债券"]
    cash = alloc["现金"]
    concentration = max(alloc.values())
    result = [f"股票：{q(eq)}    债券：{q(bond)}    现金：{q(cash)}", f"最大单项持仓：{q(concentration)}"]
    if D(eq) / nav_cents > D("0.65"):
        result.append("注意：股票占比高于 65%。")
    if D(alloc["企业债券"]) / nav_cents > D("0.25"):
        result.append("注意：企业债占比高于 25%。")
    if D(cash) / nav_cents < D("0.05"):
        result.append("注意：现金比例低于 5%。")
    if D(concentration) / nav_cents > D("0.5"):
        result.append("注意：单项持仓超过 50%。")
    return result
