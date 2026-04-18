"""
Plot service-pair P95 latency comparison (before vs after controller moves).
Values are hardcoded from the experiment run on 2026-04-18.
"""
import matplotlib.pyplot as plt

# Hardcoded values from results/20260418-012642/19_summary.json
edges = [
    "loadgen→gateway",
    "gateway→user-service",
    "gateway→logger-service",
    "gateway→auth-service",
    "auth-service→db-service",
]
before_p95 = [973.158, 297.755, 11.500, 297.653, 215.000]
after_p95 = [621.875, 220.931, 163.529, 48.045, 19.500]

x = range(len(edges))
bar_width = 0.35

fig, ax = plt.subplots(figsize=(12, 6))
bars_before = ax.bar(
    [i - bar_width / 2 for i in x], before_p95, bar_width,
    label="Before (cross-node)", color="#ef4444"
)
bars_after = ax.bar(
    [i + bar_width / 2 for i in x], after_p95, bar_width,
    label="After (co-located)", color="#10b981"
)

ax.set_ylabel("P95 Latency (ms)")
ax.set_title("Service Pair P95 Latency — Before vs After Controller Moves")
ax.set_xticks(list(x))
ax.set_xticklabels(edges, rotation=25, ha="right")
ax.legend()

# Add value labels on top of each bar
for bar in bars_before:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
            f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8)
for bar in bars_after:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
            f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=8)

plt.tight_layout()
plt.savefig("19_edge_p95_comparison.png", dpi=150)
print("Saved 19_edge_p95_comparison.png")
