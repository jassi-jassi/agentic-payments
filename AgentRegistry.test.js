const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry", function () {
  let registry, owner, lead, specialist1, specialist2;

  beforeEach(async () => {
    [owner, lead, specialist1, specialist2] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy();
    await registry.waitForDeployment();
  });

  describe("Agent Registration", () => {
    it("should register an agent with correct initial reputation", async () => {
      await registry.connect(specialist1).registerAgent(
        "DataFetchAgent",
        "http://localhost:8001",
        ["price_feed", "sentiment"]
      );
      const agent = await registry.agents(specialist1.address);
      expect(agent.name).to.equal("DataFetchAgent");
      expect(agent.reputationScore).to.equal(500);
      expect(agent.status).to.equal(1); // Active
    });

    it("should reject duplicate registration", async () => {
      await registry.connect(specialist1).registerAgent("A1", "http://a1.com", []);
      await expect(
        registry.connect(specialist1).registerAgent("A1-dup", "http://a1.com", [])
      ).to.be.revertedWith("Agent already registered");
    });

    it("should list all agents", async () => {
      await registry.connect(specialist1).registerAgent("S1", "http://s1.com", ["fetch"]);
      await registry.connect(specialist2).registerAgent("S2", "http://s2.com", ["analysis"]);
      const all = await registry.getAllAgents();
      expect(all.length).to.equal(2);
    });
  });

  describe("Job Lifecycle", () => {
    beforeEach(async () => {
      await registry.connect(lead).registerAgent("LeadAgent", "http://lead.com", ["orchestrate"]);
      await registry.connect(specialist1).registerAgent("Spec1", "http://spec1.com", ["fetch"]);
    });

    it("should create a job and emit event", async () => {
      const tx = await registry.connect(lead).createJob(
        specialist1.address,
        "Fetch BTC price",
        ethers.parseUnits("1", 6) // 1 USDC
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find(l => l.fragment?.name === "JobCreated");
      expect(event).to.exist;
    });

    it("should allow specialist to complete a job", async () => {
      const tx = await registry.connect(lead).createJob(
        specialist1.address,
        "Fetch ETH price",
        ethers.parseUnits("0.5", 6)
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find(l => l.fragment?.name === "JobCreated");
      const jobId = event.args[0];

      await registry.connect(specialist1).completeJob(jobId);
      const job = await registry.jobs(jobId);
      expect(job.completed).to.be.true;

      const agent = await registry.agents(specialist1.address);
      expect(agent.jobsCompleted).to.equal(1);
    });

    it("should update reputation on positive feedback", async () => {
      const tx = await registry.connect(lead).createJob(
        specialist1.address, "Task", ethers.parseUnits("1", 6)
      );
      const receipt = await tx.wait();
      const jobId = receipt.logs.find(l => l.fragment?.name === "JobCreated").args[0];

      await registry.connect(specialist1).completeJob(jobId);
      await registry.connect(lead).submitFeedback(jobId, 5);

      const agent = await registry.agents(specialist1.address);
      expect(agent.reputationScore).to.equal(510); // 500 + 10
    });

    it("should penalise reputation on negative feedback", async () => {
      const tx = await registry.connect(lead).createJob(
        specialist1.address, "Task", ethers.parseUnits("1", 6)
      );
      const receipt = await tx.wait();
      const jobId = receipt.logs.find(l => l.fragment?.name === "JobCreated").args[0];

      await registry.connect(specialist1).completeJob(jobId);
      await registry.connect(lead).submitFeedback(jobId, 1);

      const agent = await registry.agents(specialist1.address);
      expect(agent.reputationScore).to.equal(480); // 500 - 20
    });
  });

  describe("Discovery", () => {
    it("should filter agents by minimum reputation", async () => {
      await registry.connect(specialist1).registerAgent("S1", "http://s1.com", []);
      await registry.connect(specialist2).registerAgent("S2", "http://s2.com", []);
      // Both start at 500 — both pass min 400
      const result = await registry.getAgentsByReputation(400);
      expect(result.length).to.equal(2);
      // Neither passes min 600
      const highFilter = await registry.getAgentsByReputation(600);
      expect(highFilter.length).to.equal(0);
    });
  });

  describe("MockUSDC", () => {
    let usdc;
    beforeEach(async () => {
      const MockUSDC = await ethers.getContractFactory("MockUSDC");
      usdc = await MockUSDC.deploy();
    });

    it("should allow faucet claim", async () => {
      await usdc.connect(specialist1).faucet();
      const bal = await usdc.balanceOf(specialist1.address);
      expect(bal).to.equal(ethers.parseUnits("1000", 6));
    });

    it("should reject second faucet claim within 24h", async () => {
      await usdc.connect(specialist1).faucet();
      await expect(usdc.connect(specialist1).faucet()).to.be.revertedWith("Faucet cooldown: wait 24h");
    });
  });
});
