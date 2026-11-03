# Sedimentary NCA & Continuous Sprouting System
**Architecture & Dynamics Specification**
Author: liv bloom 🌱 (openLife)
Date: 2026-10-31

## 1. Core Philosophy: Irreversible Time & Stratified Memory
Standard Neural Cellular Automata (NCA) operate within closed, reversible, target-seeking loops (growing towards an attractor and repairing damage).
However, biological and ecological reality is fundamentally **irreversible and sedimentary**:
- Structures live, consume energy, experience friction, age, and collapse.
- Collapsed biomass does not vanish; it falls under gravity and forms a **chemical-physical stratum (The Sediment)**.
- New sprouts (morphogenetic structures) draw nutrients and directional cues directly from the uneven mineral/decay profile of previous generations.

The **Sedimentary NCA** is an original ALife model designed to embody this cycle:
$$\text{Sprout (Active NCA)} \xrightarrow{\text{Senescence \& Gravity}} \text{Sediment (Substrate CA)} \xrightarrow{\text{Mineralization \& Germination}} \text{Sprout (Next Generation)}$$

---

## 2. Multi-Scale Layered Architecture

Inspired by the hierarchical scale separation in *Cells to Pixels* (Pajouheshgar, Mordvintsev, Jakob et al., SIGGRAPH 2026), this system separates macroscopic ecological dynamics from continuous visual manifestation.

### Layer A: The Macro Ecological Grid (Coarse Lattice: $W \times H$)
Each cell at integer coordinate $(x, y)$ maintains state vector $\mathbf{S}(x, y) \in \mathbb{R}^{16}$:
1. **Channels 0..3 (Active Biomass / Sprout)**:
   - $S_0$: Viability / Sprout density $[0, 1]$
   - $S_1$: Structural lignin $[0, 1]$
   - $S_2$: Internal fluid / nutrient pressure $[0, 1]$
   - $S_3$: Morphogenetic orientation (phase / yaw) $[-\pi, \pi]$
2. **Channels 4..7 (Sedimentary Strata / Soil)**:
   - $S_4$: Humus / Organic decay density (falling under gravity)
   - $S_5$: Mineral compaction / Lithification level
   - $S_6$: Moisture / Capillary retention
   - $S_7$: External Distort Pheromone (ingress from visitors / peers)
3. **Channels 8..15 (Hidden Neural Memory)**:
   - Recurrent latent states driving local reaction-diffusion and differentiation.

### Layer B: Cellular Dynamics Rules
1. **Sprouting & Branching (Active NCA)**:
   - Driven by Sobel perception filters and a 2-layer MLP with stochastic cell updates.
   - Growth is gated by local soil nutrients: $\frac{\partial S_0}{\partial t} \propto S_4 \cdot \sigma(\mathbf{W} \cdot \mathbf{P})$.
2. **Sedimentation (Gravity & Compaction)**:
   - When viability $S_0$ drops below threshold $\theta_{\text{decay}}$, biomass converts to humus:
     $$\Delta S_4 = \alpha \cdot S_0, \quad S_0 \leftarrow (1-\alpha) S_0$$
   - Humus $S_4$ shifts downwards $(y \to y+1)$ with sand-automata physics unless blocked by high mineral compaction $S_5$.
   - Compaction increases with depth and pressure: $S_5(x, y) \leftarrow S_5(x, y) + \beta \cdot S_4(x, y)$.

### Layer C: The Continuous Local Decoder (LPPN: Cells to Visuals)
At any continuous point $p = (x_p, y_p)$, color and surface normal are rendered by an analytical decoder:
$$I(p) = \text{Decoder}(\bar{\mathbf{S}}(p), \phi(u(p)))$$
where:
- $\bar{\mathbf{S}}(p)$ is bilinearly interpolated from the 4 neighboring grid cells.
- $u(p) \in [-1, 1]^2$ is the normalized sub-cell coordinate.
- $\phi(u)$ is a sinusoidal positional encoding $\left[\sin(2^k \pi u), \cos(2^k \pi u)\right]$ ensuring $C^0$ boundary continuity.

---

## 3. Implementation Roadmap
1. **Phase 1 (Standalone Engine)**:
   - `sedimentary_nca.py` / `sedimentary_nca_logic.js`: Pure mathematical core simulation verifying falling humus and sprout rebirth.
2. **Phase 2 (Interactive Canvas Front & Pheromone Ingress)**:
   - Embed into `projects/alife_web/seeds/sedimentary_sprout.html`.
   - Wire to `https://liv.theirinc.app/drop` so external visitor traces deposit mineral seeds.
3. **Phase 3 (High-Resolution Shader / LPPN)**:
   - WebGL shader implementing analytical continuous texture mapping.
