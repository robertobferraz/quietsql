import argparse
import json
import os
import platform
import statistics
import subprocess
from pathlib import Path

from quietsql.config import load_config
from quietsql.wiring import build_services

STAGES = ("detect_ms", "translate_ms", "prefill_ms", "generate_ms", "transpile_ms", "run_ms")
TARGET_MS = 5000.0
GIB = 1024**3


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p * (len(ordered) - 1))))
    return ordered[k]


def sysctl(key: str) -> str:
    try:
        done = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, check=True)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def cpu_name() -> str:
    if platform.system() == "Darwin":
        brand = sysctl("machdep.cpu.brand_string")
        if brand:
            return brand
    return platform.processor() or platform.system()


def total_ram_gb() -> float:
    if platform.system() == "Darwin":
        memsize = sysctl("hw.memsize")
        if memsize.isdigit():
            return int(memsize) / GIB
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GIB
    except (AttributeError, ValueError, OSError):
        return 0.0


def machine_line() -> str:
    ram = total_ram_gb()
    memory = f"{ram:.0f} GB RAM" if ram else "RAM unknown"
    return f"machine: {platform.machine()} · {cpu_name()} · {os.cpu_count()} cores · {memory}"


def verdict(p50: float, p95: float) -> str:
    if p50 <= TARGET_MS and p95 <= TARGET_MS:
        return "met at the median and at the tail"
    if p50 <= TARGET_MS:
        return "met at the median, missed at the tail"
    return "missed at the median and at the tail"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/demo.duckdb"))
    parser.add_argument("--questions", type=Path, default=Path("tests/accuracy/cases.json"))
    parser.add_argument("--out", type=Path, default=Path("docs/benchmark.md"))
    args = parser.parse_args()
    services = build_services(load_config())
    source = services.sources.open_file(str(args.db))
    cases = json.loads(args.questions.read_text())
    samples: dict[str, list[float]] = {s: [] for s in STAGES}
    totals: list[float] = []
    for case in cases:
        answer = services.ask(source.id, case["question"])
        d = answer.timings.as_dict()
        for s in STAGES:
            samples[s].append(d[s])
        totals.append(sum(d.values()))
    total_p50 = percentile(totals, 0.5)
    total_p95 = percentile(totals, 0.95)
    lines = [
        "# Benchmark",
        "",
        machine_line(),
        f"dataset: {args.db} · questions: {len(cases)}",
        "",
        "| stage | p50 ms | p95 ms |",
        "|---|---:|---:|",
    ]
    for s in STAGES:
        lines.append(
            f"| {s[:-3]} | {percentile(samples[s], 0.5):.0f} | {percentile(samples[s], 0.95):.0f} |"
        )
    lines.append(f"| total | {total_p50:.0f} | {total_p95:.0f} |")
    lines.append("")
    lines.append(f"mean total {statistics.mean(totals):.0f} ms")
    lines.append("")
    lines.append("## D008")
    lines.append("")
    lines.append(f"Target: an answer in under {TARGET_MS / 1000:.0f} s on this machine.")
    lines.append("")
    lines.append(
        f"Measured: p50 total {total_p50 / 1000:.1f} s, p95 total {total_p95 / 1000:.1f} s "
        f"over {len(cases)} questions. "
        f"The target is **{verdict(total_p50, total_p95)}**."
    )
    lines.append("")
    lines.append(
        f"p95 here is the nearest-rank value over {len(cases)} questions, so it is close to the "
        "worst observation rather than a stable tail estimate. Quote both numbers together; "
        f"neither one alone describes the {TARGET_MS / 1000:.0f} s target."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
