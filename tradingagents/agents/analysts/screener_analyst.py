"""Screener.in Fundamentals Analyst — vision-based P&L analysis.

This analyst:
1. Navigates to screener.in for the given ticker (via Playwright CDP).
2. Takes a screenshot of the Profit & Loss section.
3. Passes the screenshot to llama3.2-vision (via Ollama) for analysis.
4. Returns a structured P&L analysis report as the screener_report state field.
"""

import base64
import logging

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

VISION_MODEL = "llama3.2-vision"


def _analyze_pl_with_vision(screenshot_bytes: bytes, ticker: str) -> str:
    """Send a P&L screenshot to llama3.2-vision via Ollama and return analysis."""
    try:
        from tradingagents.llm_clients.factory import create_llm_client
    except ImportError:
        return "<screener unavailable: llm factory not found>"

    image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    prompt = f"""You are a financial analyst specializing in Indian stock markets. 
You have been given a screenshot of the Profit & Loss (P&L) statement from screener.in for the company {ticker}.

Please analyze this P&L statement and provide:

1. **Revenue Trend**: Is revenue growing, flat, or declining? What is the approximate CAGR?
2. **Profit Trend**: Is net profit growing? Any sharp changes?
3. **Margin Analysis**: Are operating margins expanding or contracting?
4. **Key Ratios visible**: Mention EPS trend, any notable financial ratios visible.
5. **Red Flags**: Any sudden drops in profit, revenue, or margins?
6. **Overall Assessment**: Based on the P&L, is this company's financial health Improving / Stable / Deteriorating?

Be specific with numbers you can read from the table. Format your response clearly with the sections above."""

    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
        }
    ])

    try:
        client = create_llm_client(provider="ollama", model=VISION_MODEL, temperature=0)
        llm = client.get_llm()
        logger.info(f"Sending P&L screenshot to {VISION_MODEL} for analysis...")
        response = llm.invoke([message])
        return response.content
    except Exception as e:
        logger.error(f"Vision LLM error: {e}")
        return f"<screener analysis failed: {e}>"


def create_screener_analyst():
    """Create a screener analyst node for the trading graph.

    Does NOT take the graph LLM as input — uses llama3.2-vision directly.
    """

    def screener_analyst_node(state):
        ticker = state["company_of_interest"]
        logger.info(f"[Screener Analyst] Fetching P&L for {ticker}...")

        from tradingagents.dataflows.screener import fetch_screener_pl_screenshot
        screenshot_bytes = fetch_screener_pl_screenshot(ticker)
        # print("[Screener Analyst] Screenshot captured for {ticker} : ", screenshot_bytes)

        if screenshot_bytes is None:
            report = f"<screener unavailable: Could not capture P&L screenshot for {ticker}>"
            logger.warning(report)
        else:
            report = _analyze_pl_with_vision(screenshot_bytes, ticker)
            print(f"[Screener Analyst] P&L analysis complete for {ticker}: {report}")
            logger.info(f"[Screener Analyst] P&L analysis complete for {ticker}")

        # Return the report into the state
        return {
            "messages": [],
            "screener_report": report,
        }

    return screener_analyst_node
