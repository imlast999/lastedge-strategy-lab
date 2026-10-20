# LastEdge Strategy Lab — Private Strategies Vault

> **Security & IP Protection Notice:**  
> All files inside this directory (`strategies/vault/`) are strictly ignored by Git in the public repository.  
> This directory is designed to hold your proprietary, licensed, or client-specific trading strategies for Walk Forward Analysis, Monte Carlo simulations, Backtesting, and Exit Research.

---

## 1. How It Works

- **Auto-Discovery:** Whenever Strategy Lab initializes, it dynamically scans `strategies/vault/` for:
  1. Standalone Python strategy files (`*.py`) inheriting from `BaseStrategy`.
  2. Promoted strategy packages (`*.json` manifest sidecars paired with `*.py` code).
- **Symbol Precedence:** Any strategy discovered in this vault automatically overrides the default public strategy for the matching trading symbol (e.g. `XAUUSD`, `EURUSD`, `BTCEUR`) across all research runners.
- **Independent Git Repository:** You can turn this folder into its own standalone, private Git repository:
  ```bash
  cd "c:\LastEdge\LastEdge Strategy Lab\strategies\vault"
  git clone <YOUR_PRIVATE_REPO_URL> .
  ```
  Or run the automated synchronization script from the project root:
  ```bash
  .\sync_vault.bat <YOUR_PRIVATE_REPO_URL>
  ```
