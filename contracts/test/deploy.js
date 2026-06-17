const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`\n🚀 Deploying to: ${network.name}`);
  console.log(`   Deployer: ${deployer.address}`);
  console.log(`   Balance:  ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} AVAX\n`);

  // 1. Deploy MockUSDC
  console.log("Deploying MockUSDC...");
  const MockUSDC = await ethers.getContractFactory("MockUSDC");
  const mockUSDC = await MockUSDC.deploy();
  await mockUSDC.waitForDeployment();
  const usdcAddress = await mockUSDC.getAddress();
  console.log(`✅ MockUSDC deployed: ${usdcAddress}`);

  // 2. Deploy AgentRegistry
  console.log("Deploying AgentRegistry...");
  const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
  const registry = await AgentRegistry.deploy();
  await registry.waitForDeployment();
  const registryAddress = await registry.getAddress();
  console.log(`✅ AgentRegistry deployed: ${registryAddress}`);

  // 3. Save addresses to .env.deployed and deployments.json
  const deployments = {
    network: network.name,
    chainId: network.config.chainId,
    deployedAt: new Date().toISOString(),
    contracts: {
      AgentRegistry: registryAddress,
      MockUSDC: usdcAddress,
    },
    deployer: deployer.address,
  };

  const deploymentsPath = path.join(__dirname, "../../deployments.json");
  fs.writeFileSync(deploymentsPath, JSON.stringify(deployments, null, 2));
  console.log(`\n📄 Deployment info saved to deployments.json`);

  // 4. Print .env additions
  console.log("\n─────────────────────────────────────────────");
  console.log("Add these to your .env file:");
  console.log("─────────────────────────────────────────────");
  console.log(`AGENT_REGISTRY_ADDRESS=${registryAddress}`);
  console.log(`MOCK_USDC_ADDRESS=${usdcAddress}`);
  console.log("─────────────────────────────────────────────\n");

  // 5. Explorer links
  const explorerBase = network.name === "fuji"
    ? "https://testnet.snowtrace.io/address"
    : "https://snowtrace.io/address";
  console.log("🔗 Explorer links:");
  console.log(`   AgentRegistry: ${explorerBase}/${registryAddress}`);
  console.log(`   MockUSDC:      ${explorerBase}/${usdcAddress}\n`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
