"""
run_demo.py
────────────
End-to-end demo of the Agentic Payments system.
Shows the full pipeline: ERC-8004 discovery → x402 payment → result → reputation feedback.

Usage:
    # Make sure all 4 servers are running first, then:
    python scripts/run_demo.py

    # Or pass a custom query:
    python scripts/run_demo.py "Should I buy AVAX right now?"
"""

import sys
import json
import time
import httpx
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.WARNING)  # quiet during demo

API_URL = "http://localhost:8000"

DEMO_QUERIES = [
    "Analyze BTC and ETH price trends and give me a buy/sell signal",
    "What is the current market sentiment for crypto and should I invest?",
    "Give me a full AVAX market analysis with support/resistance levels",
]


def print_banner():
    print()
    print("=" * 60)
    print("  🤖 AGENTIC PAYMENTS DEMO")
    print("  Agents That Hire Agents — x402 + ERC-8004 on Avalanche")
    print("=" * 60)
    print()


def check_servers():
    """Make sure all 4 servers are running."""
    services = {
        "Main API (Lead Agent)": "http://localhost:8000/status",
        "DataFetchAgent":        "http://localhost:8001/health",
        "AnalysisAgent":         "http://localhost:8002/health",
        "ReportAgent":           "http://localhost:8003/health",
    }
    all_ok = True
    print("🔍 Checking services...")
    for name, url in services.items():
        try:
            r = httpx.get(url, timeout=3)
            status = "✅" if r.status_code == 200 else "⚠️ "
            print(f"   {status} {name}")
        except Exception:
            print(f"   ❌ {name} — NOT RUNNING at {url}")
            all_ok = False
    print()
    return all_ok


def run_query(query: str) -> dict:
    print(f"📝 Query: \"{query}\"")
    print()

    steps = [
        "  [1/5] 🔍 Lead Agent discovering specialists via ERC-8004...",
        "  [2/5] 🧩 Decomposing query into subtasks...",
        "  [3/5] 💸 Dispatching to DataFetchAgent (x402 payment)...",
        "  [4/5] 🧠 Dispatching to AnalysisAgent (x402 payment)...",
        "  [5/5] 📄 Dispatching to ReportAgent (x402 payment)...",
    ]

    # Print steps with a small delay for demo effect
    import threading
    stop_event = threading.Event()

    def progress():
        for step in steps:
            if stop_event.is_set():
                break
            print(step)
            time.sleep(1.5)

    t = threading.Thread(target=progress, daemon=True)
    t.start()

    start = time.time()
    try:
        response = httpx.post(
            f"{API_URL}/run",
            json={"query": query},
            timeout=120,
        )
        stop_event.set()
        t.join()
        elapsed = time.time() - start

        if response.status_code != 200:
            print(f"\n❌ API error {response.status_code}: {response.text}")
            return {}

        return response.json()

    except httpx.ConnectError:
        stop_event.set()
        print("\n❌ Could not connect to http://localhost:8000")
        print("   Start the main API first: uvicorn api.main:app --port 8000")
        sys.exit(1)
    except Exception as e:
        stop_event.set()
        print(f"\n❌ Request failed: {e}")
        return {}


def print_results(result: dict):
    if not result:
        return

    print()
    print("─" * 60)
    print("  ✅ PIPELINE COMPLETE")
    print("─" * 60)
    print()

    # Jobs summary
    jobs = result.get("jobs", [])
    print(f"  {'Agent':<25} {'Task (preview)':<30} {'Score'}")
    print(f"  {'─'*24} {'─'*30} {'─'*5}")
    for job in jobs:
        task_preview = (job.get("task", "") or "")[:28] + "…"
        print(f"  {job['specialist']:<25} {task_preview:<30} {job['feedback_score']}/5")

    print()
    total_paid = result.get("total_paid_usdc", 0)
    print(f"  💰 Total paid via x402: ${total_paid:.4f} USDC")

    fb_txs = result.get("on_chain_feedback_txs", [])
    if fb_txs:
        print(f"  🔗 Reputation feedback txs: {len(fb_txs)} written on-chain")
        for tx in fb_txs[:2]:
            short = tx[:20] + "..." if len(tx) > 20 else tx
            print(f"     https://testnet.snowtrace.io/tx/{tx}")

    print()
    print("─" * 60)
    print("  📊 FINAL REPORT")
    print("─" * 60)
    print()

    report = result.get("final_report", "No report generated.")
    print(report)

    print()
    print("─" * 60)
    print("  📦 AGENT OUTPUTS (raw)")
    print("─" * 60)
    for job in jobs:
        preview = job.get("result_preview", "")
        print(f"\n  [{job['specialist']}]")
        print(f"  {preview}")

    print()
    print("=" * 60)
    print("  🏁 Demo complete")
    print(f"  Network: Avalanche Fuji Testnet (chain_id=43113)")
    print(f"  Protocol: x402 micropayments + ERC-8004 identity")
    print("=" * 60)
    print()


def main():
    print_banner()

    if not check_servers():
        print("⚠️  Some services are offline.")
        print("   Start them first (each in a separate terminal):")
        print()
        print("   uvicorn agents.specialist.data_fetch_agent:app --port 8001")
        print("   uvicorn agents.specialist.analysis_agent:app --port 8002")
        print("   uvicorn agents.specialist.report_agent:app --port 8003")
        print("   uvicorn api.main:app --port 8000")
        print()
        ans = input("Continue anyway? (y/N): ").strip().lower()
        if ans != "y":
            sys.exit(0)

    # Use CLI arg or first demo query
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEMO_QUERIES[0]

    result = run_query(query)
    print_results(result)


if __name__ == "__main__":
    main()
