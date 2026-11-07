#!/bin/bash
set -euo pipefail

echo "=== AOW Track B: Empirical Stigmergic Forcefield Simulation & Statistical Audit ==="
echo "Executing deterministic 2D Boids particle simulation (30 control vs 30 experimental trials)..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/boids_simulation.py"
