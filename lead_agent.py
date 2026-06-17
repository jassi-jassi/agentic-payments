"""
Lead Agent — Orchestrator
──────────────────────────
1. Receives a user query
2. Discovers best specialist agents via ERC-8004 registry (on-chain)
3. Decomposes query into 3 subtasks
4. Dispatches each subtask to the right specialist via x402 HTTP payment
5. Aggregates results using LLM
6. Submits on-chain reputation feedback for each specialist
7. Returns final structured report
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any

from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from agents.shared.config import (
    LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    X402_PAYMENT_AMOUNT_WEI,
    DATA_FETCH_AGENT_URL, ANALYSIS_AGENT_URL, REPORT_AGENT_URL,
    DATA_FETCH_AGENT_WALLET, ANALYSIS_AGENT_WALLET, REPORT_AGENT_WALLET,
)
from agents.shared.x402_client import X402Client, X402PaymentError
from agents.shared.registry_client import RegistryClient, AgentInfo

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    specialist_name: str
    specialist_wallet: str
    task: str
    job_id: bytes | None = None
    result: dict | None = None
    feedback_score: int = 5
    payment_tx: str = ""


@dataclass
class OrchestrationResult:
    query: str
    final_report: str
    jobs: list[JobRecord] = field(default_factory=list)
    total_paid_usdc: float = 0.0
    on_chain_feedback_txs: list[str] = field(default_factory=list)


class LeadAgent:
    """
    Orchestrates the full multi-agent job pipeline.
    Uses ERC-8004 for discovery and x402 for payment.
    """

    def __init__(self):
        self.llm = self._init_llm()
        self.x402 = X402Client()
        self.registry = RegistryClient()
        logger.info("LeadAgent initialized")

    # ─────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────

    def run(self, query: str) -> OrchestrationResult:
        """
        Full pipeline: discover → decompose → dispatch → aggregate → feedback.
        """
        logger.info(f"LeadAgent.run() | query={query!r}")
        result = OrchestrationResult(query=query)

        # 1. Discover specialists on-chain via ERC-8004
        specialists = self._discover_specialists()

        # 2. Decompose the query into 3 subtasks
        subtasks = self._decompose_query(query)
        logger.info(f"Subtasks: {subtasks}")

        # 3. Dispatch each subtask with x402 payment
        jobs = []

        # --- Data Fetch ---
        data_specialist = specialists.get("data_fetch")
        data_job = self._dispatch_job(
            task_description=subtasks["data_fetch"],
            specialist_info=data_specialist,
            endpoint=DATA_FETCH_AGENT_URL + "/fetch",
            fallback_wallet=DATA_FETCH_AGENT_WALLET,
            payload={"query": query, "task": subtasks["data_fetch"]},
        )
        jobs.append(data_job)

        # --- Analysis ---
        analysis_specialist = specialists.get("analysis")
        analysis_job = self._dispatch_job(
            task_description=subtasks["analysis"],
            specialist_info=analysis_specialist,
            endpoint=ANALYSIS_AGENT_URL + "/analyze",
            fallback_wallet=ANALYSIS_AGENT_WALLET,
            payload={
                "query": query,
                "task": subtasks["analysis"],
                "data": data_job.result,
            },
        )
        jobs.append(analysis_job)

        # --- Report ---
        report_specialist = specialists.get("report")
        report_job = self._dispatch_job(
            task_description=subtasks["report"],
            specialist_info=report_specialist,
            endpoint=REPORT_AGENT_URL + "/report",
            fallback_wallet=REPORT_AGENT_WALLET,
            payload={
                "query": query,
                "task": subtasks["report"],
                "data": data_job.result,
                "analysis": analysis_job.result,
            },
        )
        jobs.append(report_job)

        result.jobs = jobs
        result.total_paid_usdc = sum(
            job.result.get("_x402_payment", {}).get("amount_usdc", 0)
            for job in jobs if job.result
        )

        # 4. Aggregate final answer using LLM
        result.final_report = self._aggregate_results(query, jobs)

        # 5. Write reputation feedback on-chain for each specialist
        feedback_txs = self._submit_all_feedback(jobs)
        result.on_chain_feedback_txs = feedback_txs

        logger.info("LeadAgent pipeline complete")
        return result

    # ─────────────────────────────────────────────
    # Discovery (ERC-8004)
    # ─────────────────────────────────────────────

    def _discover_specialists(self) -> dict[str, AgentInfo | None]:
        """
        Query the on-chain registry for the best specialist per capability.
        Falls back gracefully if registry is empty (useful in local dev).
        """
        specialists = {}
        capability_map = {
            "data_fetch": "price_feed",
            "analysis": "ml_analysis",
            "report": "report_generation",
        }
        for role, capability in capability_map.items():
            try:
                agent = self.registry.discover_best_agent(capability, min_reputation=400)
                specialists[role] = agent
                if agent:
                    logger.info(f"Discovered {role}: {agent.name} (rep={agent.reputation_score})")
                else:
                    logger.warning(f"No on-chain agent found for {role}, using env defaults")
            except Exception as e:
                logger.warning(f"Registry lookup failed for {role}: {e}")
                specialists[role] = None
        return specialists

    # ─────────────────────────────────────────────
    # Task Decomposition (LLM)
    # ─────────────────────────────────────────────

    def _decompose_query(self, query: str) -> dict[str, str]:
        """Use LLM to break the query into 3 specialist subtasks."""
        prompt = f"""You are an orchestrator AI. Break this user query into exactly 3 subtasks for specialist agents.

