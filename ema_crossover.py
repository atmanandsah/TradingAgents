# -*- coding: utf-8 -*-
import json
import os

# ─── INSTRUMENT LOOKUP ───────────────────────────────────────────────────────

_UNIVERSE_MAP: dict[str, str] = {}

def _load_universe() -> None:
    global _UNIVERSE_MAP
    if _UNIVERSE_MAP:
        return
    universe_path = os.path.join(os.path.dirname(__file__), "venv", "Upstock_universe.json")
    with open(universe_path, "r") as f:
        data = json.load(f)
    for item in data:
        key = item.get("instrument_key")
        name = item.get("name") or item.get("trading_symbol", "")
        if key:
            _UNIVERSE_MAP[key] = name


def get_instrument_name(instrument_key: str) -> str:
    """Convert e.g. 'NSE_EQ|INE0J1E01027' → stock name."""
    _load_universe()
    return _UNIVERSE_MAP.get(instrument_key, instrument_key)


# ─── EMA CALCULATION ──────────────────────────────────────────────────────────

def compute_ema(closes: list[float], period: int) -> list[float]:
    """Compute EMA for a list of close prices (oldest → newest)."""
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]  # seed with SMA
    for price in closes[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def detect_crossover(closes: list[float]) -> str | None:
    """
    Returns:
      'bullish'  → EMA10 just crossed ABOVE EMA20 (latest candle)
      'bearish'  → EMA10 just crossed BELOW EMA20 (latest candle)
      None       → no crossover on latest candle
    """
    if len(closes) < 21:
        return None

    ema10 = compute_ema(closes, 10)
    ema20 = compute_ema(closes, 20)

    # align: ema20 starts at index 19, ema10 starts at index 9
    # offset so both lists align to the same candle
    offset = 10  # ema10 has 10 more values than ema20
    if len(ema10) < offset + 2 or len(ema20) < 2:
        return None

    # latest and previous values (aligned)
    prev_e10 = ema10[-(2)]
    prev_e20 = ema20[-(2)]
    curr_e10 = ema10[-1]
    curr_e20 = ema20[-1]

    if prev_e10 <= prev_e20 and curr_e10 > curr_e20:
        return "bullish"
    elif prev_e10 >= prev_e20 and curr_e10 < curr_e20:
        return "bearish"
    return None


def get_ema_status(closes: list[float]) -> dict:
    """Get current EMA values and relationship."""
    if len(closes) < 20:
        return {"ema10": None, "ema20": None, "position": "insufficient data"}
    ema10 = compute_ema(closes, 10)
    ema20 = compute_ema(closes, 20)
    return {
        "ema10": round(ema10[-1], 2),
        "ema20": round(ema20[-1], 2),
        "position": "above" if ema10[-1] > ema20[-1] else "below",
    }


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with open("candles_result.json") as f:
        data = json.load(f)

    bullish = []
    bearish = []
    ema10_above = []  # EMA10 > EMA20 but no fresh crossover
    ema10_below = []  # EMA10 < EMA20 but no fresh crossover
    skipped = []

    for key, resp in data.items():
        candles = resp.get("data", {}).get("candles", [])
        if not candles:
            skipped.append(key)
            continue

        # candles are newest-first → reverse for chronological order
        candles.reverse()
        closes = [c[4] for c in candles]  # index 4 = close price

        status = get_ema_status(closes)
        signal = detect_crossover(closes)
        last_close = closes[-1]

        entry = {
            "key": key,
            "close": last_close,
            "ema10": status["ema10"],
            "ema20": status["ema20"],
        }

        if signal == "bullish":
            bullish.append(entry)
        elif signal == "bearish":
            bearish.append(entry)
        elif status["position"] == "above":
            ema10_above.append(entry)
        elif status["position"] == "below":
            ema10_below.append(entry)

    # ─── PRINT RESULTS ───────────────────────────────────────────────────────

    def print_list(title, items, emoji):
        print(f"\n{'='*70}")
        print(f"  {emoji}  {title}  ({len(items)} stocks)")
        print(f"{'='*70}")
        if not items:
            print("  (none)")
        for i in items:
            diff = round(i["ema10"] - i["ema20"], 2)
            print(f"  {i['key']:<45} {get_instrument_name(i['key'])} close={i['close']:<10}  EMA10={i['ema10']}  EMA20={i['ema20']}  diff={diff}")

    print_list("BULLISH CROSSOVER (EMA10 crossed ABOVE EMA20)", bullish, "🟢")
    print_list("BEARISH CROSSOVER (EMA10 crossed BELOW EMA20)", bearish, "🔴")
    print_list("EMA10 > EMA20 (already bullish, no fresh cross)", ema10_above, "🔵")
    print_list("EMA10 < EMA20 (already bearish, no fresh cross)", ema10_below, "🟠")

    if skipped:
        print(f"\n⚠️  Skipped (no candle data): {len(skipped)} instruments")
