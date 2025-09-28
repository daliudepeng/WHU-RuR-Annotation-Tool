import matplotlib.pyplot as plt
from collections import Counter
import os

# --- 配置 ---
ANNOTATIONS_FILE = 'annotations.txt'
OUTPUT_IMAGE_FILE = 'noise_distribution_percentage.png'
TOTAL_IMAGES = 500  # 【新增】图像总数，用于计算百分比

# 设置 matplotlib 支持中文显示，SimHei 是一个常用的支持中文的字体
plt.rcParams['font.sans-serif'] = ['SimHei']
# 解决保存图像时负号'-'显示为方块的问题
plt.rcParams['axes.unicode_minus'] = False


def analyze_noise_distribution_with_percentage():
    """
    读取标注文件，统计标签数量，计算百分比，并生成带有百分比的可视化直-
    方图。
    """
    # 检查标注文件是否存在
    if not os.path.exists(ANNOTATIONS_FILE):
        print(f"错误: 找不到标注文件 '{ANNOTATIONS_FILE}'。请确保该文件与脚本在同一目录下。")
        return

    # 使用 collections.Counter 进行高效计数
    label_counts = Counter()

    # 读取并解析文件
    with open(ANNOTATIONS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过注释行或空行
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(',')
            # parts[0] 是文件ID, parts[1:] 是标签
            labels = parts[1:]

            # 更新计数器
            label_counts.update(labels)

    # --- 准备绘图数据 ---

    target_labels = ['1', '2', '3']
    label_names = {
        '1': '漏标噪音 (1)',
        '2': '错标噪音 (2)',
        '3': '形态不符 (3)'
    }

    counts = [label_counts[label] for label in target_labels]
    display_names = [label_names[label] for label in target_labels]

    # --- 绘图 ---

    fig, ax = plt.subplots(figsize=(10, 7))  # 增加画布高度以容纳文本

    # 定义统一的暖色调
    colors = ['#FFC107', '#FFA000', '#FF8F00']  # 琥珀色、橙色、深橙色

    bars = ax.bar(display_names, counts, color=colors)

    # 设置图表标题和坐标轴标签
    ax.set_title('噪声标签分布直方图 (含百分比)', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('标签类别', fontsize=12, labelpad=15)
    ax.set_ylabel('数量', fontsize=12, labelpad=15)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)

    # 【核心更新】在每个柱子上方显示具体数值和百分比
    for bar in bars:
        yval = bar.get_height()
        # 计算百分比
        percentage = (yval / TOTAL_IMAGES) * 100
        # 将数值和百分比分行显示，让格式更清晰
        label_text = f"{int(yval)}\n({percentage:.1f}%)"

        ax.text(bar.get_x() + bar.get_width() / 2.0, yval, label_text,
                ha='center', va='bottom', fontsize=11, fontweight='medium', linespacing=1.5)

    # 自动调整Y轴的上限，为顶部的文本留出更多空间
    ax.set_ylim(0, max(counts) * 1.2)

    # 优化整体布局并保存图像
    plt.tight_layout()
    plt.savefig(OUTPUT_IMAGE_FILE, dpi=300)

    print(f"\n带百分比的可视化直方图已成功保存为 '{OUTPUT_IMAGE_FILE}'")


if __name__ == '__main__':
    analyze_noise_distribution_with_percentage()