User query: "{query}"

Return a JSON object with exactly these keys:
- "data_fetch": what data the DataFetchAgent should retrieve (prices, news, on-chain data, etc.)
- "analysis": what the AnalysisAgent should compute (trends, signals, scores, predictions)
- "report": what the ReportAgent should produce (format, structure, key takeaways)

Respond with ONLY the JSON object, no explanation."""

        response = self.llm.invoke([
            SystemMessage(content="You decompose tasks for a multi-agent AI system. Always respond with valid JSON only."),
            HumanMessage(content=prompt),
        ])

        import json, re
        text = response.content.strip()
        # Strip markdown code fences if present
        text = re.sub(r"```json|```", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON decomposition, using defaults")
            return {
                "data_fetch": f"Fetch relevant market data for: {query}",
                "analysis": f"Analyse the fetched data and generate insights for: {query}",
                "report": f"Write a concise structured report for: {query}",
            }

    # ─────────────────────────────────────────────
    # Job Dispatch (x402)
    # ─────────────────────────────────────────────

    def _dispatch_job(
        self,
        task_description: str,
        specialist_info: AgentInfo | None,
        endpoint: str,
        fallback_wallet: str,
        payload: dict,
    ) -> JobRecord:
        """
        1. Record job on-chain (ERC-8004)
        2. Call specialist endpoint (x402 auto-pays 402 response)
        3. Return JobRecord
        """
        specialist_wallet = specialist_info.endpoint if specialist_info else fallback_wallet
        # Use on-chain endpoint if discovered, else env fallback
        if specialist_info and specialist_info.endpoint.startswith("http"):
            endpoint_url = specialist_info.endpoint + "/" + endpoint.split("/")[-1]
        else:
            endpoint_url = endpoint

        record = JobRecord(
            specialist_name=specialist_info.name if specialist_info else endpoint.split("/")[2],
            specialist_wallet=specialist_info.wallet if specialist_info else fallback_wallet,
            task=task_description,
        )

        # Create job on-chain
        try:
            job_id = self.registry.create_job(
                specialist_address=record.specialist_wallet,
                task_description=task_description,
                payment_amount=X402_PAYMENT_AMOUNT_WEI,
            )
            record.job_id = job_id
            logger.info(f"Job {job_id.hex()[:16]}... created on-chain for {record.specialist_name}")
        except Exception as e:
            logger.warning(f"Could not create on-chain job (non-fatal): {e}")

        # Call specialist with x402 payment
        try:
            result = self.x402.post(endpoint_url, payload)
            record.result = result
            record.feedback_score = 5  # Optimistic default; will adjust on errors
            logger.info(f"Specialist {record.specialist_name} returned result")
        except X402PaymentError as e:
            logger.error(f"x402 payment failed for {record.specialist_name}: {e}")
            record.result = {"error": str(e)}
            record.feedback_score = 1
        except Exception as e:
            logger.error(f"Specialist call failed for {record.specialist_name}: {e}")
            record.result = {"error": str(e)}
            record.feedback_score = 2

        return record

    # ─────────────────────────────────────────────
    # Aggregation (LLM)
    # ─────────────────────────────────────────────

    def _aggregate_results(self, query: str, jobs: list[JobRecord]) -> str:
        """Combine all specialist outputs into a final answer."""
        import json

        results_summary = "\n\n".join([
            f"### {job.specialist_name}\nTask: {job.task}\nResult:\n{json.dumps(job.result, indent=2)}"
            for job in jobs
        ])

        response = self.llm.invoke([
            SystemMessage(content=(
                "You are a senior analyst synthesizing outputs from specialist AI agents. "
                "Produce a clear, structured final report with: "
                "1) Key Findings, 2) Analysis Summary, 3) Recommendation, 4) Confidence Level."
            )),
            HumanMessage(content=(
                f"Original query: {query}\n\n"
                f"Specialist agent outputs:\n{results_summary}\n\n"
                "Synthesize these into a final report for the user."
            )),
        ])
        return response.content

    # ─────────────────────────────────────────────
    # Reputation Feedback (ERC-8004)
    # ─────────────────────────────────────────────

    def _submit_all_feedback(self, jobs: list[JobRecord]) -> list[str]:
        """Submit on-chain reputation feedback for each completed job."""
        tx_hashes = []
        for job in jobs:
            if job.job_id is None:
                continue
            try:
                # Mark job complete on behalf of specialist (demo shortcut)
                # In production the specialist would call completeJob themselves
                tx = self.registry.complete_job(job.job_id)
                logger.info(f"Job marked complete: {tx}")

                fb_tx = self.registry.submit_feedback(job.job_id, job.feedback_score)
                tx_hashes.append(fb_tx)
                logger.info(
                    f"Feedback submitted for {job.specialist_name}: "
                    f"score={job.feedback_score} tx={fb_tx}"
                )
            except Exception as e:
                logger.warning(f"Feedback submission failed for {job.specialist_name}: {e}")
        return tx_hashes

    # ─────────────────────────────────────────────
    # LLM initialisation
    # ─────────────────────────────────────────────

    def _init_llm(self):
        if LLM_PROVIDER == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model="claude-3-5-haiku-20241022",
                anthropic_api_key=ANTHROPIC_API_KEY,
                temperature=0.2,
            )
        # Default: OpenAI
        return ChatOpenAI(
            model=LLM_MODEL,
            openai_api_key=OPENAI_API_KEY,
            temperature=0.2,
        )
