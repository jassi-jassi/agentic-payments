"""
Main API — Entry Point
────────────────────────
FastAPI server at http://localhost:8000
POST /run  →  triggers the full Lead Agent pipeline
GET  /status → health + on-chain stats
GET  /agents → list registered agents from ERC-8004 registry
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.lead.lead_agent import LeadAgent
from agents.shared.registry_client import RegistryClient
from agents.shared import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("MainAPI")

app = FastAPI(
    title="Agentic Payments — Lead Agent API",
    description="Multi-agent system using x402 micropayments + ERC-8004 identity on Avalanche",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
lead_agent = LeadAgent()
registry_client = RegistryClient()


class RunRequest(BaseModel):
    query: str


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "name": "Agentic Payments API",
        "version": "1.0.0",
        "endpoints": ["/run", "/agents", "/status"],
        "network": "Avalanche Fuji Testnet",
        "contracts": {
            "AgentRegistry": config.AGENT_REGISTRY_ADDRESS,
            "MockUSDC": config.MOCK_USDC_ADDRESS,
        },
    }


@app.get("/status")
def status():
    """Health check + on-chain agent count."""
    try:
        all_agents = registry_client.get_all_agents()
        agent_count = len(all_agents)
    except Exception as e:
        logger.warning(f"Could not fetch agent count: {e}")
        agent_count = -1

    return {
        "status": "ok",
        "registered_agents": agent_count,
        "chain_id": config.CHAIN_ID,
        "registry": config.AGENT_REGISTRY_ADDRESS,
        "usdc": config.MOCK_USDC_ADDRESS,
    }


@app.get("/agents")
def list_agents():
    """Return all registered agents with their on-chain info."""
    try:
        addresses = registry_client.get_all_agents()
        agents = []
        for addr in addresses:
            try:
                info = registry_client.get_agent_info(addr)
                caps = registry_client.get_capabilities(addr)
                agents.append({
                    "wallet": info.wallet,
                    "name": info.name,
                    "endpoint": info.endpoint,
                    "reputation_score": info.reputation_score,
                    "jobs_completed": info.jobs_completed,
                    "jobs_failed": info.jobs_failed,
                    "status": {0: "Inactive", 1: "Active", 2: "Suspended"}.get(info.status, "Unknown"),
                    "capabilities": caps,
                })
            except Exception as e:
                agents.append({"wallet": addr, "error": str(e)})
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registry error: {e}")


@app.post("/run")
def run_pipeline(body: RunRequest):
    """
    Trigger the full Lead Agent pipeline:
    1. Discover specialists via ERC-8004
    2. Decompose query into subtasks
    3. Dispatch to specialists with x402 micropayments
    4. Aggregate results
    5. Submit reputation feedback on-chain
    """
    if not body.query or len(body.query.strip()) < 5:
        raise HTTPException(status_code=400, detail="Query too short")

    logger.info(f"Pipeline triggered: {body.query!r}")

    try:
        result = lead_agent.run(body.query)
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "query": result.query,
        "final_report": result.final_report,
        "total_paid_usdc": result.total_paid_usdc,
        "jobs": [
            {
                "specialist": job.specialist_name,
                "task": job.task,
                "feedback_score": job.feedback_score,
                "payment_tx": job.payment_tx,
                "on_chain_job_id": job.job_id.hex() if job.job_id else None,
                "result_preview": str(job.result)[:300] if job.result else None,
            }
            for job in result.jobs
        ],
        "on_chain_feedback_txs": result.on_chain_feedback_txs,
        "protocol": "x402 + ERC-8004",
        "network": "Avalanche Fuji Testnet (chain_id=43113)",
    }
