import asyncio
import aiohttp
import json
import time
from urllib.parse import quote
from ema_crossover import get_instrument_name


# pip install aiohttp
# python fetch_candles.py


# ─── CONFIG ──────────────────────────────────────────────────────────────────

with open("all_instrument_keys.json", "r") as _f:
    INSTRUMENT_KEYS: list[str] = json.load(_f)

  
INTERVAL = "I60"          # e.g. I1, I5, I15, I30, I60, D1
FROM_TS  = 1780511399999  # epoch ms
LIMIT    = 250

# ─── HEADERS (copy your exact browser headers) ───────────────────────────────

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-GB,en;q=0.9",
    "origin": "https://tv.upstox.com",
    "priority": "u=1, i",
    "referer": "https://tv.upstox.com/",
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "x-request-id": "WPRO-5B2rVR2MX5gh2wbqNG6KC",
    # ⚠️  Update these cookies before running – they expire
    "Cookie": (
        "__cf_bm=iBYEi5iE8j49UCyUf90eTKGgSDjaYcioOCnZ0HZOcQE-1780471562.5917478-1.0.1.1-P4RO72jh0Cos2URBWTpj6VLdjxDO1jUVSRyykznHtAHHQHHbCswL.sSl0QQTI12VbL.fnsRtlZgPgbNFZFF.C81gG4TQsM2KRTJOQjEcIrbgx70BtjssKEVszIW4i685; "
        "_cfuvid=ZFj1rFABposfJGs.lLaVfVIRIouPsmUl1bAHT3g5D7s-1780433735.5982654-1.0.1.1-zhDW3j.k3XJ7aRI8_r_JfwgiTXVcL4bGkI7ke7Zlvqk"
    ),
}

BASE_URL = "https://service.upstox.com/chart/open/v3/candles"

# ─── FETCH ────────────────────────────────────────────────────────────────────

async def fetch_one(session: aiohttp.ClientSession, instrument_key: str) -> tuple[str, dict]:
    encoded_key = quote(instrument_key, safe="")
    url = f"{BASE_URL}?instrumentKey={encoded_key}&interval={INTERVAL}&from={FROM_TS}&limit={LIMIT}"

    wait = 30  # initial backoff in seconds
    for attempt in range(6):
        try:
            async with session.get(url, headers=HEADERS, ssl=False) as resp:
                data = await resp.json(content_type=None)
                if data is None:
                    return instrument_key, {"error": f"null response (HTTP {resp.status})"}
                # Rate limited → wait and retry
                if isinstance(data, dict) and data.get("error_code") == 1015:
                    print(f"  [rate-limited] {instrument_key} → waiting {wait}s (attempt {attempt+1})")
                    await asyncio.sleep(wait)
                    wait = min(wait * 2, 300)  # cap at 5 min
                    continue
                return instrument_key, data
        except Exception as e:
            return instrument_key, {"error": str(e)}
    return instrument_key, {"error": "rate-limited after 6 retries"}


async def fetch_all(instrument_keys: list[str]) -> dict:
    connector = aiohttp.TCPConnector(limit=3)  # reduced to avoid rate limit
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_one(session, key) for key in instrument_keys]
        results = await asyncio.gather(*tasks)

    return {key: response for key, response in results}


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_time = time.time()
    print(f"Fetching candles for {len(INSTRUMENT_KEYS)} instruments  [interval={INTERVAL}, from={FROM_TS}]")
    result: dict = asyncio.run(fetch_all(INSTRUMENT_KEYS))
    
    end_time = time.time()
    print("final time ", end_time - start_time)
    # Pretty-print summary
    for key, resp in result.items():
        if not isinstance(resp, dict):
            print(f"  {key:<45}  candles=-  ERROR: unexpected response type ({type(resp)})")
            continue
        status = "OK" if "error" not in resp else f"ERROR: {resp['error']}"
        candles = len(resp.get("data", {}).get("candles", [])) if "data" in resp else "-"
        # print(f"  {key:<45}  candles={candles}  {status}")

    # Save to file (only if candles length is greater than 0)
    filtered_result = {}
    no_candle = []
    for key, resp in result.items():
      if isinstance(resp, dict) and len(resp.get("data", {}).get("candles", [])) > 0:
        filtered_result[key] = resp
      else:
        no_candle.append(get_instrument_name(key))
    print("no_candle", no_candle)

    out_file = "candles_result.json"
    with open(out_file, "w") as f:
        json.dump(filtered_result, f, indent=2)

    print(f"\nSaved → {out_file} (saved {len(filtered_result)} of {len(result)} instruments)")
