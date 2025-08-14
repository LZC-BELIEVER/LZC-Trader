import os
import threading
import pandas as pd
from finta import TA
from datetime import datetime
from LZCTrader.strategy import Strategy
from brokers.broker import Broker
from LZCTrader.classes.order import Order


class BDWZ(Strategy):
    """EAGLEBD Strategy

    策略逻辑
    --------
    1. 做空条件：生命线为蓝
    2. 做多条件：生命线为红
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
        self.trade_num = 10  # 交易手数
        self.symbol_exchange = exchange  # 交易所
        self.duo_stopping = False
        self.kong_stopping = False

        self.above = 5
        self.add = 5
        self.max_stop = 3
        self.cooling_count_num = 40

        self.above = self.above * self.point_change
        self.add = self.add * self.point_change
        self.max_stop = self.max_stop * self.point_change

        self.cooling_count = self.cooling_count_num
        self.lock = threading.Lock()
        self.profit = 0
        self.dt = None
        self.current_point = 0
        self.avg = 0

    def min_generate_features(self, data: pd.DataFrame):
        # 在此函数中，根据传入参数data，计算出你策略所需的MA，EMA等指标
        if len(data) < 2*self.params["medium_ema_period"]:
            if len(data) < 2:
                empty_series = pd.Series(dtype=float, index=data.index)
                return empty_series, empty_series, empty_series, empty_series
            else:
                ema_long = TA.EMA(data, len(data))
                ema_medium = TA.EMA(data, len(data)//2)
                ema_short = TA.EMA(data, len(data)//4)
                temp_df = pd.DataFrame({
                    'close': ema_medium,
                    'open': ema_medium,
                    'high': ema_medium,  # 补充high
                    'low': ema_medium  # 补充low
                })
                life = TA.EMA(temp_df, len(data))
                life = life.squeeze()
                return ema_long, ema_medium, ema_short, life

        ema_long = TA.EMA(data, self.params["long_ema_period"])
        ema_medium = TA.EMA(data, self.params["medium_ema_period"])
        ema_short = TA.EMA(data, self.params["short_ema_period"])

        # ema = ema_medium.to_frame()
        temp_df = pd.DataFrame({
            'close': ema_medium,
            'open': ema_medium,
            'high': ema_medium,  # 补充high
            'low': ema_medium  # 补充low
        })
        life = TA.EMA(temp_df, self.params["medium_ema_period"])
        life = life.squeeze()

        return ema_long, ema_medium, ema_short, life

    def generate_signal(self, dt: datetime):
        # 此为函数主体，根据指标进行计算，产生交易信号并下单，程序只会调用这一个函数进行不断循环
        self.dt = dt

        new_orders = []
        min_data = self.broker.get_backtest_candles(instrument=self.instrument, granularity="1min", count=30, current_time=dt)
        #min_data = min_data[::-1]
        #print(min_data)

        if len(min_data) < 16:
            return new_orders

        ema_long, ema_medium, ema_short, life_line = self.min_generate_features(min_data)

        RED = life_line.iloc[-1] > life_line.iloc[-2]
        BLUE = life_line.iloc[-1] < life_line.iloc[-2]
        AA = ema_short.iloc[-1] > ema_long.iloc[-1]
        BB = ema_short.iloc[-1] < ema_long.iloc[-1]
        AAPLUS = ema_short.iloc[-1] > ema_long.iloc[-1] + self.add
        BBPLUS = ema_short.iloc[-1] < ema_long.iloc[-1] - self.add
        WHITE = (AA and BLUE) or (BB and RED)

        temp = self.broker.get_backtest_candles(instrument=self.instrument, granularity="1s", count=1, current_time=dt)
        if temp is None or len(temp) == 0:
            return new_orders
        else:
            current_point = temp.iloc[0]['Close']

        self.current_point = current_point
        # print(dt, temp)

        temp_1= self.broker.get_backtest_candles(instrument=self.instrument, granularity="1s", count=5, current_time=dt)
        if temp_1 is None or len(temp_1) < 5:
            return new_orders
        else:
            avg = temp_1['Close'].mean()

        self.avg = avg

        if self.kong_flag or self.duo_flag:
            new_orders.extend(self.dynamic_stop(life_line.iloc[-1]))

        if WHITE:
            if self.kong_flag:
                kong_exit_point = current_point
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=2,
                    offset=4,
                    price=kong_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(dt, 4, kong_exit_point)
                self.kong_flag = False
                self.kong_enter_point = 0
            if self.duo_flag:
                duo_exit_point = current_point
                # 做空信号
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=3,
                    offset=4,
                    price=duo_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(dt, 2, duo_exit_point)
                self.duo_flag = False
                self.duo_enter_point = 0
        if AA or RED:
            if self.kong_flag:
                kong_exit_point = current_point
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=2,
                    offset=4,
                    price=kong_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(dt, 4, kong_exit_point)
                self.kong_flag = False
                self.kong_enter_point = 0
            if not self.duo_flag:
                if self.current_point > life_line.iloc[-1] + self.above and AAPLUS:
                    self.duo_enter_point = current_point
                    duo_enter_point = self.duo_enter_point
                    new_order = Order(
                        instrument=self.instrument,
                        exchange=self.symbol_exchange,
                        direction=2,
                        offset=1,
                        price=duo_enter_point,
                        volume=self.trade_num,
                        stopPrice=0,
                        orderPriceType=1
                    )
                    new_orders.append(new_order)
                    self.write_order(dt, 1, duo_enter_point)
                    self.duo_flag = True
        elif BB or BLUE:
            if self.duo_flag:
                duo_exit_point = current_point
                # 做空信号
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=3,
                    offset=4,
                    price=duo_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(dt, 2, duo_exit_point)
                self.duo_flag = False
                self.duo_enter_point = 0
            if not self.kong_flag:
                if self.current_point < life_line.iloc[-1] - self.above and BBPLUS:
                    self.kong_enter_point = current_point
                    kong_enter_point = self.kong_enter_point
                    # 做空信号
                    new_order = Order(
                        instrument=self.instrument,
                        exchange=self.symbol_exchange,
                        direction=3,
                        offset=1,
                        price=kong_enter_point,
                        volume=self.trade_num,
                        stopPrice=0,
                        orderPriceType=1
                    )
                    new_orders.append(new_order)
                    self.write_order(dt, 3, kong_enter_point)
                    self.kong_flag = True
        else:
            pass

        return new_orders

    def dynamic_stop(self, life):
        new_orders = []
        # 多仓动态止损
        # if avg < life - 1 or now_min_avg <= self.duo_enter_bottom or avg < self.duo_enter_point - 8:
        if self.duo_flag:
            if self.avg < life - 1 or self.avg < self.duo_enter_point - self.max_stop:

                duo_exit_point = self.current_point
                # 做空信号
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=3,
                    offset=4,
                    price=duo_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(self.dt, 2, duo_exit_point)
                self.duo_flag = False
                self.duo_enter_point = 0

        # 空仓动态止损
        if self.kong_flag:
            if self.avg > life + 1 or self.avg > self.kong_enter_point + self.max_stop:

                kong_exit_point = self.current_point
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=2,
                    offset=4,
                    price=kong_exit_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                new_orders.append(new_order)
                self.write_order(self.dt, 4, kong_exit_point)
                self.kong_flag = False
                self.kong_enter_point = 0

        return new_orders

    def write_order(self, dt, type, point):
        time = dt.strftime("%m-%d %H:%M:%S")

        # 根据类型生成不同的订单行
        if type == 1:  # 买开
            line = f"{time},{self.instrument},open,long,{point}\n"
        elif type == 2:  # 买平
            line = f"{time},{self.instrument},close,long,{point}\n"
        elif type == 3:  # 卖开
            line = f"{time},{self.instrument},open,short,{point}\n"
        elif type == 4:  # 卖平
            line = f"{time},{self.instrument},close,short,{point}\n"
        else:
            raise ValueError("Invalid type")

        # 创建目标文件夹路径
        base_dir = r"H:\Quant_Proj\LeopardBKT\backtest_result"
        instrument_dir = os.path.join(base_dir, self.instrument)
        output_file = os.path.join(instrument_dir, "result.txt")

        with self.lock:
            try:
                # 写入文件
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                print(f"写入订单记录失败: {e}")

    def reset(self):
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
        self.avg = 0





