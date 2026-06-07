import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from tradingagents.dataflows.screener import fetch_screener_data

data = fetch_screener_data("DATAPATTNS.NS")
if data:
    print("\n" + "="*60)
    print(data[:30000])  # print first 3000 chars to verify
    print("="*60)
    print(f"\nTotal chars: {len(data)}")
else:
    print("FAILED: No data returned")
