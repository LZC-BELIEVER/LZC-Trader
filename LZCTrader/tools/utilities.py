import re
import yaml
from datetime import datetime, time, timedelta


def read_yaml(file_path: str) -> dict:
    """Function to read and extract contents from .yaml file.

    Parameters
    ----------
    file_path : str
        The absolute filepath to the yaml file.

    Returns
    -------
    dict
        The loaded yaml file in dictionary form.
    """
    with open(file_path, "r", encoding='utf-8') as f:
        return yaml.safe_load(f)


def extract_letters(instrument: str):
    # 匹配连续字母直到遇到数字
    match = re.match(r'^([a-zA-Z]+)\d+', instrument)
    return match.group(1) if match else None


def extract_hours_from_ranges(daily_test_time):
    """提取时间段内所有完整小时"""
    hours = set()

    # 处理时间段（支持单时段和双时段）
    ranges = []
    if len(daily_test_time) == 2:
        ranges.append((time(*daily_test_time[0]), time(*daily_test_time[1])))
    else:
        ranges.append((time(*daily_test_time[0]), time(*daily_test_time[1])))
        ranges.append((time(*daily_test_time[2]), time(*daily_test_time[3])))

    # 遍历每个时间段
    for start, end in ranges:
        current = datetime.combine(datetime.today(), start)
        end_dt = datetime.combine(datetime.today(), end)

        # 处理跨日情况（如23:00-01:00）
        if end_dt < current:
            end_dt += timedelta(days=1)

        # 收集所有完整小时
        while current <= end_dt:
            hours.add(current.hour)
            current += timedelta(hours=1)

    return sorted(hours)

def get_trading_hours(start_date, end_date, periods):
    """计算所有交易小时数"""
    total_hours = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 5:  # 跳过周末
            for start_time, end_time in periods:
                delta = datetime.combine(current_date, end_time) - datetime.combine(current_date, start_time)
                total_hours += delta.total_seconds() / 3600
        current_date += timedelta(days=1)
    return int(total_hours)
