# scripts/analyze_timing_logs.py
import re
import sys
from collections import defaultdict
import statistics

def main():
    if len(sys.argv) < 2:
        print("Використання: python scripts/analyze_timing_logs.py <шлях_до_файлу_логів>")
        sys.exit(1)

    log_path = sys.argv[1]

    pattern = re.compile(r"\[(\w+)\] (\S+) took ([\d.]+)ms")
    durations = defaultdict(list)

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                _, label, ms = match.groups()
                durations[label].append(float(ms))

    if not durations:
        print(f"У файлі '{log_path}' не знайдено жодного рядка формату "
              f"'[request_id] label took Xms'. Перевірте, чи додані декоратори "
              f"log_duration/log_duration_async у код і чи контейнер перезапущений.")
        return

    for label, values in sorted(durations.items()):
        p95_idx = min(int(len(values) * 0.95), len(values) - 1)
        print(f"{label:35} p50={statistics.median(values):8.0f}ms "
              f"p95={sorted(values)[p95_idx]:8.0f}ms "
              f"n={len(values)}")

if __name__ == "__main__":
    main()