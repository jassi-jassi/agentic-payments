"""
Shared configuration for all agents.
Loads from .env file — never hardcode secrets.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Wallet / Chain ──────────────────────────────────────────────
PRIVATE_KEY: str = os.environ["PRIVATE_KEY"]
FUJI_RPC_URL: str = os.getenv("FUJI_RPC_URL", "https://api.avax-test.network/ext/bc/C/rpc")
CHAIN_ID: int = int(os.getenv("CHAIN_ID", "43113"))  # 43113=Fuji, 43114=Mainnet

# ── Contract Addresses (set after deploy) ───────────────────────
AGENT_REGISTRY_ADDRESS: str = os.environ["AGENT_REGISTRY_ADDRESS"]
MOCK_USDC_ADDRESS: str = os.environ["MOCK_USDC_ADDRESS"]

# ── LLM API Keys ────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # "openai" | "anthropic"
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ── Specialist Agent Endpoints ───────────────────────────────────
DATA_FETCH_AGENT_URL: str = os.getenv("DATA_FETCH_AGENT_URL", "http://localhost:8001")
ANALYSIS_AGENT_URL: str = os.getenv("ANALYSIS_AGENT_URL", "http://localhost:8002")
REPORT_AGENT_URL: str = os.getenv("REPORT_AGENT_URL", "http://localhost:8003")

# ── Specialist Agent Wallets (addresses, not private keys) ───────
DATA_FETCH_AGENT_WALLET: str = os.getenv("DATA_FETCH_AGENT_WALLET", "")
ANALYSIS_AGENT_WALLET: str = os.getenv("ANALYSIS_AGENT_WALLET", "")
REPORT_AGENT_WALLET: str = os.getenv("REPORT_AGENT_WALLET", "")
LEAD_AGENT_WALLET: str = os.getenv("LEAD_AGENT_WALLET", "")

# ── x402 Payment Config ──────────────────────────────────────────
X402_PAYMENT_AMOUNT_USDC: float = float(os.getenv("X402_PAYMENT_AMOUNT_USDC", "0.01"))
X402_PAYMENT_AMOUNT_WEI: int = int(X402_PAYMENT_AMOUNT_USDC * 1_000_000)  # 6 decimals

# ── Load ABI from compiled artifacts ────────────────────────────
def load_abi(contract_name: str) -> list:
    """Load ABI from Hardhat artifacts directory."""
    artifact_path = Path(__file__).parent.parent.parent / \
        "artifacts" / "contracts" / "src" / f"{contract_name}.sol" / f"{contract_name}.json"
    if artifact_path.exists():
        with open(artifact_path) as f:
            return json.load(f)["abi"]
    # Fallback: minimal ABI for key functions
    return _get_minimal_abi(contract_name)

def _get_minimal_abi(contract_name: str) -> list:
    """Minimal ABI used before contracts are compiled."""
    if contract_name == "AgentRegistry":
        return [
            {"inputs": [{"name": "name","type": "string"},{"name": "endpoint","type": "string"},{"name": "capabilities","type": "string[]"}],"name": "registerAgent","outputs": [],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [{"name": "specialist","type": "address"},{"name": "taskDescription","type": "string"},{"name": "paymentAmount","type": "uint256"}],"name": "createJob","outputs": [{"name": "jobId","type": "bytes32"}],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [{"name": "jobId","type": "bytes32"}],"name": "completeJob","outputs": [],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [{"name": "jobId","type": "bytes32"},{"name": "feedbackScore","type": "uint8"}],"name": "submitFeedback","outputs": [],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [],"name": "getAllAgents","outputs": [{"name": "","type": "address[]"}],"stateMutability": "view","type": "function"},
            {"inputs": [{"name": "minReputation","type": "uint256"}],"name": "getAgentsByReputation","outputs": [{"name": "filtered","type": "address[]"}],"stateMutability": "view","type": "function"},
            {"inputs": [{"name": "","type": "address"}],"name": "agents","outputs": [{"name": "wallet","type": "address"},{"name": "name","type": "string"},{"name": "endpoint","type": "string"},{"name": "status","type": "uint8"},{"name": "registeredAt","type": "uint256"},{"name": "reputationScore","type": "uint256"},{"name": "jobsCompleted","type": "uint256"},{"name": "jobsFailed","type": "uint256"},{"name": "totalEarned","type": "uint256"}],"stateMutability": "view","type": "function"},
        ]
    if contract_name == "MockUSDC":
        return [
            {"inputs": [{"name": "spender","type": "address"},{"name": "amount","type": "uint256"}],"name": "approve","outputs": [{"name": "","type": "bool"}],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [{"name": "to","type": "address"},{"name": "amount","type": "uint256"}],"name": "transfer","outputs": [{"name": "","type": "bool"}],"stateMutability": "nonpayable","type": "function"},
            {"inputs": [{"name": "account","type": "address"}],"name": "balanceOf","outputs": [{"name": "","type": "uint256"}],"stateMutability": "view","type": "function"},
            {"inputs": [],"name": "faucet","outputs": [],"stateMutability": "nonpayable","type": "function"},
        ]
    return []
