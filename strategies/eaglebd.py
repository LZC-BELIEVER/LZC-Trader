import threading
import pandas as pd
from finta import TA
from datetime import datetime
from LZCTrader.strategy import Strategy
from brokers.broker import Broker
from LZCTrader.classes.order import Order


class EAGLEBD(Strategy):
    """EAGLEBD Strategy

    策略逻辑
    --------
    1. 做空条件：生命线为蓝
    2. 做多条件：生命线为红
    """

    def __init__(
        self, instrument: str, exchange: str, parameters: dict, broker: Broker
    ) -> None:
        self.name = "EAGLEBD Strategy"
        self.params = parameters
        self.broker = broker
        self.instrument = instrument  # 品种
        self.duo_flag = False  # 多仓标志
        self.kong_flag = False  # 空仓标志
        self.duo_enter_point = 0  # 做多进场点
        self.duo_enter_bottom = 0
        self.kong_enter_point = 0  # 做空进场点
        self.kong_enter_bottom = 0
        self.trade_num = 10  # 交易手数
        self.symbol_exchange = exchange  # 交易所
        self.trade_offset = 3  # 取买几卖几
        self.duo_stopping = False
        self.kong_stopping = False
        self.above = 6
        self.cooling_count_num = 40
        self.cooling_count = self.cooling_count_num
        self.lock = threading.Lock()
        self.profit = 0

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
        new_orders = []
        min_data = self.broker.get_candles(self.instrument, granularity="1min", count=30, cut_yesterday=True)
        min_data = min_data[::-1]
        # print(data)

        if len(min_data) < 1:
            print("数据不足!")
            return None

        ema_long, ema_medium, ema_short, life_line = self.min_generate_features(min_data)

        position_dict = self.broker.get_position(self.instrument)
        print(f"{self.instrument} position", position_dict["long_tdPosition"], position_dict["long_ydPosition"], position_dict["short_tdPosition"], position_dict["short_ydPosition"] )

        print("life -1 life -2", life_line.iloc[-1], life_line.iloc[-2])
        print(f"{self.instrument}", min_data[-1:])

        RED = life_line.iloc[-1] > life_line.iloc[-2]
        BLUE = life_line.iloc[-1] < life_line.iloc[-2]
        AA = ema_short.iloc[-1] > ema_long.iloc[-1]
        BB = ema_short.iloc[-1] < ema_long.iloc[-1]
        AAPLUS = ema_short.iloc[-1] > ema_long.iloc[-1] + 2.5
        BBPLUS = ema_short.iloc[-1] < ema_long.iloc[-1] - 2.5
        WHITE = (AA and BLUE) or (BB and RED)

        temp = self.broker.get_candles(self.instrument, granularity="1s", count=1)
        current_point = temp.iloc[0]['Close']

        life_data = min_data.tail(2)
        avg_life = (life_data['Open'] + life_data['Close']) // 2
        now_life = avg_life.mean()

        if self.kong_flag or self.duo_flag:
            new_orders.append(self.dynamic_stop(life_line.iloc[-1]))

        if self.duo_stopping:
            print("remain", self.cooling_count)
            if self.cooling_count == 0:
                self.duo_stopping = False
        if self.kong_stopping:
            print("remain", self.cooling_count)
            if self.cooling_count == 0:
                self.kong_stopping = False
        if WHITE:
            self.duo_stopping = False
            self.kong_stopping = False
            if self.kong_flag:
                print("开始平空仓！！！！！！！！！！！")
                print("life_line.iloc[-1] > life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1] > ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                self.broker.relog()
                kong_exit_point = current_point + self.trade_offset
                print("kong exit point", current_point)
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
                self.kong_flag = False
                self.profit = self.profit - (current_point - self.kong_enter_point)
                print("profit", self.profit)
                self.kong_enter_point = 0
                self.write_order(type=4, point=current_point)
            if self.duo_flag:
                print("开始平多仓！！！！！！！！！！！")
                print("life_line.iloc[-1] < life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1] < ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                self.broker.relog()
                duo_exit_point = current_point - self.trade_offset
                print("duo exit point", current_point)
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
                self.duo_flag = False
                self.profit = self.profit + (current_point - self.duo_enter_point)
                print("profit", self.profit)
                self.duo_enter_point = 0
                self.write_order(type=2, point=current_point)
        if AA or RED:
            if self.kong_stopping:
                self.kong_stopping = False
            if self.kong_flag:
                print("开始平空仓！！！！！！！！！！！")
                print("life_line.iloc[-1] > life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1] > ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                self.broker.relog()
                kong_exit_point = current_point + self.trade_offset
                print("kong exit point", current_point)
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
                self.kong_flag = False
                self.profit = self.profit - (current_point - self.kong_enter_point)
                print("profit", self.profit)
                self.kong_enter_point = 0
                self.write_order(type=4, point=current_point)
            if not self.duo_flag:
                if self.duo_stopping:
                    self.cooling_count = self.cooling_count - 1
                else:
                    print("avg, nowlife, lifeline", [x for x in avg_life], now_life, life_line.iloc[-1])
                    if now_life > life_line.iloc[-1] + self.above and AAPLUS:
                        print("开始做多！！！！！！！！！！！")
                        print("life_line.iloc[-1] > life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                        print("ema_short.iloc[-1] > ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                        self.broker.relog()
                        self.duo_enter_point = current_point
                        duo_enter_point = self.duo_enter_point + self.trade_offset

                        temp = self.broker.get_candles(self.instrument, granularity="1min", count=2)
                        self.duo_enter_bottom = temp.iloc[1]['Low']
                        print("duo_enter_bottom:", self.duo_enter_bottom)

                        print("duo_enter_point:", self.duo_enter_point)
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
                        self.duo_flag = True
                        self.write_order(type=1, point=current_point)
            new_orders = [x for x in new_orders if x is not None]
            if len(new_orders) == 0:
                print("life_line.iloc[-1]  life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1]  ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                new_orders = None
        elif BB or BLUE:
            if self.duo_stopping:
                self.duo_stopping = False
            if self.duo_flag:
                print("开始平多仓！！！！！！！！！！！")
                print("life_line.iloc[-1] < life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1] < ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                self.broker.relog()
                duo_exit_point = current_point - self.trade_offset
                print("duo exit point", current_point)
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
                self.duo_flag = False
                self.profit = self.profit + (current_point - self.duo_enter_point)
                print("profit", self.profit)
                self.duo_enter_point = 0
                self.write_order(type=2, point=current_point)
            if not self.kong_flag:
                if self.kong_stopping:
                    self.cooling_count = self.cooling_count - 1
                else:
                    print("avg, nowlife, lifeline", [x for x in avg_life], now_life, life_line.iloc[-1])
                    if now_life < life_line.iloc[-1] - self.above and BBPLUS:
                        print("开始做空！！！！！！！！！！！")
                        print("life_line.iloc[-1] < life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                        print("ema_short.iloc[-1] < ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                        self.broker.relog()
                        self.kong_enter_point = current_point
                        kong_enter_point = self.kong_enter_point - self.trade_offset

                        temp = self.broker.get_candles(self.instrument, granularity="1min", count=2)
                        self.kong_enter_bottom = temp.iloc[1]['High']
                        print("kong_enter_bottom:", self.kong_enter_bottom)

                        print("kong_enter_point:", self.kong_enter_point)
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
                        self.kong_flag = True
                        self.write_order(type=3, point=current_point)
            new_orders = [x for x in new_orders if x is not None]
            if len(new_orders) == 0:
                print("life_line.iloc[-1]  life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1]  ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                new_orders = None
        else:
            new_orders = [x for x in new_orders if x is not None]
            if len(new_orders) == 0:
                print("life_line.iloc[-1]  life_line.iloc[-2]", life_line.iloc[-1], life_line.iloc[-2])
                print("ema_short.iloc[-1]  ema_long.iloc[-1]", ema_short.iloc[-1], ema_long.iloc[-1])
                new_orders = None

        # print("new_orders", new_orders)
        return new_orders

    def dynamic_stop(self, life):
        # 此为止损设置函数，用得到可以要，用不到可以不要
        sec_candles = self.broker.get_candles(self.instrument, granularity="1s", count=5)
        data = (sec_candles['Close'] + sec_candles['Open'])//2
        avg = data.mean()
        new_order = None

        temp = self.broker.get_candles(self.instrument, granularity="1min", count=1)
        temp_close_0 = temp.iloc[0]['Close']
        temp_open_0 = temp.iloc[0]['Open']
        now_min_avg = (temp_close_0 + temp_open_0) / 2
        print("now_sec_avg", avg)
        print("now_min_avg", now_min_avg)

        # 多仓动态止损
        # if avg < life - 1 or now_min_avg <= self.duo_enter_bottom or avg < self.duo_enter_point - 8:
        if avg < life - 1 or avg < self.duo_enter_point - 1:
            if self.duo_flag:
                print("多仓止损")
                print("avg,life", avg, life)
                self.broker.relog()
                temp = self.broker.get_candles(self.instrument, granularity="1s", count=1)
                duo_stopping_point = temp.iloc[0]['Close'] - self.trade_offset
                print("duo enter point", self.duo_enter_point)
                print("duo stopping point", temp.iloc[0]['Close'])
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=3,
                    offset=4,
                    price=duo_stopping_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                # self.duo_stopping = True
                self.duo_flag = False
                self.profit = self.profit + (temp.iloc[0]['Close'] - self.duo_enter_point)
                print("profit", self.profit)
                self.duo_enter_point = 0
                self.duo_stopping = True
                self.cooling_count = self.cooling_count_num
                self.write_order(type=2, point=temp.iloc[0]['Close'])
        # 空仓动态止损
        if avg > life + 1 or avg > self.kong_enter_point + 1:
            if self.kong_flag:
                print("空仓止损")
                print("avg,life", avg, life)
                self.broker.relog()
                temp = self.broker.get_candles(self.instrument, granularity="1s", count=1)
                kong_stopping_point = temp.iloc[0]['Close'] + self.trade_offset
                print("kong enter point", self.kong_enter_point)
                print("kong stopping point", temp.iloc[0]['Close'])
                new_order = Order(
                    instrument=self.instrument,
                    exchange=self.symbol_exchange,
                    direction=2,
                    offset=4,
                    price=kong_stopping_point,
                    volume=self.trade_num,
                    stopPrice=0,
                    orderPriceType=1
                )
                # self.kong_stopping = True
                self.kong_flag = False
                self.profit = self.profit - (temp.iloc[0]['Close'] - self.kong_enter_point)
                print("profit", self.profit)
                self.kong_enter_point = 0
                self.kong_stopping = True
                self.cooling_count = self.cooling_count_num
                self.write_order(type=4, point=temp.iloc[0]['Close'])
        return new_order

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
            with open(r"H:\Quant_Proj\LeopardSeek/result/order_book.txt", "a", encoding="utf-8") as f:
                f.write(line)
