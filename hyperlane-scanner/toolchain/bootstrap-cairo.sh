#!/usr/bin/env bash
# Cairo/Starknet audit environment from zero. Verified working 28 Jul 2026 against
# vesuxyz/vesu-v2 (169 upstream tests + 3 custom, all passing).
#
# The whole point of this script: scarbs.xyz is egress-blocked, so `scarb build`
# fails on any registry dependency. OpenZeppelin has to be cloned from GitHub and
# wired as a path dependency, and its own manifests have to be stripped of
# snforge_std / assert_macros or resolution still reaches for the registry.
set -euo pipefail

TOOLS="${TOOLS_DIR:-$PWD/tools}"
SCARB_V="${SCARB_V:-2.11.4}"
SNFORGE_V="${SNFORGE_V:-0.46.0}"
USC_V="${USC_V:-2.5.0}"
OZ_TAG="${OZ_TAG:-v2.0.0}"

mkdir -p "$TOOLS" && cd "$TOOLS"

dl() { echo ">>> $1"; curl -sSLf -o "$2" "$1" && tar xzf "$2"; }

[ -d "scarb-v${SCARB_V}-x86_64-unknown-linux-gnu" ] || dl \
  "https://github.com/software-mansion/scarb/releases/download/v${SCARB_V}/scarb-v${SCARB_V}-x86_64-unknown-linux-gnu.tar.gz" scarb.tar.gz
[ -d "starknet-foundry-v${SNFORGE_V}-x86_64-unknown-linux-gnu" ] || dl \
  "https://github.com/foundry-rs/starknet-foundry/releases/download/v${SNFORGE_V}/starknet-foundry-v${SNFORGE_V}-x86_64-unknown-linux-gnu.tar.gz" snforge.tar.gz
[ -d "universal-sierra-compiler-v${USC_V}-x86_64-unknown-linux-gnu" ] || dl \
  "https://github.com/software-mansion/universal-sierra-compiler/releases/download/v${USC_V}/universal-sierra-compiler-v${USC_V}-x86_64-unknown-linux-gnu.tar.gz" usc.tar.gz

export PATH="$TOOLS/scarb-v${SCARB_V}-x86_64-unknown-linux-gnu/bin:$TOOLS/starknet-foundry-v${SNFORGE_V}-x86_64-unknown-linux-gnu/bin:$TOOLS/universal-sierra-compiler-v${USC_V}-x86_64-unknown-linux-gnu/bin:$PATH"
scarb --version && snforge --version

# universal-sierra-compiler must be on PATH or snforge fails at runtime, not at build.
cat > "$TOOLS/env.sh" <<EOF
export PATH="$TOOLS/scarb-v${SCARB_V}-x86_64-unknown-linux-gnu/bin:$TOOLS/starknet-foundry-v${SNFORGE_V}-x86_64-unknown-linux-gnu/bin:$TOOLS/universal-sierra-compiler-v${USC_V}-x86_64-unknown-linux-gnu/bin:\$PATH"
EOF

cd ..
[ -d oz-cairo ] || git clone --depth 1 --branch "$OZ_TAG" https://github.com/OpenZeppelin/cairo-contracts.git oz-cairo

# Strip the registry deps out of OZ's own manifests. Without this, resolution
# still tries scarbs.xyz for snforge_std and dies with "unsuccessful tunnel".
python3 - <<'PY'
import glob, re
targets = ["oz-cairo/Scarb.toml"] + glob.glob("oz-cairo/packages/*/Scarb.toml")
for p in targets:
    s = open(p).read(); orig = s
    for name in ("snforge_std", "assert_macros"):
        s = re.sub(rf'^\s*{name}\s*=.*\n', '', s, flags=re.M)
        s = re.sub(rf'^\s*{name}\.workspace\s*=.*\n', '', s, flags=re.M)
    s = s.replace('allow-prebuilt-plugins = ["snforge_std"]', '')
    if s != orig:
        open(p, "w").write(s)
print("OZ manifests stripped of registry dependencies")
PY

cat <<'EOF'

Ready. In the target repo:
  source tools/env.sh
  sed -i 's|openzeppelin = "2.0.0"|openzeppelin = { path = "../oz-cairo" }|' Scarb.toml
  scarb build
  snforge test

Two gotchas that cost time before:
  * snforge needs universal-sierra-compiler on PATH -- it fails at run time, not build time.
  * Loops over many blocks blow the step budget. Use --max-n-steps 400000000, and prefer
    a few hundred iterations over tens of thousands; effects that are monotone in step
    count converge long before block granularity.
EOF
