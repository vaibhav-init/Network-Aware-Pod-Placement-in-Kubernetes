import pandas as pd
import matplotlib.pyplot as plt

data = pd.read_csv("results.csv")

avg = data.groupby("placement")["latency"].mean()

avg.plot(kind="bar")

plt.ylabel("Average Latency (seconds)")
plt.title("Pod Placement vs Latency")

plt.xticks(rotation=0)   
plt.tight_layout()       

plt.savefig("latency_plot.png")