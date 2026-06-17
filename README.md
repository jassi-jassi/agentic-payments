# 🤖 Agentic Payments — Agents That Hire Agents

> A multi-agent system where a Lead Agent autonomously decomposes tasks, discovers specialist agents via **ERC-8004** on-chain identity, pays them via **x402** HTTP micropayments, and writes reputation feedback — all on **Avalanche C-Chain (Fuji Testnet)**.

Built for the **Speedrun: Agentic Payments** hackathon by Team1 India.

---

## 🏗 Architecture

```
User Query
    │
    ▼
Lead Agent (Orchestrator)
    ├── Reads ERC-8004 registry → discovers specialist agents by reputation
    ├── Decomposes task into subtasks
    ├── Calls specialist agent endpoints (FastAPI)
    │       └── x402 micropayment per HTTP call (stablecoin on Avalanche)
    ├── Aggregates results
    ├── Writes reputation feedback on-chain (ERC-8004)
    └── Returns final output
```

**Specialist Agents:**
- `DataFetchAgent` — fetches prices, oracle data, market sentiment
- `AnalysisAgent` — ML scoring, feature engineering, signal detection
- `ReportAgent` — formats and delivers the final structured report

---

## 📁 Project Structure

```
agentic-payments/
├── contracts/              # Solidity smart contracts (Hardhat)
│   ├── src/
│   │   ├── AgentRegistry.sol       # ERC-8004 identity + reputation registry
│   │   └── MockUSDC.sol            # Mock stablecoin for testnet payments
│   ├── scripts/
│   │   └── deploy.js               # Deploy to Fuji testnet
│   └── test/
│       └── AgentRegistry.test.js
├── agents/
│   ├── shared/
│   │   ├── x402_client.py          # x402 payment client
│   │   ├── registry_client.py      # ERC-8004 on-chain calls
│   │   └── config.py               # Env + chain config
│   ├── lead/
│   │   └── lead_agent.py           # Orchestrator (LangChain)
│   └── specialist/
│       ├── data_fetch_agent.py     # FastAPI: data fetching
│       ├── analysis_agent.py       # FastAPI: ML analysis
│       └── report_agent.py         # FastAPI: report generation
├── api/
│   └── main.py                     # Entry point API (triggers lead agent)
├── dashboard/
│   └── index.html                  # Simple demo dashboard
├── scripts/
│   ├── register_agents.py          # Register agents on-chain
│   ├── fund_agents.py              # Fund agent wallets with test AVAX
│   └── run_demo.py                 # End-to-end demo script
├── .env.example
├── requirements.txt
├── hardhat.config.js
└── package.json
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Node.js 18+, Python 3.10+
- MetaMask with Fuji testnet AVAX ([faucet](https://faucet.avax.network/))
- API keys: OpenAI or Anthropic

### 2. Install dependencies

```bash
# Solidity / Hardhat
npm install

# Python
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Fill in: PRIVATE_KEY, RPC_URL, OPENAI_API_KEY (or ANTHROPIC_API_KEY)
```

### 4. Deploy contracts to Fuji

```bash
npx hardhat run contracts/scripts/deploy.js --network fuji
# Copy deployed addresses into .env
```

### 5. Register specialist agents on-chain

```bash
python scripts/register_agents.py
```

### 6. Start specialist agent servers

```bash
# Terminal 1
uvicorn agents.specialist.data_fetch_agent:app --port 8001

# Terminal 2
uvicorn agents.specialist.analysis_agent:app --port 8002

# Terminal 3
uvicorn agents.specialist.report_agent:app --port 8003
```

### 7. Start the main API

```bash
uvicorn api.main:app --port 8000
```

### 8. Run a demo query

```bash
python scripts/run_demo.py
# Or POST to http://localhost:8000/run with {"query": "Analyze BTC price trend and give me a buy/sell signal"}
```

---

## 🔗 Deployed Contracts (Fuji Testnet)

> Fill these in after deployment:

| Contract | Address |
|---|---|
| AgentRegistry | `0x...` |
| MockUSDC | `0x...` |

---

## 🏆 Judging Criteria Coverage

| Criterion | How we address it |
|---|---|
| Value Proposition | Fully autonomous agent economy — no human in the loop after query |
| Technical Complexity | Both x402 + ERC-8004 integrated; multi-agent LangChain orchestration |
| Avalanche Usage | On-chain registry, reputation, and x402 stablecoin payments on Fuji C-Chain |
| Mainnet Bonus | Deploy same contracts to Avalanche mainnet (optional step in deploy script) |

---

## 📄 License

MIT
