"""
ERC-8004 Registry Client
──────────────────────────
Wraps all on-chain calls to AgentRegistry.sol:
  - Agent discovery (getAllAgents, getAgentsByReputation)
  - Job lifecycle (createJob, completeJob, submitFeedback)
  - Identity reads (agents mapping)
"""

import logging
from dataclasses import dataclass
from web3 import Web3
from eth_account import Account

from . import config

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    wallet: str
    name: str
    endpoint: str
    reputation_score: int
    jobs_completed: int
    jobs_failed: int
    total_earned: int
    status: int  # 0=Inactive, 1=Active, 2=Suspended


class RegistryClient:
    """
    Python client for ERC-8004 AgentRegistry smart contract.
    """

    def __init__(self, private_key: str | None = None):
        self.private_key = private_key or config.PRIVATE_KEY
        self.w3 = Web3(Web3.HTTPProvider(config.FUJI_RPC_URL))
        self.account = Account.from_key(self.private_key)

        abi = config.load_abi("AgentRegistry")
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(config.AGENT_REGISTRY_ADDRESS),
            abi=abi,
        )
        logger.info(f"RegistryClient ready | signer={self.account.address}")

    # ─────────────────────────────────────────────
    # Identity — Write
    # ─────────────────────────────────────────────

    def register_agent(self, name: str, endpoint: str, capabilities: list[str]) -> str:
        """Register this agent on-chain. Returns tx hash."""
        tx = self.contract.functions.registerAgent(
            name, endpoint, capabilities
        ).build_transaction(self._tx_params())
        return self._sign_and_send(tx)

    def update_endpoint(self, new_endpoint: str) -> str:
        tx = self.contract.functions.updateEndpoint(new_endpoint).build_transaction(
            self._tx_params()
        )
        return self._sign_and_send(tx)

    # ─────────────────────────────────────────────
    # Job Lifecycle — Write
    # ─────────────────────────────────────────────

    def create_job(self, specialist_address: str, task_description: str, payment_amount: int) -> bytes:
        """
        Record a new job on-chain before dispatching to specialist.
        Returns the jobId (bytes32).
        """
        tx = self.contract.functions.createJob(
            Web3.to_checksum_address(specialist_address),
            task_description,
            payment_amount,
        ).build_transaction(self._tx_params())
        tx_hash = self._sign_and_send(tx)

        # Retrieve jobId from emitted event
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        job_created_event = self.contract.events.JobCreated().process_receipt(receipt)
        if job_created_event:
            job_id = job_created_event[0]["args"]["jobId"]
            logger.info(f"Job created on-chain: {job_id.hex()}")
            return job_id
        raise RuntimeError("JobCreated event not found in receipt")

    def complete_job(self, job_id: bytes) -> str:
        """Specialist calls this after finishing the task."""
        tx = self.contract.functions.completeJob(job_id).build_transaction(
            self._tx_params()
        )
        return self._sign_and_send(tx)

    def submit_feedback(self, job_id: bytes, feedback_score: int) -> str:
        """
        Lead Agent calls this after validating specialist output.
        feedback_score: 1 (poor) to 5 (excellent)
        """
        assert 1 <= feedback_score <= 5, "Score must be 1–5"
        tx = self.contract.functions.submitFeedback(
            job_id, feedback_score
        ).build_transaction(self._tx_params())
        return self._sign_and_send(tx)

    # ─────────────────────────────────────────────
    # Discovery — Read
    # ─────────────────────────────────────────────

    def get_all_agents(self) -> list[str]:
        return self.contract.functions.getAllAgents().call()

    def get_agents_by_reputation(self, min_reputation: int = 400) -> list[str]:
        return self.contract.functions.getAgentsByReputation(min_reputation).call()

    def get_agent_info(self, wallet_address: str) -> AgentInfo:
        raw = self.contract.functions.agents(
            Web3.to_checksum_address(wallet_address)
        ).call()
        # raw tuple: (wallet, name, endpoint, status, registeredAt, reputationScore,
        #             jobsCompleted, jobsFailed, totalEarned)
        return AgentInfo(
            wallet=raw[0],
            name=raw[1],
            endpoint=raw[2],
            status=raw[3],
            reputation_score=raw[5],
            jobs_completed=raw[6],
            jobs_failed=raw[7],
            total_earned=raw[8],
        )

    def get_capabilities(self, wallet_address: str) -> list[str]:
        return self.contract.functions.getCapabilities(
            Web3.to_checksum_address(wallet_address)
        ).call()

    def discover_best_agent(self, capability: str, min_reputation: int = 400) -> AgentInfo | None:
        """
        Find the highest-reputation active agent with the required capability.
        This is the core ERC-8004 discovery flow.
        """
        candidates = self.get_agents_by_reputation(min_reputation)
        best: AgentInfo | None = None

        for addr in candidates:
            try:
                caps = self.get_capabilities(addr)
                if capability in caps:
                    info = self.get_agent_info(addr)
                    if info.status == 1:  # Active
                        if best is None or info.reputation_score > best.reputation_score:
                            best = info
            except Exception as e:
                logger.warning(f"Could not read capabilities for {addr}: {e}")

        if best:
            logger.info(
                f"Best agent for '{capability}': {best.name} "
                f"@ {best.endpoint} (rep={best.reputation_score})"
            )
        else:
            logger.warning(f"No active agent found for capability '{capability}'")

        return best

    # ─────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────

    def _tx_params(self) -> dict:
        return {
            "chainId": config.CHAIN_ID,
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gasPrice": self.w3.eth.gas_price,
            "gas": 300_000,
        }

    def _sign_and_send(self, tx: dict) -> str:
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt["status"] != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")
        return tx_hash.hex()
