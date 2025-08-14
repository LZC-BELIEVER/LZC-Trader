import os
import threading
import pandas as pd
from finta import TA
from datetime import datetime
from LZCTrader.strategy import Strategy
from brokers.broker import Broker
from LZCTrader.classes.order import Order


class MATP(Strategy):
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
        self.duo_flag = False  # 多仓标志
        self.kong_flag = False  # 空仓标志
        self.duo_enter_point = 0  # 做多进场点
        self.kong_enter_point = 0  # 做空进场点
        self.trade_num = 10  # 交易手数
        self.symbol_exchange = exchange  # 交易所
        self.point_change = point_change
        self.duo_stopping = False
        self.kong_stopping = False

        self.above = 5
        self.add = 5
        self.max_stop = 3
        self.trade_offset = 3
        self.take_profit = 5
        self.diff = 1
        self.cooling_count_num = 30

        self.above = self.above * self.point_change
        self.add = self.add * self.point_change
        self.max_stop = self.max_stop * self.point_change
        self.diff = self.diff * self.point_change
        self.take_profit = self.take_profit * self.point_change
        self.trade_offset = self.trade_offset * self.point_change

        self.cooling_count = self.cooling_count_num
        self.lock = threading.Lock()
        self.profit = 0
        self.dt = None
        self.current_point = 0
        self.avg = 0
        self.cooling = 0

    def generate_ma(self, data: pd.DataFrame):
        data = (data['Open'] + data['Close']) / 2.0
        ma_short = data.rolling(window=self.params["short_ma_period"]).mean()
        ma_long = data.rolling(window=self.params["long_ma_period"]).mean()

        return ma_short, ma_long

    def generate_signal(self, dt: datetime):
        # 此为函数主体，根据指标进行计算，产生交易信号并下单，程序只会调用这一个函数进行不断循环
        self.dt = dt
        # now = datetime.now().strftime("%H:%M:%S")

        new_orders = []
        min_data = self.broker.get_candles(instrument=self.instrument, granularity="1min", count=30, cut_yesterday=True)

        if len(min_data) < 10:
            return new_orders

        ma_short, ma_long = self.generate_ma(min_data)

        last_short = ma_short.iloc[-1]
        last_long = ma_long.iloc[-1]

        temp = self.broker.get_candles(instrument=self.instrument, granularity="tick", count=1, cut_yesterday=True)
        if temp is None or len(temp) == 0:
            return new_orders
        else:
            current_point = temp.iloc[0]['Close']

        self.current_point = current_point

        if self.kong_flag or self.duo_flag:
            new_orders.extend(self.dynamic_stop())

        if self.duo_stopping:
            if last_short < last_long:
                self.duo_stopping = False
        if self.kong_stopping:
            if last_short > last_long:
                self.kong_stopping = False

        if not self.duo_stopping:
            if not self.duo_flag:
                if last_short > last_long + self.diff:
                    print(f"{self.instrument} OPENING LONG! enter: {current_point} ")
                    self.duo_enter_point = current_point
                    duo_enter_point = self.duo_enter_point + self.trade_offset
                    self.broker.relog()
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
                    self.write_order(1, duo_enter_point)
                    self.duo_flag = True
                    self.duo_stopping = True
        if not self.kong_stopping:
            if not self.kong_flag:
                if last_short < last_long - self.diff:
                    print(f"{self.instrument} OPENING SHORT! enter: {current_point}")
                    self.kong_enter_point = current_point
                    kong_enter_point = self.kong_enter_point - self.trade_offset
                    # 做空信号
                    self.broker.relog()
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
                    self.write_order(3, kong_enter_point)
                    self.kong_flag = True
                    self.kong_stopping = True

        if self.duo_flag:
            if self.current_point > self.duo_enter_point + self.take_profit:
                print(f"{self.instrument} CLOSING LONG! enter: {self.duo_enter_point} exit: {current_point}")
                duo_exit_point = current_point - self.trade_offset
                self.broker.relog()
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
                self.profit = self.profit + (current_point - self.duo_enter_point)
                self.write_order(2, duo_exit_point)
                self.duo_flag = False
                self.duo_enter_point = 0
        if self.kong_flag:
            if self.current_point < self.kong_enter_point - self.take_profit:
                print(f"{self.instrument} CLOSING SHORT! enter: {self.kong_enter_point} exit: {current_point}")
                kong_exit_point = current_point + self.trade_offset
                self.broker.relog()
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
                self.profit = self.profit - (current_point - self.kong_enter_point)
                self.write_order(4, kong_exit_point)
                self.kong_flag = False
                self.kong_enter_point = 0

        return new_orders

    def dynamic_stop(self):
        new_orders = []
        # 多仓动态止损
        if self.duo_flag:
            if self.current_point < self.duo_enter_point - self.max_stop:
                print(f"{self.instrument} STOPPING LONG! enter: {self.duo_enter_point} exit: {self.current_point}")

                duo_exit_point = self.current_point - self.trade_offset
                self.broker.relog()
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
                self.profit = self.profit + (self.current_point - self.duo_enter_point)
                self.write_order(2, duo_exit_point)
                self.duo_flag = False
                self.duo_enter_point = 0
                self.cooling_count = self.cooling_count_num
                self.duo_stopping = True

        # 空仓动态止损
        if self.kong_flag:
            if self.current_point > self.kong_enter_point + self.max_stop:
                print(f"{self.instrument} STOPPING SHORT! enter: {self.kong_enter_point} exit: {self.current_point}")

                kong_exit_point = self.current_point + self.trade_offset
                self.broker.relog()
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
                self.profit = self.profit - (self.current_point - self.kong_enter_point)
                self.write_order(4, kong_exit_point)
                self.kong_flag = False
                self.kong_enter_point = 0
                self.cooling_count = self.cooling_count_num
                self.kong_stopping = True

        return new_orders

    def write_order(self, type, point):
        now = datetime.now().strftime("%m-%d %H:%M:%S")
        if type == 1:  # 买开
            line = f"{now} {self.instrument}，买开，{point}，profit {self.profit} \n"
        elif type == 2:  # 买平
            line = f"{now} {self.instrument}，买平，{point}，profit {self.profit}  \n"
        elif type == 3:  # 卖开
            line = f"{now} {self.instrument}，卖开，{point}，profit {self.profit}  \n"
        elif type == 4:  # 卖平
            line = f"{now} {self.instrument}，卖平，{point}，profit {self.profit} \n"
        else:
            raise ValueError("Invalid type")

        with self.lock:
            with open(r"H:\Quant_Proj\LZCTrader/result/order_book.txt", "a", encoding="utf-8") as f:
                f.write(line)

    def reset(self):
        pass







