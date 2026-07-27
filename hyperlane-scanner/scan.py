#!/usr/bin/env python3
"""
Static-analysis scanner for the Hyperlane protocol contracts, built for
triaging candidates before submitting to the Hyperlane Immunefi bug bounty
(https://immunefi.com/bug-bounty/hyperlane/).

Pipeline:
  1. Clone (or reuse) the hyperlane-monorepo.
  2. Install its Foundry/Soldeer dependencies and build with forge.
  3. Run Slither against contracts/ only (dependencies, tests and scripts
     are excluded — they are out of bounty scope).
  4. Run a small set of Hyperlane-specific heuristics (regex-based) that
     flag code worth a manual look: access control on message-entry points,
     signature/ECDSA handling, delegatecall, selfdestruct, etc.
  5. Emit a single Markdown report grouped by severity.

This tool does not "find bugs" on its own — it narrows down where to look.
Every finding still needs manual verification and a PoC before it is worth
submitting to Immunefi.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_CLONE_URL = "https://github.com/hyperlane-xyz/hyperlane-monorepo.git"
SEVERITY_ORDER = ["High", "Medium", "Low", "Informational", "Optimization"]

# Slither detectors that are near-always noise on this codebase (OZ-upgradeable
# storage gaps shadowing each other by design, etc.). Filtered out by default;
# pass --no-noise-filter to see everything.
NOISY_DETECTORS = {
    "shadowing-abstract",
    "naming-convention",
    "solc-version",
    "pragma",
}

# Heuristic checklist: (label, regex, why it matters for a bug-bounty review)
CHECKLIST_PATTERNS = [
    (
        "delegatecall",
        re.compile(r"\bdelegatecall\b"),
        "Delegatecall changes storage context; verify the target/calldata can't be attacker-controlled.",
    ),
    (
        "selfdestruct",
        re.compile(r"\bselfdestruct\b"),
        "Self-destructing a contract Hyperlane depends on (Mailbox, ISM, Router) could brick routes.",
    ),
    (
        "ecrecover / signature handling",
        re.compile(r"\becrecover\b|\bECDSA\.recover\b"),
        "Check for signature malleability, missing zero-address checks, and replay across chains/domains.",
    ),
    (
        "low-level call",
        re.compile(r"\.call\{|\.call\("),
        "Unchecked low-level calls can silently fail or allow reentrancy into Mailbox/Router flows.",
    ),
    (
        "external message entry point",
        re.compile(r"function\s+(process|handle|verify)\s*\("),
        "These are the functions attackers control input to (relayers, ISMs); confirm access control "
        "(onlyMailbox / onlyInbox) and replay protection are present and correctly ordered.",
    ),
    (
        "unchecked arithmetic block",
        re.compile(r"\bunchecked\s*\{"),
        "Confirm the surrounding invariants really rule out under/overflow before trusting this block.",
    ),
]

# Directories that are never in the Immunefi smart-contract scope for this repo.
EXCLUDED_DIR_PARTS = {"test", "script", "mock", "dependencies", "lib", "node_modules"}


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})")
    return subprocess.run(cmd, cwd=cwd, check=check)


def ensure_repo(repo_dir: Path, clone_url: str) -> None:
    if repo_dir.exists():
        print(f"Reusing existing checkout at {repo_dir}")
        return
    if shutil.which("git") is None:
        sys.exit("git is required but was not found on PATH")
    run(["git", "clone", "--depth", "1", clone_url, str(repo_dir)], cwd=repo_dir.parent)


def ensure_deps(pkg_dir: Path, skip: bool) -> None:
    if skip:
        return
    if shutil.which("forge") is None:
        sys.exit(
            "forge (Foundry) is required but was not found on PATH.\n"
            "Install it from https://getfoundry.sh, or in network-restricted\n"
            "environments download the release tarball directly from\n"
            "https://github.com/foundry-rs/foundry/releases and put `forge`\n"
            "on PATH."
        )
    run(["forge", "soldeer", "install"], cwd=pkg_dir, check=False)


def run_build(pkg_dir: Path, skip: bool) -> None:
    if skip:
        return
    run(["forge", "build", "--skip", "test", "--skip", "script"], cwd=pkg_dir)


def run_slither(pkg_dir: Path, out_json: Path) -> dict:
    if shutil.which("slither") is None and subprocess.run(
        [sys.executable, "-m", "slither", "--version"], cwd=pkg_dir, capture_output=True
    ).returncode != 0:
        sys.exit(
            "slither is required but was not found.\n"
            "Install it with: pip install -r hyperlane-scanner/requirements.txt"
        )

    config = pkg_dir / "slither.config.json"
    cmd = [sys.executable, "-m", "slither", ".", "--json", str(out_json)]
    if config.exists():
        cmd += ["--config-file", str(config)]
    else:
        cmd += ["--filter-paths", "|".join(EXCLUDED_DIR_PARTS)]

    # Slither exits non-zero when it finds issues -- that's expected, not a failure.
    subprocess.run(cmd, cwd=pkg_dir)

    if not out_json.exists():
        sys.exit("Slither did not produce a JSON report; check the build/compile step above.")
    return json.loads(out_json.read_text())


def is_in_scope(filename: str) -> bool:
    parts = set(Path(filename).parts)
    return not (parts & EXCLUDED_DIR_PARTS)


def parse_slither(data: dict, apply_noise_filter: bool) -> list[dict]:
    findings = []
    for det in data.get("results", {}).get("detectors", []):
        if apply_noise_filter and det["check"] in NOISY_DETECTORS:
            continue

        elements = det.get("elements", [])
        rel_files = {
            e["source_mapping"]["filename_relative"]
            for e in elements
            if e.get("source_mapping", {}).get("filename_relative")
        }
        if rel_files and not any(is_in_scope(f) for f in rel_files):
            continue  # entirely in dependencies/test/mock -- not bounty scope

        findings.append(
            {
                "check": det["check"],
                "impact": det.get("impact", "Informational"),
                "confidence": det.get("confidence", "Medium"),
                "description": det.get("description", "").strip(),
                "files": sorted(f for f in rel_files if is_in_scope(f)) or sorted(rel_files),
            }
        )

    findings.sort(key=lambda f: SEVERITY_ORDER.index(f["impact"]) if f["impact"] in SEVERITY_ORDER else 99)
    return findings


def run_checklist(contracts_dir: Path) -> list[dict]:
    hits = []
    for sol_file in sorted(contracts_dir.rglob("*.sol")):
        rel = sol_file.relative_to(contracts_dir.parent)
        if not is_in_scope(str(rel)):
            continue
        text = sol_file.read_text(errors="ignore")
        for label, pattern, why in CHECKLIST_PATTERNS:
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append({"label": label, "file": str(rel), "line": line, "why": why})
    return hits


def render_report(findings: list[dict], checklist: list[dict], out_path: Path) -> None:
    by_impact: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_impact[f["impact"]].append(f)

    lines = [
        "# Hyperlane Contract Scan Report",
        "",
        "Generated by `hyperlane-scanner/scan.py`. This is a triage aid, not a",
        "vulnerability confirmation — every item below needs manual review and,",
        "for High/Critical claims, a working PoC before it's worth submitting to",
        "the [Hyperlane Immunefi program](https://immunefi.com/bug-bounty/hyperlane/).",
        "",
        "## Slither findings (Hyperlane contracts only, dependencies/tests excluded)",
        "",
    ]

    for impact in SEVERITY_ORDER:
        items = by_impact.get(impact, [])
        if not items:
            continue
        lines.append(f"### {impact} ({len(items)})")
        lines.append("")
        for f in items:
            lines.append(f"- **{f['check']}** (confidence: {f['confidence']})")
            for file in f["files"]:
                lines.append(f"  - `{file}`")
            desc = f["description"].replace("\n", "\n  ")
            lines.append(f"  - {desc}")
        lines.append("")

    if not findings:
        lines.append("_No findings after noise filtering — try `--no-noise-filter` for the raw output._")
        lines.append("")

    lines.append("## Manual-review checklist (heuristic, not a static-analysis result)")
    lines.append("")
    lines.append(
        "These are pattern matches meant to point a reviewer at likely-sensitive code "
        "(message entry points, signature handling, low-level calls, etc.), not confirmed issues."
    )
    lines.append("")

    by_label: dict[str, list[dict]] = defaultdict(list)
    for h in checklist:
        by_label[h["label"]].append(h)

    if not checklist:
        lines.append("_No checklist matches found._")
    for label, hits in by_label.items():
        lines.append(f"### {label} ({len(hits)})")
        lines.append(f"_{hits[0]['why']}_")
        lines.append("")
        for h in hits:
            lines.append(f"- `{h['file']}:{h['line']}`")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"\nReport written to {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", default="hyperlane-monorepo", help="Path to clone/reuse the monorepo at")
    ap.add_argument("--clone-url", default=DEFAULT_CLONE_URL)
    ap.add_argument("--package", default="solidity", help="Sub-package inside the monorepo containing contracts")
    ap.add_argument("--out", default="reports/report.md", help="Markdown report output path")
    ap.add_argument("--skip-clone", action="store_true", help="Assume --repo-dir already exists")
    ap.add_argument("--skip-deps", action="store_true", help="Skip `forge soldeer install`")
    ap.add_argument("--skip-build", action="store_true", help="Skip `forge build` (reuse existing out/)")
    ap.add_argument("--no-noise-filter", action="store_true", help="Include noisy/low-value detectors")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    repo_dir = (base / args.repo_dir).resolve()
    out_path = (base / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_clone:
        ensure_repo(repo_dir, args.clone_url)
    pkg_dir = repo_dir / args.package
    if not pkg_dir.exists():
        sys.exit(f"Package directory not found: {pkg_dir}")

    ensure_deps(pkg_dir, args.skip_deps)
    run_build(pkg_dir, args.skip_build)

    slither_json = base / "reports" / "slither_raw.json"
    slither_json.parent.mkdir(parents=True, exist_ok=True)
    data = run_slither(pkg_dir, slither_json)

    findings = parse_slither(data, apply_noise_filter=not args.no_noise_filter)
    checklist = run_checklist(pkg_dir / "contracts")
    render_report(findings, checklist, out_path)


if __name__ == "__main__":
    main()
