"""
ReportAgent — FastAPI Specialist
──────────────────────────────────
Serves at http://localhost:8003
Implements x402 payment gate.
Capabilities: report_generation, formatting, markdown_output
"""

import time
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from web3 import Web3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.shared import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportAgent")

app = FastAPI(title="ReportAgent", version="1.0.0")

PAYMENT_AMOUNT = config.X402_PAYMENT_AMOUNT_WEI
MY_WALLET = config.REPORT_AGENT_WALLET


class ReportRequest(BaseModel):
    query: str
    task: str
    data: dict | None = None
    analysis: dict | None = None


# ─────────────────────────────────────────────
# x402 verification
# ─────────────────────────────────────────────

def verify_payment(request: Request) -> bool:
    tx_hash = request.headers.get("X-402-Tx-Hash")
    payer = request.headers.get("X-402-Payer")
    if not tx_hash or not payer:
        return False
    try:
        w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        return receipt is not None and receipt["status"] == 1
    except Exception:
        return bool(tx_hash)


def payment_required_response() -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "error": "Payment Required",
            "recipient": MY_WALLET,
            "amount": PAYMENT_AMOUNT,
            "token": config.MOCK_USDC_ADDRESS,
            "chain_id": config.CHAIN_ID,
            "description": f"Pay {PAYMENT_AMOUNT / 1_000_000:.4f} USDC to access ReportAgent",
            "protocol": "x402",
        },
    )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "ReportAgent", "wallet": MY_WALLET}


@app.post("/report")
async def generate_report(body: ReportRequest, request: Request):
    if not verify_payment(request):
        logger.info("No payment — returning 402")
        return payment_required_response()

    logger.info(f"Generating report for: {body.task}")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    prices = {}
    analysis = {}

    if body.data and "data" in body.data:
        prices = body.data["data"].get("prices", {})
    if body.analysis and "analysis" in body.analysis:
        analysis = body.analysis["analysis"]

    # Build structured markdown report
    report_md = _build_markdown_report(body.query, prices, analysis, now)
    report_json = _build_json_report(body.query, prices, analysis, now)

    logger.info("ReportAgent returning results")
    return JSONResponse(content={
        "status": "success",
        "report": {
            "markdown": report_md,
            "json": report_json,
            "generated_at": now,
            "query": body.query,
        },
    })


# ─────────────────────────────────────────────
# Report builders
# ─────────────────────────────────────────────

def _build_markdown_report(query: str, prices: dict, analysis: dict, timestamp: str) -> str:
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    avax = prices.get("avalanche-2", {})
    btc_a = analysis.get("bitcoin", {})
    eth_a = analysis.get("ethereum", {})
    avax_a = analysis.get("avalanche", {})
    sentiment = analysis.get("market_sentiment", {})
    recommendation = analysis.get("portfolio_recommendation", {})

    lines = [
        f"# 📊 Agentic Market Report",
        f"**Query:** {query}",
        f"**Generated:** {timestamp} by ReportAgent (paid via x402 on Avalanche Fuji)",
        "",
        "---",
        "",
        "## 🌡️ Market Sentiment",
        f"- **Fear & Greed Index:** {sentiment.get('fear_greed_score', 'N/A')} — *{sentiment.get('sentiment_label', 'N/A')}*",
        f"- **Overall Market Bias:** `{sentiment.get('overall_market_bias', 'N/A')}`",
        "",
        "---",
        "",
        "## 💰 Asset Prices & Signals",
        "",
        "| Asset | Price (USD) | 24h Change | Trend | Signal | RSI Est. |",
        "|-------|------------|------------|-------|--------|----------|",
    ]

    if btc:
        lines.append(
            f"| Bitcoin (BTC) | ${btc.get('usd', 0):,.2f} | "
            f"{btc.get('usd_24h_change', 0):+.2f}% | "
            f"{btc_a.get('trend', 'N/A')} | "
            f"**{btc_a.get('signal', 'N/A')}** | "
            f"{btc_a.get('rsi_estimate', 'N/A')} |"
        )
    if eth:
        lines.append(
            f"| Ethereum (ETH) | ${eth.get('usd', 0):,.2f} | "
            f"{eth.get('usd_24h_change', 0):+.2f}% | "
            f"{eth_a.get('trend', 'N/A')} | "
            f"**{eth_a.get('signal', 'N/A')}** | "
            f"{eth_a.get('rsi_estimate', 'N/A')} |"
        )
    if avax:
        lines.append(
            f"| Avalanche (AVAX) | ${avax.get('usd', 0):,.2f} | "
            f"{avax.get('usd_24h_change', 0):+.2f}% | "
            f"{avax_a.get('trend', 'N/A')} | "
            f"**{avax_a.get('signal', 'N/A')}** | "
            f"{avax_a.get('rsi_estimate', 'N/A')} |"
        )

    action = recommendation.get("action", "HOLD")
    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(action, "⚪")

    lines += [
        "",
        "---",
        "",
        "## 🎯 Portfolio Recommendation",
        "",
        f"### {emoji} {action} — {recommendation.get('confidence', 0)}% Confidence",
        "",
        f"> {recommendation.get('reasoning', '')}",
        "",
        "---",
        "",
        "## ⚠️ Disclaimer",
        "_This report is generated autonomously by AI agents. Not financial advice._",
        "_All data fetched live via x402-gated specialist agents on Avalanche Fuji Testnet._",
    ]

    return "\n".join(lines)


def _build_json_report(query: str, prices: dict, analysis: dict, timestamp: str) -> dict:
    return {
        "query": query,
        "timestamp": timestamp,
        "prices": prices,
        "analysis": analysis,
        "protocol": "x402 + ERC-8004",
        "network": "Avalanche Fuji Testnet",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
