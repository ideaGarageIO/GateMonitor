#!/usr/bin/env python3
"""
Simulates cyclictest output for two scenarios:
1. Non-isolated CPU (standard setup)
2. Isolated CPU with memory locking

This generates realistic fake data showing typical differences.
"""

import numpy as np
import argparse
from dataclasses import dataclass
from typing import List, Tuple
import json


@dataclass
class CyclictestConfig:
    duration_sec: int = 60
    interval_us: int = 1000  # 1ms interval (1000 loops/sec)
    priority: int = 99


def generate_non_isolated_latencies(config: CyclictestConfig, seed: int = 42) -> np.ndarray:
    """
    Generate latencies typical of a non-isolated CPU.

    Characteristics:
    - Higher baseline latency (15-30 µs typical)
    - Frequent small spikes from scheduler/interrupts
    - Occasional large spikes (100-500+ µs) from system activity
    - More variance overall
    """
    rng = np.random.default_rng(seed)
    num_samples = config.duration_sec * (1_000_000 // config.interval_us)

    # Base latency: log-normal distribution centered around 20-25 µs
    base = rng.lognormal(mean=3.0, sigma=0.4, size=num_samples)

    # Add periodic scheduler interference (every ~4ms = HZ=250)
    scheduler_ticks = np.zeros(num_samples)
    tick_indices = np.arange(0, num_samples, 4)
    scheduler_ticks[tick_indices] = rng.exponential(scale=15, size=len(tick_indices))

    # Add random interrupt spikes (roughly 2% of samples)
    interrupt_mask = rng.random(num_samples) < 0.02
    interrupt_spikes = np.zeros(num_samples)
    interrupt_spikes[interrupt_mask] = rng.exponential(scale=50, size=interrupt_mask.sum())

    # Add occasional large spikes from system activity (0.1% of samples)
    # These represent things like page faults, disk I/O completion, network activity
    large_spike_mask = rng.random(num_samples) < 0.001
    large_spikes = np.zeros(num_samples)
    large_spikes[large_spike_mask] = rng.exponential(scale=200, size=large_spike_mask.sum())

    # Very rare extreme spikes (0.01%) - kernel activity, SMI, etc.
    extreme_mask = rng.random(num_samples) < 0.0001
    extreme_spikes = np.zeros(num_samples)
    extreme_spikes[extreme_mask] = rng.uniform(500, 2000, size=extreme_mask.sum())

    latencies = base + scheduler_ticks + interrupt_spikes + large_spikes + extreme_spikes

    # Ensure minimum latency is realistic (at least 5 µs)
    latencies = np.maximum(latencies, 5)

    return latencies.astype(int)


def generate_isolated_latencies(config: CyclictestConfig, seed: int = 43) -> np.ndarray:
    """
    Generate latencies typical of an isolated CPU with mlockall.

    Characteristics:
    - Lower baseline latency (5-15 µs typical)
    - Much fewer spikes (no scheduler interference on this CPU)
    - No page faults (memory is locked)
    - Occasional small spikes from unavoidable interrupts
    - Much tighter distribution
    """
    rng = np.random.default_rng(seed)
    num_samples = config.duration_sec * (1_000_000 // config.interval_us)

    # Base latency: tighter log-normal distribution centered around 8-10 µs
    base = rng.lognormal(mean=2.1, sigma=0.25, size=num_samples)

    # Minimal interrupt spikes (0.2% of samples) - only unavoidable ones
    # like timer interrupts that can't be fully isolated
    interrupt_mask = rng.random(num_samples) < 0.002
    interrupt_spikes = np.zeros(num_samples)
    interrupt_spikes[interrupt_mask] = rng.exponential(scale=10, size=interrupt_mask.sum())

    # Very rare larger spikes (0.02%) - SMI, NMI, hardware quirks
    rare_mask = rng.random(num_samples) < 0.0002
    rare_spikes = np.zeros(num_samples)
    rare_spikes[rare_mask] = rng.uniform(30, 100, size=rare_mask.sum())

    latencies = base + interrupt_spikes + rare_spikes

    # Ensure minimum latency is realistic (at least 3 µs)
    latencies = np.maximum(latencies, 3)

    return latencies.astype(int)


def compute_histogram(latencies: np.ndarray, max_bucket: int = 500) -> dict:
    """Compute histogram buckets (like cyclictest --histogram)."""
    hist = {}
    for i in range(max_bucket + 1):
        count = np.sum(latencies == i)
        if count > 0:
            hist[i] = int(count)
    # Overflow bucket
    overflow = np.sum(latencies > max_bucket)
    if overflow > 0:
        hist[f">{max_bucket}"] = int(overflow)
    return hist


def compute_stats(latencies: np.ndarray) -> dict:
    """Compute summary statistics."""
    return {
        "min": int(np.min(latencies)),
        "avg": float(np.mean(latencies)),
        "max": int(np.max(latencies)),
        "stdev": float(np.std(latencies)),
        "median": int(np.median(latencies)),
        "p99": int(np.percentile(latencies, 99)),
        "p99.9": int(np.percentile(latencies, 99.9)),
        "p99.99": int(np.percentile(latencies, 99.99)),
        "samples": len(latencies),
    }


def format_cyclictest_output(latencies: np.ndarray, scenario: str, config: CyclictestConfig) -> str:
    """Format output similar to cyclictest summary."""
    stats = compute_stats(latencies)

    output = []
    output.append(f"# Simulated cyclictest data: {scenario}")
    output.append(f"# Duration: {config.duration_sec} seconds")
    output.append(f"# Interval: {config.interval_us} µs")
    output.append(f"# Priority: {config.priority}")
    output.append(f"# Samples: {stats['samples']}")
    output.append("")
    output.append("T: 0 ( PID) P:{:2d} I:{:5d} C:{:8d} Min:{:6d} Act:{:6d} Avg:{:6.1f} Max:{:6d}".format(
        config.priority,
        config.interval_us,
        stats['samples'],
        stats['min'],
        int(latencies[-1]),  # Last actual value
        stats['avg'],
        stats['max']
    ))
    output.append("")
    output.append("Statistics:")
    output.append(f"  Min:      {stats['min']:6d} µs")
    output.append(f"  Avg:      {stats['avg']:6.1f} µs")
    output.append(f"  Max:      {stats['max']:6d} µs")
    output.append(f"  Stdev:    {stats['stdev']:6.1f} µs")
    output.append(f"  Median:   {stats['median']:6d} µs")
    output.append(f"  P99:      {stats['p99']:6d} µs")
    output.append(f"  P99.9:    {stats['p99.9']:6d} µs")
    output.append(f"  P99.99:   {stats['p99.99']:6d} µs")

    return "\n".join(output)


def format_histogram_output(latencies: np.ndarray, max_bucket: int = 200) -> str:
    """Format histogram output (like cyclictest --histogram)."""
    lines = []
    lines.append("# Latency histogram (µs : count)")

    for us in range(max_bucket + 1):
        count = np.sum(latencies == us)
        if count > 0:
            bar = "#" * min(int(count / 100), 50)
            lines.append(f"{us:6d}: {count:8d} {bar}")

    overflow = np.sum(latencies > max_bucket)
    if overflow > 0:
        lines.append(f">{max_bucket:5d}: {overflow:8d}")

    return "\n".join(lines)


def print_comparison(non_isolated: np.ndarray, isolated: np.ndarray):
    """Print side-by-side comparison."""
    stats_ni = compute_stats(non_isolated)
    stats_i = compute_stats(isolated)

    print("\n" + "=" * 70)
    print("COMPARISON: Non-Isolated vs Isolated CPU")
    print("=" * 70)
    print(f"{'Metric':<15} {'Non-Isolated':>15} {'Isolated':>15} {'Improvement':>15}")
    print("-" * 70)

    metrics = [
        ("Min (µs)", "min"),
        ("Avg (µs)", "avg"),
        ("Max (µs)", "max"),
        ("Stdev (µs)", "stdev"),
        ("Median (µs)", "median"),
        ("P99 (µs)", "p99"),
        ("P99.9 (µs)", "p99.9"),
        ("P99.99 (µs)", "p99.99"),
    ]

    for label, key in metrics:
        ni_val = stats_ni[key]
        i_val = stats_i[key]
        if ni_val != 0:
            improvement = ((ni_val - i_val) / ni_val) * 100
            print(f"{label:<15} {ni_val:>15.1f} {i_val:>15.1f} {improvement:>14.1f}%")
        else:
            print(f"{label:<15} {ni_val:>15.1f} {i_val:>15.1f} {'N/A':>15}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Simulate cyclictest data")
    parser.add_argument("-d", "--duration", type=int, default=60,
                        help="Test duration in seconds (default: 60)")
    parser.add_argument("-i", "--interval", type=int, default=1000,
                        help="Interval in microseconds (default: 1000)")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output file prefix (generates .json and .txt files)")
    parser.add_argument("--histogram", action="store_true",
                        help="Print histogram output")
    parser.add_argument("--json", action="store_true",
                        help="Output raw data as JSON")
    args = parser.parse_args()

    config = CyclictestConfig(
        duration_sec=args.duration,
        interval_us=args.interval,
    )

    print(f"Generating simulated cyclictest data...")
    print(f"Duration: {config.duration_sec}s, Interval: {config.interval_us}µs")
    print()

    # Generate data for both scenarios
    non_isolated = generate_non_isolated_latencies(config)
    isolated = generate_isolated_latencies(config)

    # Print results
    print("=" * 70)
    print("SCENARIO 1: Non-Isolated CPU (standard setup)")
    print("=" * 70)
    print(format_cyclictest_output(non_isolated, "Non-Isolated CPU", config))

    if args.histogram:
        print("\n" + format_histogram_output(non_isolated))

    print("\n")
    print("=" * 70)
    print("SCENARIO 2: Isolated CPU with mlockall")
    print("=" * 70)
    print(format_cyclictest_output(isolated, "Isolated CPU + mlockall", config))

    if args.histogram:
        print("\n" + format_histogram_output(isolated))

    # Print comparison
    print_comparison(non_isolated, isolated)

    # Save to files if requested
    if args.output:
        # Save JSON data
        data = {
            "config": {
                "duration_sec": config.duration_sec,
                "interval_us": config.interval_us,
                "priority": config.priority,
            },
            "non_isolated": {
                "stats": compute_stats(non_isolated),
                "histogram": compute_histogram(non_isolated),
            },
            "isolated": {
                "stats": compute_stats(isolated),
                "histogram": compute_histogram(isolated),
            }
        }

        if args.json:
            data["non_isolated"]["raw"] = non_isolated.tolist()
            data["isolated"]["raw"] = isolated.tolist()

        json_file = f"{args.output}.json"
        with open(json_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nSaved data to {json_file}")

        # Save text summary
        txt_file = f"{args.output}.txt"
        with open(txt_file, "w") as f:
            f.write("SCENARIO 1: Non-Isolated CPU\n")
            f.write(format_cyclictest_output(non_isolated, "Non-Isolated CPU", config))
            f.write("\n\n")
            f.write("SCENARIO 2: Isolated CPU + mlockall\n")
            f.write(format_cyclictest_output(isolated, "Isolated CPU + mlockall", config))
        print(f"Saved summary to {txt_file}")


if __name__ == "__main__":
    main()
