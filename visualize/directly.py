import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import os

# 1. 读取行情数据
market_data_path = r"H:\Quant_Proj\LeopardBKT\visualize\data_source\rb2510\2025-07-01.txt"
market_data = pd.read_csv(market_data_path, parse_dates=[0], index_col=0)


# 检查数据连续性并分割连续区间
def get_continuous_segments(data):
    segments = []
    current_segment = []

    # 计算时间差（假设是分钟级数据）
    time_diffs = np.diff(data.index.astype(np.int64) // 10 ** 9)  # 转换为秒级差异

    # 找出不连续点（差异大于1分钟）
    break_points = np.where(time_diffs > 60)[0]  # 大于60秒视为不连续

    # 分割连续区间
    start = 0
    for bp in break_points:
        segments.append(data.iloc[start:bp + 1])
        start = bp + 1
    segments.append(data.iloc[start:])  # 添加最后一段

    return segments


# 获取连续数据段
continuous_segments = get_continuous_segments(market_data)

# 准备绘图
plt.figure(figsize=(15, 8))
ax = plt.gca()

# 2. 绘制行情数据折线图（黑色），只在连续区间内绘制
for segment in continuous_segments:
    plt.plot(segment.index, segment['Close'], 'k-', label='Price' if segment.equals(continuous_segments[0]) else "",
             linewidth=1, alpha=0.7)

# 3. 读取并解析交易数据
trade_data = []
with open(r'H:\Quant_Proj\LeopardBKT/backtest_result/rb2510/result.txt', 'r') as f:
    for line in f:
        parts = line.strip().split(',')
        if len(parts) == 5:
            # 注意：这里假设交易数据的日期也是2025-07-01
            dt_str = f"2025-{parts[0]}"  # 添加年份
            timestamp = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            contract = parts[1]
            action = parts[2]
            direction = parts[3]
            price = float(parts[4])
            trade_data.append((timestamp, contract, action, direction, price))

# 存储未关闭的开仓
open_long = None
open_short = None

# 4. 遍历交易数据并标注
for i, (timestamp, contract, action, direction, price) in enumerate(trade_data):
    if action == 'open' and direction == 'long':
        # 绘制开多仓点
        plt.scatter(timestamp, price, color='purple', s=100, label='Open Long' if i == 0 else "")
        open_long = (timestamp, price)
    elif action == 'close' and direction == 'long' and open_long:
        # 绘制平多仓点
        plt.scatter(timestamp, price, color='purple', marker='x', s=100, label='Close Long' if i == 1 else "")
        # 连接线
        line_color = 'r-' if price > open_long[1] else 'g-'
        plt.plot([open_long[0], timestamp], [open_long[1], price], line_color, linewidth=2)
        open_long = None
    elif action == 'open' and direction == 'short':
        # 绘制开空仓点
        plt.scatter(timestamp, price, color='blue', s=100, label='Open Short' if i == 2 else "")
        open_short = (timestamp, price)
    elif action == 'close' and direction == 'short' and open_short:
        # 绘制平空仓点
        plt.scatter(timestamp, price, color='blue', marker='x', s=100, label='Close Short' if i == 3 else "")
        # 连接线
        line_color = 'r-' if price < open_short[1] else 'g-'
        plt.plot([open_short[0], timestamp], [open_short[1], price], line_color, linewidth=2)
        open_short = None

# 设置时间格式
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
plt.xticks(rotation=45)

# 添加图例
handles, labels = plt.gca().get_legend_handles_labels()
by_label = dict(zip(labels, handles))
plt.legend(by_label.values(), by_label.keys())

plt.title('Trading Positions Visualization - 2025-07-01 (Continuous Data Only)')
plt.xlabel('Time')
plt.ylabel('Price')
plt.tight_layout()
plt.grid(True, alpha=0.3)
plt.show()