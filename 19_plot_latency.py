import matplotlib.pyplot as plt

different_node = [0.001270, 0.001363, 0.001296, 0.001424, 0.001318, 0.001291, 0.001330, 0.002543]
same_node = [0.001514, 0.001385, 0.001332, 0.001479, 0.001346, 0.001252, 0.001222, 0.001278]

placements = ["different-node", "same-node"]
avg_latency = [sum(different_node) / len(different_node), sum(same_node) / len(same_node)]

plt.bar(placements, avg_latency)

plt.ylabel("Average Latency (seconds)")
plt.title("Pod Placement vs Latency")

plt.xticks(rotation=0)   
plt.tight_layout()       

plt.savefig("19_latency_plot.png")