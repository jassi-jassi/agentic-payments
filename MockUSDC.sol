// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title MockUSDC
 * @notice Mock stablecoin for x402 testnet payments.
 *         6 decimals to match real USDC.
 *         Anyone can mint for testing (faucet-style).
 */
contract MockUSDC is ERC20, Ownable {

    uint8 private constant DECIMALS = 6;
    uint256 public constant FAUCET_AMOUNT = 1000 * 10**6; // 1000 USDC per claim
    mapping(address => uint256) public lastFaucetClaim;
    uint256 public constant FAUCET_COOLDOWN = 24 hours;

    event FaucetClaimed(address indexed recipient, uint256 amount);

    constructor() ERC20("Mock USDC", "mUSDC") Ownable(msg.sender) {
        // Mint initial supply to deployer
        _mint(msg.sender, 10_000_000 * 10**DECIMALS);
    }

    function decimals() public pure override returns (uint8) {
        return DECIMALS;
    }

    /**
     * @notice Claim test USDC from faucet (once per 24h per address)
     */
    function faucet() external {
        require(
            block.timestamp >= lastFaucetClaim[msg.sender] + FAUCET_COOLDOWN,
            "Faucet cooldown: wait 24h"
        );
        lastFaucetClaim[msg.sender] = block.timestamp;
        _mint(msg.sender, FAUCET_AMOUNT);
        emit FaucetClaimed(msg.sender, FAUCET_AMOUNT);
    }

    /**
     * @notice Admin mint for demo setup
     */
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }
}
