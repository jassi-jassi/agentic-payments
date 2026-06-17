"""
register_agents.py
───────────────────
Registers the Lead Agent + 3 specialist agents on the ERC-8004 AgentRegistry.
Run this ONCE after deploying contracts.

Usage:
    python scripts/register_agents.py
"""

import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from web3 import Web3
from eth_account import Account
from agents.shared import config
from agents.shared.registry_client import RegistryClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger("RegisterAgents")


# ── Agent definitions ───────────────────────────────────────────
# Each agent has its own private key in a real deployment.
# For this demo, we use the same deployer key for all (one wallet, multiple registrations
# won't work). In practice, give each agent its own wallet.

AGENTS = [
    {
        "env_key": "LEAD_AGENT_WALLET",
        "name": "LeadAgent-v1",
        "endpoint": config.DATA_FETCH_AGENT_URL.replace(":8001", ":8000"),
        "capabilities": ["orchestrate", "decompose", "aggregate"],
        "description": "Lead orchestrator agent",
    },
    {
        "env_key": "DATA_FETCH_AGENT_WALLET",
        "name": "DataFetchAgent-v1",
        "endpoint": config.DATA_FETCH_AGENT_URL,
        "capabilities": ["price_feed", "sentiment", "market_data", "oracle"],
        "description": "Fetches live market data via CoinGecko and Fear & Greed Index",
    },
    {
        "env_key": "ANALYSIS_AGENT_WALLET",
        "name": "AnalysisAgent-v1",
        "endpoint": config.ANALYSIS_AGENT_URL,
        "capabilities": ["ml_analysis", "trend_detection", "signal_scoring", "rsi"],
        "description": "ML-based trend analysis and buy/sell signal generation",
    },
    {
        "env_key": "REPORT_AGENT_WALLET",
        "name": "ReportAgent-v1",
        "endpoint": config.REPORT_AGENT_URL,
        "capabilities": ["report_generation", "formatting", "markdown_output"],
        "description": "Formats and delivers structured market reports",
    },
]


def main():
    print("\n🔗 Connecting to Avalanche Fuji Testnet...")
    w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
    if not w3.is_connected():
        print("❌ Could not connect to Fuji RPC. Check FUJI_RPC_URL in .env")
        sys.exit(1)
    print(f"✅ Connected | Chain ID: {w3.eth.chain_id}")

    print(f"\n📋 AgentRegistry: {config.AGENT_REGISTRY_ADDRESS}")
    print(f"📋 MockUSDC:      {config.MOCK_USDC_ADDRESS}\n")

    # In a real multi-wallet setup, each agent signs its own registration.
    # Here we simulate with the deployer key for all agents.
    deployer = Account.from_key(config.PRIVATE_KEY)
    print(f"Deployer/signer: {deployer.address}")
    balance = w3.eth.get_balance(deployer.address)
    print(f"Balance: {w3.from_wei(balance, 'ether'):.4f} AVAX\n")

    if balance < w3.to_wei(0.01, "ether"):
        print("⚠️  Low AVAX balance. Get testnet AVAX from https://faucet.avax.network/")

    registry = RegistryClient(config.PRIVATE_KEY)

    # Check if already registered
    try:
        existing = registry.get_agent_info(deployer.address)
        if existing.wallet != "0x" + "0" * 40:
            print(f"⚠️  Address {deployer.address} already registered as '{existing.name}'")
            print("   Each agent needs its own wallet. For demo, skipping re-registration.\n")
    except Exception:
        pass

    print("─" * 50)
    print("Registering specialist agents on-chain (ERC-8004)...")
    print("─" * 50)
    print()

    # For demo: register the main agent (DataFetchAgent) from deployer wallet
    # In production: each agent has its own private key and registers itself
    demo_agent = AGENTS[1]  # DataFetchAgent
    try:
        tx = registry.register_agent(
            name=demo_agent["name"],
            endpoint=demo_agent["endpoint"],
            capabilities=demo_agent["capabilities"],
        )
        print(f"✅ {demo_agent['name']} registered")
        print(f"   Capabilities: {demo_agent['capabilities']}")
        print(f"   Endpoint:     {demo_agent['endpoint']}")
        print(f"   Tx:           {tx}")
    except Exception as e:
        if "already registered" in str(e).lower():
            print(f"ℹ️  {demo_agent['name']} already registered — skipping")
        else:
            print(f"❌ Registration failed: {e}")

    print()
    print("─" * 50)
    print("📝 .env additions needed for multi-wallet setup:")
    print("─" * 50)
    print("""
# Generate separate wallets for each agent:
# python -c "from eth_account import Account; a=Account.create(); print(a.address, a.key.hex())"

LEAD_AGENT_WALLET=0x...        # Register separately with lead's private key
DATA_FETCH_AGENT_WALLET=0x...  # Register separately with data agent's private key
ANALYSIS_AGENT_WALLET=0x...    # Register separately with analysis agent's private key
REPORT_AGENT_WALLET=0x...      # Register separately with report agent's private key
""")
    print()
    print("✅ Registration script complete")
    print("   Next: python scripts/fund_agents.py")


if __name__ == "__main__":
    main()
