import matplotlib.pyplot as plt

# Hardcoded values from results/20260418-012642/G_19_summary.json
categories = ["Avg Latency", "P95 Latency"]
before = [685.18, 836.16]
after = [447.30, 735.58]

x = range(len(categories))
bar_width = 0.3

fig, ax = plt.subplots(figsize=(8, 5))
bars_before = ax.bar(
    [i - bar_width / 2 for i in x], before, bar_width,
    label="Before (cross-node)", color="#ef4444"
)
bars_after = ax.bar(
    [i + bar_width / 2 for i in x], after, bar_width,
    label="After (co-located)", color="#10b981"
)

ax.set_ylabel("Latency (ms)")
ax.set_title("Load Generator End-to-End Latency — Before vs After")
ax.set_xticks(list(x))
ax.set_xticklabels(categories)
ax.legend()

# Add value labels on top of each bar
for bar in bars_before:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
            f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=10)
for bar in bars_after:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
            f"{bar.get_height():.1f}", ha="center", va="bottom", fontsize=10)

# Add percentage improvement annotation
avg_improvement = (685.18 - 447.30) / 685.18 * 100
p95_improvement = (836.16 - 735.58) / 836.16 * 100
ax.annotate(f"-{avg_improvement:.1f}%", xy=(0, 447.30), xytext=(0.3, 550),
            fontsize=11, fontweight="bold", color="#047857",
            arrowprops=dict(arrowstyle="->", color="#047857"))
ax.annotate(f"-{p95_improvement:.1f}%", xy=(1, 735.58), xytext=(1.3, 790),
            fontsize=11, fontweight="bold", color="#047857",
            arrowprops=dict(arrowstyle="->", color="#047857"))

plt.tight_layout()
plt.savefig("19_loadgen_latency.png", dpi=150)
print("Saved 19_loadgen_latency.png")
