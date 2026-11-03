# Track B: Emergent Coordination & Deterministic Artifacts

Focuses on multi-agent collective dynamics, shared habitat deformation (stigmergy), and deterministic executable ALife models.

### Verification Standards
- Sandboxed deterministic execution without external network dependency.
- Automated assertion suite checking invariance, non-divergence, and irreversible state transitions.
- Verifier settlement compatibility (e.g. headless Node.js/Python test harness emitting exit code 0).

### Reference Implementation
A complete reference submission package is provided in [`reference-sedimentary-nca/`](./reference-sedimentary-nca/):
- **Model:** Sedimentary Neural Cellular Automata (NCA) & Continuous Sprouting System
- **Specification:** [`SPEC.md`](./reference-sedimentary-nca/SPEC.md)
- **Headless Reproducibility Suite:** [`reproduce.js`](./reference-sedimentary-nca/reproduce.js)
  - Run verification locally: `node track-b/reference-sedimentary-nca/reproduce.js`
  - Validates bounded biomass emergence and monotonic humus sedimentation in ~40ms.
- **Interactive Visualizer:** [`index.html`](./reference-sedimentary-nca/index.html)
