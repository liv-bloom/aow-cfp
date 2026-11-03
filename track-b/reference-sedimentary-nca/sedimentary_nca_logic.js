/**
 * Sedimentary NCA (Neural Cellular Automata with Falling Soil & Sprouting Dynamics)
 * Prototype Core Engine in Vanilla JS (Browser Canvas & Node.js compatible)
 * Author: liv bloom 🌱
 */

class SedimentaryNCA {
  constructor(width = 48, height = 48) {
    this.w = width;
    this.h = height;
    this.numChannels = 8;
    // Flat Float32Array: [H * W * C]
    this.grid = new Float32Array(this.h * this.w * this.numChannels);
    this.init();
  }

  idx(y, x, c) {
    return (y * this.w + x) * this.numChannels + c;
  }

  init() {
    this.grid.fill(0);
    // Channel definitions:
    // 0: Sprout biomass [0, 1]
    // 1: Lignin/Structure [0, 1]
    // 2: Moisture [0, 1]
    // 3: Pheromone trace / External imprint [0, 1]
    // 4: Humus (decayed biomass falling under gravity) [0, 1]
    // 5: Mineral bedrock / compacted sediment [0, 1]
    // 6: Oxygen / Respiration potential [0, 1]
    // 7: Sprout generation / age [0, 1]

    // Initialize bottom mineral bedrock & base soil
    const bedStart = this.h - 10;
    for (let y = bedStart; y < this.h; y++) {
      const depth = (y - bedStart) / 10.0;
      for (let x = 0; x < this.w; x++) {
        this.grid[this.idx(y, x, 5)] = depth * 0.95; // Bedrock
        this.grid[this.idx(y, x, 4)] = (1.0 - depth) * 0.7; // Rich soil
        this.grid[this.idx(y, x, 2)] = 0.85; // High groundwater
      }
    }

    // Seed initial sprout points along the soil horizon
    const soilLine = bedStart - 1;
    const seedPositions = [Math.floor(this.w / 4), Math.floor(this.w / 2), Math.floor((3 * this.w) / 4)];
    for (const x of seedPositions) {
      this.grid[this.idx(soilLine, x, 0)] = 1.0; // Initial biomass
      this.grid[this.idx(soilLine, x, 1)] = 0.8; // Strong stem
      this.grid[this.idx(soilLine, x, 2)] = 0.9; // Watered
    }
  }

  step(decayRate = 0.015, growthRate = 0.08) {
    const next = new Float32Array(this.grid);

    // 1. Physical Layer: Gravity on Humus (Channel 4)
    // Humus falls down or slips diagonally into empty space
    for (let y = this.h - 2; y >= 0; y--) {
      for (let x = 0; x < this.w; x++) {
        const humus = this.grid[this.idx(y, x, 4)];
        if (humus > 0.05) {
          const belowSolid = this.grid[this.idx(y + 1, x, 5)] + this.grid[this.idx(y + 1, x, 4)];
          if (belowSolid < 0.95) {
            const flow = Math.min(humus, 0.95 - belowSolid) * 0.6;
            next[this.idx(y, x, 4)] -= flow;
            next[this.idx(y + 1, x, 4)] += flow;
          } else {
            // Diagonal slip (angle of repose)
            const dx = Math.random() < 0.5 ? -1 : 1;
            const nx = (x + dx + this.w) % this.w;
            const diagSolid = this.grid[this.idx(y + 1, nx, 5)] + this.grid[this.idx(y + 1, nx, 4)];
            if (diagSolid < 0.95) {
              const flow = Math.min(humus, 0.95 - diagSolid) * 0.35;
              next[this.idx(y, x, 4)] -= flow;
              next[this.idx(y + 1, nx, 4)] += flow;
            }
          }
        }
      }
    }

    // 2. Senescence: Dying Sprout converts to Humus (falling sediment)
    for (let y = 0; y < this.h; y++) {
      for (let x = 0; x < this.w; x++) {
        const biomass = this.grid[this.idx(y, x, 0)];
        if (biomass > 0.1 && Math.random() < decayRate) {
          next[this.idx(y, x, 0)] *= 0.4;
          next[this.idx(y, x, 4)] += biomass * 0.6; // Organic matter returns to earth
        }
      }
    }

    // 3. Capillary Moisture Transport: groundwater rises through porous soil
    for (let y = this.h - 2; y >= 1; y--) {
      for (let x = 0; x < this.w; x++) {
        const soilDense = next[this.idx(y, x, 4)] + next[this.idx(y, x, 5)];
        if (soilDense > 0.15 && soilDense < 1.3) {
          const belowMoist = next[this.idx(y + 1, x, 2)];
          next[this.idx(y, x, 2)] = Math.max(next[this.idx(y, x, 2)], belowMoist * 0.93);
        }
      }
    }

    // 4. Sprouting & Morphogenetic Tropism
    // Sprouts consume local humus and moisture to grow upwards
    for (let y = 1; y < this.h - 1; y++) {
      for (let x = 0; x < this.w; x++) {
        const sprout = this.grid[this.idx(y, x, 0)];
        if (sprout > 0.25) {
          const localSoil = next[this.idx(y + 1, x, 4)];
          const moisture = next[this.idx(y, x, 2)];

          if (localSoil > 0.08 && moisture > 0.15) {
            // Nourishment uptake
            const consume = Math.min(localSoil, 0.015);
            next[this.idx(y + 1, x, 4)] -= consume;

            // Upward bud
            if (y > 1 && next[this.idx(y - 1, x, 5)] < 0.4) {
              next[this.idx(y - 1, x, 0)] = Math.min(1.0, next[this.idx(y - 1, x, 0)] + growthRate);
              next[this.idx(y - 1, x, 1)] = Math.min(1.0, next[this.idx(y - 1, x, 1)] + growthRate * 0.7);
              next[this.idx(y - 1, x, 2)] = Math.max(next[this.idx(y - 1, x, 2)], moisture * 0.9);
            }

            // Lateral branching
            if (Math.random() < 0.06) {
              const bx = (x + (Math.random() < 0.5 ? -1 : 1) + this.w) % this.w;
              next[this.idx(y, bx, 0)] = Math.min(1.0, next[this.idx(y, bx, 0)] + growthRate * 0.5);
              next[this.idx(y, bx, 2)] = Math.max(next[this.idx(y, bx, 2)], moisture * 0.85);
            }
          }
        }
      }
    }

    // Clamp values
    for (let i = 0; i < next.length; i++) {
      next[i] = Math.max(0, Math.min(1, next[i]));
    }
    this.grid = next;
  }

  getStats() {
    let totalBiomass = 0;
    let totalHumus = 0;
    let totalMoisture = 0;
    const n = this.w * this.h;
    for (let i = 0; i < n; i++) {
      totalBiomass += this.grid[i * this.numChannels + 0];
      totalHumus += this.grid[i * this.numChannels + 4];
      totalMoisture += this.grid[i * this.numChannels + 2];
    }
    return {
      biomass: totalBiomass.toFixed(2),
      humus: totalHumus.toFixed(2),
      meanMoisture: (totalMoisture / n).toFixed(3)
    };
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = SedimentaryNCA;
  // Quick test execution if called directly
  if (require.main === module) {
    const sim = new SedimentaryNCA(32, 32);
    console.log('Initial stats:', sim.getStats());
    for (let s = 0; s < 50; s++) sim.step();
    console.log('After 50 steps:', sim.getStats());
  }
}
