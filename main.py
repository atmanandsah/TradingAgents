import logging

# Enable INFO-level logs to appear in the terminal
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# DEFAULT_CONFIG already applies TRADINGAGENTS_* env-var overrides
# (llm_provider, deep_think_llm, quick_think_llm, backend_url, etc.),
# so users can switch models or endpoints purely via .env without
# editing this script. Override individual keys here only when you
# want a hard-coded value that should ignore the environment.
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "llama3.1"
config["quick_think_llm"] = "llama3.1"
config["analysts_only"] = True

# Initialize with custom config
ta = TradingAgentsGraph(selected_analysts=["social"], debug=True, config=config)

# User-specified Stocks of Indian Market (NSE)
indian_stocks = [
    "DATAPATTNS.NS",
    "AXISCADES.NS",
    "BEL.NS",
    "HAL.NS",
    "BHARATFORG.NS",
    "BDL.NS",
    "MTARTECH.NS",
    "GRSE.NS"
]

import datetime
today_date = datetime.datetime.now().strftime("%Y-%m-%d")

for stock in indian_stocks:
    print(f"\n--- Scanning {stock} for {today_date} ---")
    try:
        _, decision = ta.propagate(stock, today_date)
        print(f"Decision for {stock}:")
        print(decision)
    except Exception as e:
        print(f"Error scanning {stock}: {e}")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
