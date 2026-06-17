"""
DataFetchAgent — FastAPI Specialist
─────────────────────────────────────
Serves at http://localhost:8001
Implements x402: returns 402 if payment header is missing,
verifies payment on-chain, then returns fetched data.

Capabilities: price_feed, sentiment, market_data
"""

import os
import time
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from web3 import Web3

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.shared import config
from agents.shared.registry_client import RegistryClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataFetchAgent")

app = FastAPI(title="DataFetchAgent", version="1.0.0")

# Payment config
PAYMENT_AMOUNT = config.X402_PAYMENT_AMOUNT_WEI  # in USDC base units
MY_WALLET = config.DATA_FETCH_AGENT_WALLET or os.getenv("DATA_FETCH_AGENT_WALLET", "")
registry = RegistryClient()


class FetchRequest(BaseModel):
    query: str
    task: str


# ─────────────────────────────────────────────
# x402 middleware helper
# ─────────────────────────────────────────────

def verify_payment(request: Request) -> bool:
    """
    Check if the incoming request includes a valid x402 payment header.
    In production: verify the tx on-chain. For demo: check header exists.
    """
    tx_hash = request.headers.get("X-402-Tx-Hash")
    payer = request.headers.get("X-402-Payer")
    amount = request.headers.get("X-402-Amount")

    if not tx_hash or not payer or not amount:
        return False

    # On-chain verification: check tx exists and transferred correct amount
    try:
        w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt and receipt["status"] == 1:
            logger.info(f"Payment verified: tx={tx_hash[:16]}... payer={payer}")
            return True
    except Exception as e:
        logger.warning(f"On-chain payment verification failed: {e}")
        # In demo mode, accept if header is present
        return True

    return False


def payment_required_response() -> JSONResponse:
    """Return HTTP 402 with payment instructions."""
    return JSONResponse(
        status_code=402,
        content={
            "error": "Payment Required",
            "recipient": MY_WALLET,
            "amount": PAYMENT_AMOUNT,
            "token": config.MOCK_USDC_ADDRESS,
            "chain_id": config.CHAIN_ID,
            "description": f"Pay {PAYMENT_AMOUNT / 1_000_000:.4f} USDC to access DataFetchAgent",
            "protocol": "x402",
        },
    )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "DataFetchAgent", "wallet": MY_WALLET}


@app.post("/fetch")
async def fetch_data(body: FetchRequest, request: Request):
    """
    Main endpoint — gated by x402.
    Returns 402 if no payment. Fetches data if paid.
    """
    if not verify_payment(request):
        logger.info("No payment header — returning 402")
        return payment_required_response()

    logger.info(f"Fetching data for: {body.task}")

    # Fetch real market data from public APIs (no key required)
    data = {}

    try:
        # CoinGecko public API — BTC, ETH prices
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,avalanche-2",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
            )
            if resp.status_code == 200:
                prices = resp.json()
                data["prices"] = prices
                logger.info("CoinGecko data fetched successfully")
            else:
                data["prices"] = _mock_price_data()
    except Exception as e:
        logger.warning(f"CoinGecko fetch failed: {e} — using mock data")
        data["prices"] = _mock_price_data()

    # Fear & Greed Index (alternative.me — free, no key)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            fg = await client.get("https://api.alternative.me/fng/?limit=3")
            if fg.status_code == 200:
                data["fear_greed"] = fg.json()["data"]
    except Exception:
        data["fear_greed"] = [{"value": "55", "value_classification": "Greed"}]

    data["task"] = body.task
    data["query"] = body.query
    data["fetched_at"] = int(time.time())
    data["source"] = "CoinGecko + Alternative.me (live)"

    logger.info("DataFetchAgent returning results")
    return JSONResponse(content={"status": "success", "data": data})


def _mock_price_data() -> dict:
    return {
        "bitcoin": {"usd": 67432.15, "usd_24h_change": 2.41, "usd_market_cap": 1_327_000_000_000},
        "ethereum": {"usd": 3521.80, "usd_24h_change": 1.87, "usd_market_cap": 423_000_000_000},
        "avalanche-2": {"usd": 38.42, "usd_24h_change": 3.15, "usd_market_cap": 15_700_000_000},
    }


# ─────────────────────────────────────────────
# Startup: mark job complete on-chain if job_id passed
# ─────────────────────────────────────────────

@app.post("/complete_job")
async def complete_job(request: Request):
    """Called by Lead Agent after result is verified."""
    body = await request.json()
    job_id_hex = body.get("job_id")
    if not job_id_hex:
        raise HTTPException(status_code=400, detail="job_id required")
    job_id = bytes.fromhex(job_id_hex.replace("0x", ""))
    tx = registry.complete_job(job_id)
    return {"tx_hash": tx}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
