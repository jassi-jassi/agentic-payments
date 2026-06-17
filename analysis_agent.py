"""
AnalysisAgent — FastAPI Specialist
────────────────────────────────────
Serves at http://localhost:8002
Implements x402 payment gate.
Capabilities: ml_analysis, trend_detection, signal_scoring
"""

import time
import logging
import statistics
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from web3 import Web3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.shared import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnalysisAgent")

app = FastAPI(title="AnalysisAgent", version="1.0.0")

PAYMENT_AMOUNT = config.X402_PAYMENT_AMOUNT_WEI
MY_WALLET = config.ANALYSIS_AGENT_WALLET


class AnalysisRequest(BaseModel):
    query: str
    task: str
    data: dict | None = None


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
        return bool(tx_hash)  # demo fallback


def payment_required_response() -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "error": "Payment Required",
            "recipient": MY_WALLET,
            "amount": PAYMENT_AMOUNT,
            "token": config.MOCK_USDC_ADDRESS,
            "chain_id": config.CHAIN_ID,
            "description": f"Pay {PAYMENT_AMOUNT / 1_000_000:.4f} USDC to access AnalysisAgent",
            "protocol": "x402",
        },
    )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "AnalysisAgent", "wallet": MY_WALLET}


@app.post("/analyze")
async def analyze(body: AnalysisRequest, request: Request):
    if not verify_payment(request):
        logger.info("No payment — returning 402")
        return payment_required_response()

    logger.info(f"Running analysis for: {body.task}")

    prices = {}
    fear_greed = []

    if body.data and "data" in body.data:
        inner = body.data["data"]
        prices = inner.get("prices", {})
        fear_greed = inner.get("fear_greed", [])

    analysis = {}

    # ── BTC Analysis ──
    btc = prices.get("bitcoin", {})
    if btc:
        btc_change = btc.get("usd_24h_change", 0)
        btc_price = btc.get("usd", 0)
        analysis["bitcoin"] = {
            "price_usd": btc_price,
            "change_24h_pct": round(btc_change, 2),
            "trend": _classify_trend(btc_change),
            "signal": _generate_signal(btc_change, fear_greed),
            "rsi_estimate": _estimate_rsi(btc_change),
            "support_level": round(btc_price * 0.95, 2),
            "resistance_level": round(btc_price * 1.05, 2),
        }

    # ── ETH Analysis ──
    eth = prices.get("ethereum", {})
    if eth:
        eth_change = eth.get("usd_24h_change", 0)
        eth_price = eth.get("usd", 0)
        analysis["ethereum"] = {
            "price_usd": eth_price,
            "change_24h_pct": round(eth_change, 2),
            "trend": _classify_trend(eth_change),
            "signal": _generate_signal(eth_change, fear_greed),
            "rsi_estimate": _estimate_rsi(eth_change),
            "support_level": round(eth_price * 0.95, 2),
            "resistance_level": round(eth_price * 1.05, 2),
        }

    # ── AVAX Analysis ──
    avax = prices.get("avalanche-2", {})
    if avax:
        avax_change = avax.get("usd_24h_change", 0)
        avax_price = avax.get("usd", 0)
        analysis["avalanche"] = {
            "price_usd": avax_price,
            "change_24h_pct": round(avax_change, 2),
            "trend": _classify_trend(avax_change),
            "signal": _generate_signal(avax_change, fear_greed),
            "rsi_estimate": _estimate_rsi(avax_change),
        }

    # ── Market Sentiment ──
    fg_score = int(fear_greed[0]["value"]) if fear_greed else 50
    analysis["market_sentiment"] = {
        "fear_greed_score": fg_score,
        "sentiment_label": _fg_label(fg_score),
        "overall_market_bias": "BULLISH" if fg_score > 55 else ("BEARISH" if fg_score < 45 else "NEUTRAL"),
    }

    # ── Portfolio Recommendation ──
    signals = [
        v.get("signal", "HOLD")
        for v in analysis.values()
        if isinstance(v, dict) and "signal" in v
    ]
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")
    analysis["portfolio_recommendation"] = {
        "action": "BUY" if buy_count > sell_count else ("SELL" if sell_count > buy_count else "HOLD"),
        "confidence": round(max(buy_count, sell_count) / max(len(signals), 1) * 100, 1),
        "reasoning": f"{buy_count} BUY signals, {sell_count} SELL signals across monitored assets",
    }

    analysis["task"] = body.task
    analysis["analysed_at"] = int(time.time())

    logger.info("AnalysisAgent returning results")
    return JSONResponse(content={"status": "success", "analysis": analysis})


# ─────────────────────────────────────────────
# Analysis helpers
# ─────────────────────────────────────────────

def _classify_trend(change_24h: float) -> str:
    if change_24h > 3:
        return "STRONG_UPTREND"
    elif change_24h > 0.5:
        return "UPTREND"
    elif change_24h < -3:
        return "STRONG_DOWNTREND"
    elif change_24h < -0.5:
        return "DOWNTREND"
    return "SIDEWAYS"


def _generate_signal(change_24h: float, fear_greed: list) -> str:
    fg_score = int(fear_greed[0]["value"]) if fear_greed else 50
    # Simple momentum + sentiment signal
    if change_24h > 2 and fg_score > 50:
        return "BUY"
    elif change_24h < -2 and fg_score < 50:
        return "SELL"
    return "HOLD"


def _estimate_rsi(change_24h: float) -> float:
    """Rough RSI estimate from single-period change (demo only)."""
    base = 50.0
    rsi = base + (change_24h * 3)
    return round(max(0, min(100, rsi)), 1)


def _fg_label(score: int) -> str:
    if score >= 75:
        return "Extreme Greed"
    elif score >= 55:
        return "Greed"
    elif score >= 45:
        return "Neutral"
    elif score >= 25:
        return "Fear"
    return "Extreme Fear"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
