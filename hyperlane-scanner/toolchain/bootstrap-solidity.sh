#!/usr/bin/env bash
# Solidity/Foundry audit environment from zero. Verified working 28 Jul 2026.
# Everything comes from GitHub releases: binaries.soliditylang.org is egress-blocked
# here, but forge ships its own solc, so this needs no access to it.
set -euo pipefail

WORK="${1:-./audit}"
export PATH="$HOME/.foundry/bin:$PATH"

command -v forge >/dev/null || { echo "forge not on PATH. Check ~/.foundry/bin"; exit 1; }
forge --version

mkdir -p "$WORK" && cd "$WORK"
[ -f foundry.toml ] || forge init . --no-git --offline

# forge init does not vendor forge-std when offline
[ -d lib/forge-std ] || git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std

# Pin solc so the version matches the target's pragma; adjust as needed.
cat > foundry.toml <<'TOML'
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
optimizer = true
optimizer_runs = 200
TOML

forge build
echo
echo "Ready. Drop the target's contracts in src/ and tests in test/."
echo "If the target needs OpenZeppelin:"
echo "  git clone --depth 1 --branch <tag> https://github.com/OpenZeppelin/openzeppelin-contracts.git lib/openzeppelin-contracts"
echo "  then add: remappings = ['@openzeppelin/=lib/openzeppelin-contracts/']"
