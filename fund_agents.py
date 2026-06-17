"""
fund_agents.py
───────────────
Mints mock USDC to all agent wallets so they can pay each other via x402.
Also claims from faucet if available.

Usage:
    python scripts/fund_agents.py
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FundAgents")

MINT_AMOUNT_USDC = 500  # USDC per agent wallet


def main():
    print("\n💰 Funding agent wallets with mock USDC...")
    w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
    deployer = Account.from_key(config.PRIVATE_KEY)

    usdc_abi = config.load_abi("MockUSDC")
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(config.MOCK_USDC_ADDRESS),
        abi=usdc_abi,
    )

    wallets_to_fund = {
        "LeadAgent":      config.LEAD_AGENT_WALLET,
        "DataFetchAgent": config.DATA_FETCH_AGENT_WALLET,
        "AnalysisAgent":  config.ANALYSIS_AGENT_WALLET,
        "ReportAgent":    config.REPORT_AGENT_WALLET,
    }

    amount_wei = MINT_AMOUNT_USDC * 1_000_000  # 6 decimals

    for name, wallet in wallets_to_fund.items():
        if not wallet or wallet == "0x":
            print(f"⚠️  {name}: wallet address not set in .env — skipping")
            continue

        wallet = Web3.to_checksum_address(wallet)
        bal_before = usdc.functions.balanceOf(wallet).call() / 1_000_000

        if bal_before >= MINT_AMOUNT_USDC:
            print(f"ℹ️  {name} ({wallet[:10]}...) already has {bal_before:.2f} USDC — skipping")
            continue

        try:
            nonce = w3.eth.get_transaction_count(deployer.address)
            tx = usdc.functions.mint(wallet, amount_wei).build_transaction({
                "chainId": config.CHAIN_ID,
                "from": deployer.address,
                "nonce": nonce,
                "gasPrice": w3.eth.gas_price,
                "gas": 100_000,
            })
            signed = deployer.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] == 1:
                bal_after = usdc.functions.balanceOf(wallet).call() / 1_000_000
                print(f"✅ {name} ({wallet[:10]}...) funded: {bal_after:.2f} USDC | tx={tx_hash.hex()[:16]}...")
            else:
                print(f"❌ {name}: mint tx reverted")
        except Exception as e:
            print(f"❌ {name}: {e}")

    # Also claim from faucet for the deployer/lead agent
    print("\n🚰 Claiming from USDC faucet for deployer...")
    try:
        nonce = w3.eth.get_transaction_count(deployer.address)
        tx = usdc.functions.faucet().build_transaction({
            "chainId": config.CHAIN_ID,
            "from": deployer.address,
            "nonce": nonce,
            "gasPrice": w3.eth.gas_price,
            "gas": 100_000,
        })
        signed = deployer.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] == 1:
            bal = usdc.functions.balanceOf(deployer.address).call() / 1_000_000
            print(f"✅ Deployer faucet claimed | Balance: {bal:.2f} USDC")
        else:
            print("ℹ️  Faucet claim reverted (cooldown?)")
    except Exception as e:
        print(f"ℹ️  Faucet: {e}")

    print("\n✅ Funding complete. Run: python scripts/run_demo.py")


if __name__ == "__main__":
    main()
