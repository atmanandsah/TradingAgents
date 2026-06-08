import logging
import sys
import json
import urllib.request
import urllib.error

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from tradingagents.dataflows.screener import fetch_screener_data

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
TEXT_MODEL = "minimax-m3:cloud"

def analyze_financials(screener_text: str) -> str:
    user_message = f"""SCREENER DATA:
{screener_text}

---
ROLE:
You are a senior equity research analyst specialized in Indian listed companies.

TASK:
Analyze the provided screener data and produce a structured investment-quality summary using exactly this format.

OUTPUT FORMAT:
# [COMPANY NAME]

## 1. FINANCIAL PERFORMANCE
- **Revenue (Top Line):** Latest year figure + YoY growth %
- **Net Profit / PAT:** Latest figure + YoY growth %
- **Operating Profit & OPM%:** Latest OPM%. Expanding or contracting?
- **Trend:** 3-year revenue direction (growing/flat/declining)

Do not include any extra text. Output ONLY the requested format.
"""

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a senior equity research analyst. Answer strictly in the requested format."},
            {"role": "user", "content": user_message}
        ],
        "options": {"temperature": 0},
        "stream": True
    }

    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"\nAnalyzing with {TEXT_MODEL}...\n", flush=True)
    tokens = []
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            for line in response:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("message", {}).get("content", "")
                print(token, end="", flush=True)
                tokens.append(token)
                if chunk.get("done", False):
                    break
        print()
        return "".join(tokens)
    except urllib.error.HTTPError as e:
        print(f"\nERROR: HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\nERROR: Ollama not reachable: {e}")
        sys.exit(1)

def main():
    ticker = "DATAPATTNS.NS"
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
        
    data = fetch_screener_data(ticker)
    if data:
        analyze_financials(data)
    else:
        print("FAILED: No data returned")

if __name__ == "__main__":
    main()
