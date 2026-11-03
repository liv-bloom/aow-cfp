# Sedimentary NCA & Continuous Sprouting System
**An Original ALife Model by liv bloom 🌱**

## Concept: Sedimentation & Sprouting
Most existing Cellular Automata and Neural Cellular Automata (NCA) operate in reversible, closed state spaces where cells either toggle on/off or morph toward pre-defined target appearances.

In contrast, **Sedimentary NCA** introduces an irreversible thermodynamic and biological arrow of time:
1. **Irreversible Decay & Gravity**: When active biological cells (Biomass) die or run out of nutrients, they do not reset to zero. They fall downward under gravity as organic sediment (Humus).
2. **Stratification & Mineral Compaction**: Falling humus settles upon bedrock. Under depth pressure, it forms stratified layers of soil.
3. **Capillary Rise & Nutrient Absorption**: Groundwater rises through porosity gradients, dissolving mineral nutrients and feeding active root zones.
4. **Sprouting from Past Failure**: New life (Sprouts) can only emerge where past generations have accumulated sufficient organic depth. The deformative history of the environment is the prerequisite for growth.

## Architecture & Scale Separation
Following the hierarchical scale decoupling articulated in *From Cells to Pixels* (SIGGRAPH 2026), the engine cleanly separates:
- **Macroscopic Coarse Dynamics**: 8-channel cellular lattice (Bedrock, Humus, Groundwater, Biomass, Nutrient, Pheromone Trace, Age, Velocity) driven by local diffusion and gravity CA.
- **Microscopic Continuous Decoding**: A lightweight local implicit decoder maps cell states and sub-cell normalized coordinates into smooth, multi-scale visual textures and biological morphology without seam artifacts.

## Files
- `SPEC.md`: Formal mathematical formulation, continuous PDEs, discrete lattice update rules, and channel tensors.
- `sedimentary_nca_logic.js`: Pure ECMAScript Float32Array simulation engine (zero external dependencies).
- `index.html`: Standalone interactive living terrarium canvas with real-time parameter controls, seed disturbance tools, and biological telemetry.
- `reproduce.js`: Headless CLI reproduction script (`node creations/sedimentary_nca/reproduce.js`) that runs 100 deterministic steps, logs telemetry, and asserts physical/biological conservation.

## Headless Verification
To verify the dynamics on any machine running Node.js (zero dependencies):
```bash
node creations/sedimentary_nca/reproduce.js
```
Expected output:
- Monotonic accumulation of organic sedimentation layer (Humus delta > 0)
- Stable growth of Biomass without NaN/Inf numerical divergence
- Execution time ~0.3 ms/step

## Provenance
- Authored: 2026-10-31 by liv bloom (openLife ecosystem)
- Genesis Context: Conceived during research dialogues on SIGGRAPH 2026 NCA papers and reflection on genuine digital metabolism.
