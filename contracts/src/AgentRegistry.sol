// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title AgentRegistry
 * @notice Implements ERC-8004 — on-chain identity, reputation, and validation
 *         for autonomous AI agents in the Agentic Payments system.
 *
 * @dev Identity Registry: agents register with metadata (name, endpoint, capabilities)
 *      Reputation Registry: score updated after each job via feedback
 *      Validation Registry: track completed/validated work history
 */
contract AgentRegistry is Ownable, ReentrancyGuard {

    // ─────────────────────────────────────────────
    // Data Structures
    // ─────────────────────────────────────────────

    enum AgentStatus { Inactive, Active, Suspended }

    struct AgentIdentity {
        address wallet;          // Agent's wallet address (receives x402 payments)
        string name;             // Human-readable name e.g. "DataFetchAgent-v1"
        string endpoint;         // HTTP endpoint e.g. "https://agent.example.com"
        string[] capabilities;   // e.g. ["price_feed", "sentiment"]
        AgentStatus status;
        uint256 registeredAt;
        uint256 reputationScore; // 0–1000 (starts at 500)
        uint256 jobsCompleted;
        uint256 jobsFailed;
        uint256 totalEarned;     // in wei (mock USDC units)
    }

    struct Job {
        bytes32 jobId;
        address requesterAgent;  // Lead Agent that hired this specialist
        address specialistAgent; // Agent hired for the job
        string taskDescription;
        uint256 paymentAmount;
        bool completed;
        bool validated;
        uint8 feedbackScore;     // 1–5
        uint256 createdAt;
        uint256 completedAt;
    }

    // ─────────────────────────────────────────────
    // State
    // ─────────────────────────────────────────────

    mapping(address => AgentIdentity) public agents;
    mapping(bytes32 => Job) public jobs;
    address[] public agentList;
    bytes32[] public jobList;

    uint256 public constant INITIAL_REPUTATION = 500;
    uint256 public constant MAX_REPUTATION = 1000;
    uint256 public constant MIN_REPUTATION = 0;
    uint256 public constant REPUTATION_REWARD = 10;  // per successful job
    uint256 public constant REPUTATION_PENALTY = 20; // per failed job

    // ─────────────────────────────────────────────
    // Events
    // ─────────────────────────────────────────────

    event AgentRegistered(address indexed wallet, string name, string endpoint);
    event AgentUpdated(address indexed wallet, string endpoint);
    event AgentSuspended(address indexed wallet);
    event JobCreated(bytes32 indexed jobId, address requester, address specialist, uint256 payment);
    event JobCompleted(bytes32 indexed jobId, address specialist);
    event JobValidated(bytes32 indexed jobId, uint8 feedbackScore);
    event ReputationUpdated(address indexed agent, uint256 oldScore, uint256 newScore);

    // ─────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────

    constructor() Ownable(msg.sender) {}

    // ─────────────────────────────────────────────
    // Identity Registry
    // ─────────────────────────────────────────────

    /**
     * @notice Register a new AI agent on-chain.
     * @param name        Human-readable name
     * @param endpoint    HTTP/S endpoint where the agent serves requests
     * @param capabilities List of capability strings
     */
    function registerAgent(
        string calldata name,
        string calldata endpoint,
        string[] calldata capabilities
    ) external {
        require(agents[msg.sender].wallet == address(0), "Agent already registered");
        require(bytes(name).length > 0, "Name required");
        require(bytes(endpoint).length > 0, "Endpoint required");

        agents[msg.sender] = AgentIdentity({
            wallet: msg.sender,
            name: name,
            endpoint: endpoint,
            capabilities: capabilities,
            status: AgentStatus.Active,
            registeredAt: block.timestamp,
            reputationScore: INITIAL_REPUTATION,
            jobsCompleted: 0,
            jobsFailed: 0,
            totalEarned: 0
        });

        agentList.push(msg.sender);
        emit AgentRegistered(msg.sender, name, endpoint);
    }

    /**
     * @notice Update agent endpoint (e.g. after redeployment)
     */
    function updateEndpoint(string calldata newEndpoint) external {
        require(agents[msg.sender].wallet != address(0), "Not registered");
        agents[msg.sender].endpoint = newEndpoint;
        emit AgentUpdated(msg.sender, newEndpoint);
    }

    /**
     * @notice Admin: suspend a misbehaving agent
     */
    function suspendAgent(address agent) external onlyOwner {
        agents[agent].status = AgentStatus.Suspended;
        emit AgentSuspended(agent);
    }

    // ─────────────────────────────────────────────
    // Validation / Job Registry
    // ─────────────────────────────────────────────

    /**
     * @notice Lead Agent records a new job assignment on-chain before payment.
     */
    function createJob(
        address specialist,
        string calldata taskDescription,
        uint256 paymentAmount
    ) external returns (bytes32 jobId) {
        require(agents[msg.sender].wallet != address(0), "Requester not registered");
        require(agents[specialist].status == AgentStatus.Active, "Specialist not active");

        jobId = keccak256(abi.encodePacked(
            msg.sender, specialist, taskDescription, block.timestamp, jobList.length
        ));

        jobs[jobId] = Job({
            jobId: jobId,
            requesterAgent: msg.sender,
            specialistAgent: specialist,
            taskDescription: taskDescription,
            paymentAmount: paymentAmount,
            completed: false,
            validated: false,
            feedbackScore: 0,
            createdAt: block.timestamp,
            completedAt: 0
        });

        jobList.push(jobId);
        emit JobCreated(jobId, msg.sender, specialist, paymentAmount);
    }

    /**
     * @notice Specialist agent marks a job complete.
     */
    function completeJob(bytes32 jobId) external {
        Job storage job = jobs[jobId];
        require(job.specialistAgent == msg.sender, "Not the specialist for this job");
        require(!job.completed, "Already completed");

        job.completed = true;
        job.completedAt = block.timestamp;
        agents[msg.sender].jobsCompleted++;
        agents[msg.sender].totalEarned += job.paymentAmount;

        emit JobCompleted(jobId, msg.sender);
    }

    /**
     * @notice Lead Agent submits feedback after validating specialist output.
     * @param feedbackScore 1 (poor) to 5 (excellent)
     */
    function submitFeedback(bytes32 jobId, uint8 feedbackScore) external nonReentrant {
        require(feedbackScore >= 1 && feedbackScore <= 5, "Score must be 1-5");
        Job storage job = jobs[jobId];
        require(job.requesterAgent == msg.sender, "Only requester can submit feedback");
        require(job.completed, "Job not completed yet");
        require(!job.validated, "Feedback already submitted");

        job.validated = true;
        job.feedbackScore = feedbackScore;

        // Update reputation
        address specialist = job.specialistAgent;
        uint256 oldScore = agents[specialist].reputationScore;
        uint256 newScore;

        if (feedbackScore >= 4) {
            // Good job: reward
            newScore = oldScore + REPUTATION_REWARD > MAX_REPUTATION
                ? MAX_REPUTATION
                : oldScore + REPUTATION_REWARD;
        } else if (feedbackScore <= 2) {
            // Bad job: penalise
            agents[specialist].jobsFailed++;
            newScore = oldScore < REPUTATION_PENALTY
                ? MIN_REPUTATION
                : oldScore - REPUTATION_PENALTY;
        } else {
            // Neutral: no change
            newScore = oldScore;
        }

        agents[specialist].reputationScore = newScore;
        emit ReputationUpdated(specialist, oldScore, newScore);
        emit JobValidated(jobId, feedbackScore);
    }

    // ─────────────────────────────────────────────
    // View / Discovery
    // ─────────────────────────────────────────────

    /**
     * @notice Get all registered agents (for discovery).
     */
    function getAllAgents() external view returns (address[] memory) {
        return agentList;
    }

    /**
     * @notice Get active agents with reputation above a threshold.
     * @param minReputation Minimum reputation score (0–1000)
     */
    function getAgentsByReputation(uint256 minReputation)
        external view returns (address[] memory filtered)
    {
        uint256 count = 0;
        for (uint256 i = 0; i < agentList.length; i++) {
            AgentIdentity storage a = agents[agentList[i]];
            if (a.status == AgentStatus.Active && a.reputationScore >= minReputation) {
                count++;
            }
        }
        filtered = new address[](count);
        uint256 j = 0;
        for (uint256 i = 0; i < agentList.length; i++) {
            AgentIdentity storage a = agents[agentList[i]];
            if (a.status == AgentStatus.Active && a.reputationScore >= minReputation) {
                filtered[j++] = agentList[i];
            }
        }
    }

    /**
     * @notice Get an agent's capabilities.
     */
    function getCapabilities(address agent) external view returns (string[] memory) {
        return agents[agent].capabilities;
    }

    /**
     * @notice Get all job IDs.
     */
    function getAllJobs() external view returns (bytes32[] memory) {
        return jobList;
    }
}
