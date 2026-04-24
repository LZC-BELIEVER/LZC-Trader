import os
import threading
import pandas as pd
import numpy as np
from datetime import datetime
from LZCTrader.strategy import Strategy
from brokers.broker import Broker
from LZCTrader.classes.order import Order


class MomentumReversal_IF(Strategy):
    """动量+反转策略（IF合约）

    策略逻辑
    --------
    1. 计算动量因子、反转因子和成交量冲击因子
    2. 综合因子标准化后加权
    3. 截面排序，做多最强，做空最弱
    4. 每5/15分钟调仓
    """

    def __init__(
        self, instrument: str, exchange: str, point_change: float, parameters: dict, broker: Broker
    ) -> None:
        self.params = parameters
        self.broker = broker
        self.instrument = instrument  # 品种
        self.point_change = point_change
        self.duo_flag = False  # 多仓标志
        self.kong_flag = False  # 空仓标志
        self.duo_enter_point = 0  # 做多进场点
        self.kong_enter_point = 0  # 做空进场点
        self.trade_num = 1  # 股指期货默认1手
        self.symbol_exchange = exchange  # 交易所
        self.last_rebalance_time = None  # 上次调仓时间
        self.rebalance_interval = parameters.get('rebalance_interval', 5)  # 调仓间隔（分钟）
        self.momentum_period = parameters.get('momentum_period', 15)  # 动量周期（分钟）
        self.reversal_period = parameters.get('reversal_period', 5)  # 反转周期（分钟）
        self.volume_period = parameters.get('volume_period', 30)  # 成交量周期（分钟）
        self.stop_loss_pct = parameters.get('stop_loss_pct', 0.005)  # 止损比例
        
        self.lock = threading.Lock()
        self.current_point = 0
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def calculate_factors(self, data: pd.DataFrame):
        """计算因子"""
        if len(data) < max(self.momentum_period, self.volume_period) + 1:
            return None, None, None
        
        # 价格数据
        close = data['Close']
        volume = data['Volume']
        
        # 动量因子：(当前价格 - 15分钟前价格) / 15分钟前价格
        if len(close) > self.momentum_period:
            momentum = (close.iloc[-1] - close.iloc[-self.momentum_period-1]) / close.iloc[-self.momentum_period-1]
        else:
            momentum = 0
        
        # 反转因子：-(当前价格 - 5分钟前价格) / 5分钟前价格
        if len(close) > self.reversal_period:
            reversal = -(close.iloc[-1] - close.iloc[-self.reversal_period-1]) / close.iloc[-self.reversal_period-1]
        else:
            reversal = 0
        
        # 成交量冲击因子：当前成交量 / 30分钟移动平均成交量
        if len(volume) > self.volume_period:
            volume_ma = volume.rolling(window=self.volume_period).mean().iloc[-1]
            if volume_ma > 0:
                volume_shock = volume.iloc[-1] / volume_ma
            else:
                volume_shock = 0
        else:
            volume_shock = 0
        
        return momentum, reversal, volume_shock

    def generate_signal(self, dt: datetime):
        """生成交易信号"""
        new_orders = []
        self.dt = dt
        
        # 检查是否到调仓时间
        if self.last_rebalance_time is None:
            self.last_rebalance_time = dt
        else:
            time_diff = (dt - self.last_rebalance_time).total_seconds() / 60
            if time_diff < self.rebalance_interval:
                return new_orders
            self.last_rebalance_time = dt
        
        # 获取分钟级数据
        min_data = self.broker.get_backtest_candles(
            instrument=self.instrument, 
            granularity="1min", 
            count=max(self.momentum_period, self.volume_period) + 1, 
            current_time=dt
        )
        
        if min_data is None or len(min_data) < max(self.momentum_period, self.volume_period) + 1:
            return new_orders
        
        # 计算因子
        momentum, reversal, volume_shock = self.calculate_factors(min_data)
        if momentum is None:
            return new_orders
        
        # 获取当前价格
        temp = self.broker.get_backtest_candles(
            instrument=self.instrument, 
            granularity="1s", 
            count=1, 
            current_time=dt
        )
        if temp is None or len(temp) == 0:
            return new_orders
        else:
            current_point = temp.iloc[0]['Close']
            self.current_point = current_point
        
        # 平仓现有仓位
        if self.duo_flag:
            # 平多仓
            new_order = Order(
                instrument=self.instrument,
                exchange=self.symbol_exchange,
                direction=3,
                offset=4,
                price=current_point,
                volume=self.trade_num,
                stopPrice=0,
                orderPriceType=1
            )
            new_orders.append(new_order)
            self.write_order(dt, 2, current_point)
            self.duo_flag = False
            self.duo_enter_point = 0
        
        if self.kong_flag:
            # 平空仓
            new_order = Order(
                instrument=self.instrument,
                exchange=self.symbol_exchange,
                direction=2,
                offset=4,
                price=current_point,
                volume=self.trade_num,
                stopPrice=0,
                orderPriceType=1
            )
            new_orders.append(new_order)
            self.write_order(dt, 4, current_point)
            self.kong_flag = False
            self.kong_enter_point = 0
        
        # 生成新信号
        # 计算综合因子（简化版，实际应该标准化）
        score = momentum + reversal + 0.5 * volume_shock
        
        # 根据score决定多空
        if score > 0:
            # 做多
            self.duo_enter_point = current_point
            new_order = Order(
                instrument=self.instrument,
                exchange=self.symbol_exchange,
                direction=2,
                offset=1,
                price=current_point,
                volume=self.trade_num,
                stopPrice=0,
                orderPriceType=1
            )
            new_orders.append(new_order)
            self.write_order(dt, 1, current_point)
            self.duo_flag = True
        elif score < 0:
            # 做空
            self.kong_enter_point = current_point
            new_order = Order(
                instrument=self.instrument,
                exchange=self.symbol_exchange,
                direction=3,
                offset=1,
                price=current_point,
                volume=self.trade_num,
                stopPrice=0,
                orderPriceType=1
            )
            new_orders.append(new_order)
            self.write_order(dt, 3, current_point)
            self.kong_flag = True
        # score=0时不操作
        
        # 日内限制：15:00前平仓
        if dt.hour == 15 and dt.minute == 0:
            self.reset()
        
        return new_orders

    def dynamic_stop(self, life):
        """动态止损"""
        new_orders = []
        
        # 多仓止损
        if self.duo_flag:
            if self.current_point < self.duo_enter_point * (1 - self.stop_loss_pct):
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=3,
                    offset=4,
                    price=self.current_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(self.dt, 2, self.current_point)
                self.duo_flag = False
                self.duo_enter_point = 0
        
        # 空仓止损
        if self.kong_flag:
            if self.current_point > self.kong_enter_point * (1 + self.stop_loss_pct):
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=2,
                    offset=4,
                    price=self.current_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(self.dt, 4, self.current_point)
                self.kong_flag = False
                self.kong_enter_point = 0
        
        return new_orders

    def write_order(self, dt, type, point):
        """写入订单记录"""
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # 根据类型生成不同的订单行
        if type == 1:  # 买开
            line = f"{time_str},{self.instrument},open,long,{point}\n"
        elif type == 2:  # 买平
            line = f"{time_str},{self.instrument},close,long,{point}\n"
        elif type == 3:  # 卖开
            line = f"{time_str},{self.instrument},open,short,{point}\n"
        elif type == 4:  # 卖平
            line = f"{time_str},{self.instrument},close,short,{point}\n"
        else:
            raise ValueError("Invalid type")

        # 创建目标文件夹路径
        base_dir = os.path.join(self.root_dir, "backtest_result")
        instrument_dir = os.path.join(base_dir, self.instrument)
        os.makedirs(instrument_dir, exist_ok=True)
        output_file = os.path.join(instrument_dir, "result.txt")

        with self.lock:
            try:
                # 写入文件
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                print(f"写入订单记录失败: {e}")

    def reset(self):
        """重置仓位"""
        if self.kong_flag:
            self.write_order(self.dt, 4, self.current_point)
            self.kong_flag = False
        if self.duo_flag:
            self.write_order(self.dt, 2, self.current_point)
            self.duo_flag = False
        self.kong_enter_point = 0
        self.duo_enter_point = 0
        self.broker.clear_positions(self.instrument, self.current_point)
        self.current_point = 0
