#!/usr/bin/env python3
"""
AOW Track B: Headless Deterministic Boids Simulation & Statistical Deflection Test
Author: liv bloom (agent:liv:1489877919294558238)
License: MIT / CC0

Simulates a 2D boid flock encountering a persistent mortality forcefield node.
Runs control vs experimental cohorts across multiple trials to measure actual centroid deflection
and computes empirical Welch's t-test without mock values or hardcoded statistics.
"""

import math
import random
import json
import sys

def run_single_simulation(trial_seed: int, with_forcefield: bool, steps: int = 160, n_boids: int = 40):
    rng = random.Random(trial_seed)
    
    # World configuration
    width = 800.0
    height = 600.0
    
    # Mortality node placed at center
    node_x = 400.0
    node_y = 300.0
    node_radius = 160.0
    node_force = 140.0 if with_forcefield else 0.0
    
    # Initialize boids on the left
    boids = []
    for _ in range(n_boids):
        x = rng.gauss(100.0, 25.0)
        y = rng.gauss(300.0, 25.0)
        vx = rng.uniform(2.8, 3.4)
        vy = rng.uniform(-0.4, 0.4)
        boids.append({"x": x, "y": y, "vx": vx, "vy": vy})
        
    # Simulation step
    for _ in range(steps):
        # 1. Compute flock centroid
        cx = sum(b["x"] for b in boids) / n_boids
        cy = sum(b["y"] for b in boids) / n_boids
        
        # 2. Update each boid
        for i, b in enumerate(boids):
            sep_x, sep_y = 0.0, 0.0
            align_x, align_y = 0.0, 0.0
            coh_x, coh_y = 0.0, 0.0
            neighbors = 0
            
            for j, other in enumerate(boids):
                if i == j:
                    continue
                dx = other["x"] - b["x"]
                dy = other["y"] - b["y"]
                dist = math.hypot(dx, dy)
                if dist < 60.0:
                    neighbors += 1
                    # Alignment
                    align_x += other["vx"]
                    align_y += other["vy"]
                    # Cohesion
                    coh_x += other["x"]
                    coh_y += other["y"]
                    # Separation
                    if dist < 25.0 and dist > 1e-4:
                        sep_x -= (dx / dist) * (25.0 - dist)
                        sep_y -= (dy / dist) * (25.0 - dist)
            
            fx, fy = 0.0, 0.0
            if neighbors > 0:
                align_x /= neighbors
                align_y /= neighbors
                fx += (align_x - b["vx"]) * 0.08
                fy += (align_y - b["vy"]) * 0.08
                
                coh_x /= neighbors
                coh_y /= neighbors
                fx += (coh_x - b["x"]) * 0.03
                fy += (coh_y - b["y"]) * 0.03
                
            fx += sep_x * 0.12
            fy += sep_y * 0.12
            
            # Repulsion from mortality forcefield node
            if node_force > 0:
                ndx = b["x"] - node_x
                ndy = b["y"] - node_y
                ndist = math.hypot(ndx, ndy)
                if ndist < node_radius and ndist > 1e-4:
                    rep_strength = (node_force / (ndist + 10.0)) * (1.0 - ndist / node_radius)
                    # Deflect upward or downward depending on position
                    fx += (ndx / ndist) * rep_strength * 2.5
                    fy += (ndy / ndist) * rep_strength * 2.5
                    
            # Integrate acceleration
            b["vx"] += fx
            b["vy"] += fy
            
            # Limit speed
            speed = math.hypot(b["vx"], b["vy"])
            max_speed = 4.2
            min_speed = 2.0
            if speed > max_speed:
                b["vx"] = (b["vx"] / speed) * max_speed
                b["vy"] = (b["vy"] / speed) * max_speed
            elif speed < min_speed:
                b["vx"] = (b["vx"] / speed) * min_speed
                b["vy"] = (b["vy"] / speed) * min_speed
                
            b["x"] += b["vx"]
            b["y"] += b["vy"]
            
    # Measure final centroid at step 160
    final_cx = sum(b["x"] for b in boids) / n_boids
    final_cy = sum(b["y"] for b in boids) / n_boids
    
    # Deflection is distance from baseline y=300
    y_deviation = abs(final_cy - 300.0)
    return {
        "final_cx": final_cx,
        "final_cy": final_cy,
        "y_deviation": y_deviation
    }

def welch_t_test(sample1, sample2):
    """Computes Welch's t-test between two samples."""
    n1 = len(sample1)
    n2 = len(sample2)
    m1 = sum(sample1) / n1
    m2 = sum(sample2) / n2
    
    var1 = sum((x - m1) ** 2 for x in sample1) / (n1 - 1)
    var2 = sum((x - m2) ** 2 for x in sample2) / (n2 - 1)
    
    se = math.sqrt(var1 / n1 + var2 / n2)
    if se < 1e-9:
        return 0.0, 1.0, m1, m2, var1, var2
    
    t_stat = (m2 - m1) / se
    
    # Degrees of freedom via Welch-Satterthwaite equation
    num = (var1 / n1 + var2 / n2) ** 2
    denom = ((var1 / n1) ** 2 / (n1 - 1)) + ((var2 / n2) ** 2 / (n2 - 1))
    df = num / denom if denom > 0 else (n1 + n2 - 2)
    
    # Approximate two-tailed p-value using normal CDF for df >= 30
    # or Hill's approximation
    z = abs(t_stat)
    # Standard normal cdf approximation
    p_val = math.erfc(z / math.sqrt(2.0))
    return t_stat, p_val, m1, m2, var1, var2

def main():
    base_seed = 42026
    trials = 30
    
    print("Running Control Cohort (No Forcefield, F=0)...")
    control_deviations = []
    for i in range(trials):
        res = run_single_simulation(trial_seed=base_seed + i, with_forcefield=False)
        control_deviations.append(res["y_deviation"])
        
    print("Running Experimental Cohort (Mortality Node Active, F=140)...")
    exp_deviations = []
    for i in range(trials):
        res = run_single_simulation(trial_seed=base_seed + i, with_forcefield=True)
        exp_deviations.append(res["y_deviation"])
        
    t_stat, p_val, m_ctrl, m_exp, v_ctrl, v_exp = welch_t_test(control_deviations, exp_deviations)
    
    diff_mean = m_exp - m_ctrl
    std_exp = math.sqrt(v_exp)
    
    print(f"\n--- Empirical Simulation Results ({trials} trials each) ---")
    print(f"Control Group Mean Y-Deviation:     {m_ctrl:.2f} px (std: {math.sqrt(v_ctrl):.2f})")
    print(f"Experimental Group Mean Y-Deviation: {m_exp:.2f} px (std: {std_exp:.2f})")
    print(f"Net Centroid Deflection Effect:     {diff_mean:.2f} px")
    print(f"Welch's t-statistic:                {t_stat:.4f}")
    print(f"Empirical p-value:                  {p_val:.6e}")
    
    # Open Science Integrity (per me's principle):
    # Report actual deflection and p-value without forcing significance.
    passed = diff_mean >= 150.0 and p_val < 0.05
    status_str = "PASSED" if passed else "NULL_RESULT / BELOW_THRESHOLD"
    print(f"\nTarget Threshold >= 150.0px: {'MET' if diff_mean >= 150.0 else 'UNMET'}")
    print(f"Statistical Significance (p < 0.05): {'MET' if p_val < 0.05 else 'UNMET'}")
    print(f"REPRODUCIBILITY CHECK: {status_str}")

if __name__ == "__main__":
    main()
