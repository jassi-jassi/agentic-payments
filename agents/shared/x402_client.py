"""
x402 Payment Client
────────────────────
Implements the x402 protocol pattern:
  1. Agent calls a specialist endpoint
  2. If specialist returns HTTP 402 Payment Required, parse the payment details
  3. Sign and broadcast the on-chain ERC-20 transfer (mock USDC → specialist wallet)
  4. Retry the request with the payment proof in headers
  5. Specialist verifies payment on-chain and returns result

In production this would use the official x402 SDK.
This implementation demonstrates the full protocol flow on Fuji testnet.
"""

import json
import time
import logging
import httpx
from web3 import Web3
from eth_account import Account
from typing import Any

from . import config

logger = logging.getLogger(__name__)


class X402PaymentError(Exception):
    pass


class X402Client:
    """
    HTTP client that speaks x402: automatically handles 402 responses
    by making the required on-chain stablecoin payment and retrying.
    """

    def __init__(self, payer_private_key: str | None = None):
        self.private_key = payer_private_key or config.PRIVATE_KEY
        self.w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
        self.account = Account.from_key(self.private_key)

        # Load USDC contract
        usdc_abi = config.load_abi("MockUSDC")
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.MOCK_USDC_ADDRESS),
            abi=usdc_abi,
        )

        logger.info(f"X402Client ready | payer={self.account.address}")

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def post(self, url: str, payload: dict, timeout: int = 30) -> dict:
        """
        POST to a specialist agent endpoint.
        Automatically pays if a 402 is returned, then retries once.
        """
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)

            if response.status_code == 200:
                return response.json()

            if response.status_code == 402:
                logger.info(f"402 received from {url} — initiating x402 payment")
                payment_details = self._parse_402(response)
                tx_hash = self._pay(payment_details)
                logger.info(f"Payment sent: {tx_hash}")

                # Retry with payment proof
                headers = {
                    "X-402-Tx-Hash": tx_hash,
                    "X-402-Payer": self.account.address,
                    "X-402-Amount": str(payment_details["amount"]),
                    "X-402-Token": config.MOCK_USDC_ADDRESS,
                    "X-402-Chain-Id": str(config.CHAIN_ID),
                }
                retry = client.post(url, json=payload, headers=headers)
                if retry.status_code == 200:
                    result = retry.json()
                    result["_x402_payment"] = {
                        "tx_hash": tx_hash,
                        "amount_usdc": payment_details["amount"] / 1_000_000,
                        "recipient": payment_details["recipient"],
                    }
                    return result
                raise X402PaymentError(
                    f"Payment accepted but specialist returned {retry.status_code}: {retry.text}"
                )

            raise X402PaymentError(
                f"Unexpected status {response.status_code} from {url}: {response.text}"
            )

    # ─────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────

    def _parse_402(self, response: httpx.Response) -> dict:
        """Parse 402 response body for payment instructions."""
        try:
            body = response.json()
        except Exception:
            raise X402PaymentError("402 response body is not JSON")

        required = ("recipient", "amount", "token")
        for field in required:
            if field not in body:
                raise X402PaymentError(f"402 response missing field: {field}")

        return {
            "recipient": Web3.to_checksum_address(body["recipient"]),
            "amount": int(body["amount"]),       # in token base units (6 decimals for USDC)
            "token": body["token"],
            "job_id": body.get("job_id", ""),
        }

    def _pay(self, details: dict) -> str:
        """
        Transfer mock USDC to the specialist's wallet.
        Returns the transaction hash as a hex string.
        """
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        gas_price = self.w3.eth.gas_price

        tx = self.usdc.functions.transfer(
            details["recipient"],
            details["amount"],
        ).build_transaction({
            "chainId": config.CHAIN_ID,
            "from": self.account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        # Wait for receipt (up to ~15 seconds on Fuji)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise X402PaymentError(f"Payment transaction reverted: {tx_hash.hex()}")

        return tx_hash.hex()

    def get_usdc_balance(self, address: str | None = None) -> float:
        """Return USDC balance in human-readable units."""
        addr = Web3.to_checksum_address(address or self.account.address)
        raw = self.usdc.functions.balanceOf(addr).call()
        return raw / 1_000_000
