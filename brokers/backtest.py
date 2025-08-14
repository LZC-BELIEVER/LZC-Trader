import pandas as pd
from datetime import datetime, timedelta, date, time
from brokers.broker import Broker
from LZCTrader.classes.order import Order
from LZCTrader.classes.bkresult import Bkresult
import BKAPI


class Backtest(Broker):
    def __init__(self, enter_license: str):

        self.lisence = enter_license
        self.api = BKAPI.Context(lisence=self.lisence)
        self.timer_thread = None
        self.bkresult_list = []

    def __repr__(self):
        return "Futures Broker Interface"

    def __str__(self):
        return "Futures Broker Interface"

    def get_candles(
            self,
            instrument: str,
            granularity: str = None,
            count: int = None,
            start_time: datetime = None,
            end_time: datetime = None,
            cut_yesterday: bool = False
    ) -> pd.DataFrame:

        interval_delta = {
            '0.5s': timedelta(seconds=0.5),
            '1s': timedelta(seconds=1),
            '1min': timedelta(minutes=1),
            '1h': timedelta(hours=1)
        }[granularity]

        if count is not None:
            if start_time is None and end_time is None:
                response = self.api.instrument.candles(
                    instrument, granularity=granularity, count=count
                )
            elif start_time is not None and end_time is None:
                end_time = start_time + interval_delta * count
                response = self.api.instrument.candles_according_time(
                    instrument, granularity=granularity, start_time=start_time, end_time=end_time
                )
            elif start_time is None and end_time is not None:
                start_time = end_time - interval_delta * count
                response = self.api.instrument.candles_according_time(
                    instrument, granularity=granularity, start_time=start_time, end_time=end_time
                )
            else:
                response = self.api.instrument.candles(
                    instrument, granularity=granularity, count=count
                )
        else:
            # count is None
            if start_time is None and end_time is None:
                raise ValueError("Start_time or end_time are required")
            response = self.api.instrument.candles_according_time(
                instrument, granularity=granularity, start_time=start_time, end_time=end_time
            )
            # try to get data
        data = self.response_to_df(response, cut_yesterday)

        return data

    def response_to_df(self, response, cut_yesterday):
        """将API响应转换为Pandas DataFrame的函数。"""
        try:
            candles = response
        except KeyError:
            raise Exception(
                "下载数据时出错 - 请检查仪器格式并重试。"
            )

        times = []
        close_price, high_price, low_price, open_price, volume = [], [], [], [], []

        # 请求为字典时，要用[]访问，不能用.访问

        for candle in candles:
            times.append(candle["actionTimestamp"])
            close_price.append(float(candle["close"]))
            high_price.append(float(candle["high"]))
            low_price.append(float(candle["low"]))
            open_price.append(float(candle["open"]))
            volume.append(float(candle["volume"]))

        dataframe = pd.DataFrame(
            {
                "Open": open_price,
                "High": high_price,
                "Low": low_price,
                "Close": close_price,
                "Volume": volume,
            }
        )

        # 将 'barTime' 转换为正确的日期时间格式，去掉微秒部分
        dataframe.index = pd.to_datetime(times, format='ISO8601')

        if cut_yesterday:
            hours = dataframe.index.hour
            get_morning = (hours >= 8) & (hours <= 16)  # 8:00 - 16:00
            get_night = ((hours >= 20) & (hours <= 23)) | ((hours >= 0) & (hours <= 5))  # 20:00 - 5:00

            # 检查是否同时包含 morning 和 night 数据
            has_morning = any(get_morning)
            has_night = any(get_night)

            if has_morning and has_night:
                # 如果同时存在，则根据当前时间决定保留哪一组
                current_hour = pd.Timestamp.now().hour  # 获取当前时间的小时
                if 8 <= current_hour <= 16:
                    selected_group = dataframe[get_morning]  # 当前是早上，保留 morning 数据
                else:
                    selected_group = dataframe[get_night]  # 当前是晚上，保留 night 数据
            elif has_morning:
                selected_group = dataframe[get_morning]  # 只有 morning 数据
            elif has_night:
                selected_group = dataframe[get_night]  # 只有 night 数据
            else:
                raise ValueError("Wrong Data!")  # 都不满足，返回完整数据

            return selected_group

        return dataframe

    def place_order(self, order: Order):
        instrument = order.instrument
        for bkresult in self.bkresult_list:
            if bkresult.instrument == instrument:
                bkresult.update_result(order)
                return
        raise ValueError("Instrument Not Found")

    def set_bklist(self, bkresult_list: list[Bkresult]):
        self.bkresult_list = bkresult_list

    def relog(self):
        pass

    def get_position(self, instrument: str) -> dict:
        return {}

    def get_backtest_candles(
            self,
            instrument: str,
            granularity: str = None,
            count: int = None,
            current_time: datetime = None,
            cut_yesterday: bool = False
    ) -> pd.DataFrame:

        '''interval_delta = {
            '0.5s': timedelta(seconds=0.5),
            '1s': timedelta(seconds=1),
            '1min': timedelta(minutes=1),
            '1h': timedelta(hours=1)
        }[granularity]'''

        supported_granularity = ['1s', '1min']
        if granularity not in supported_granularity:
            raise ValueError("Unsupported Granularity")

        for bkresult in self.bkresult_list:
            if bkresult.instrument == instrument:
                if granularity == '1s':
                    buff_data = bkresult.get_1s_buff()
                    data = self.get_historical_data(df=buff_data, end_time=current_time, granularity=granularity, num_periods=count)
                    return data
                elif granularity == '1min':
                    buff_data = bkresult.get_1min_buff()
                    data = self.get_historical_data(df=buff_data, end_time=current_time, granularity=granularity, num_periods=count)
                    return data
                else:
                    raise ValueError("Unsupported Granularity")
        raise ValueError("Instrument Not Found")

    def buff_1s_set(self, instrument: str, dt: datetime):
        granularity = '1s'

        hour_start = dt.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        # 这里不需要异步，可以直接调用
        response = self.api.instrument.candles_according_time(
            instrument=instrument,
            granularity=granularity,
            start_time=hour_start,
            end_time=hour_end
        )
        hour_data = self.response_to_df(response, False)

        for bkresult in self.bkresult_list:
            if bkresult.instrument == instrument:
                bkresult.set_1s_buff(hour_data)
                return
        raise ValueError("Instrument Not Found")

    def buff_1min_set(self, instrument: str, current_date: date):
        granularity = '1min'

        day_start = datetime.combine(current_date, time.min)
        day_end = datetime.combine(current_date, time.max)

        # 这里不需要异步，可以直接调用
        response = self.api.instrument.candles_according_time(
            instrument=instrument,
            granularity=granularity,
            start_time=day_start,
            end_time=day_end
        )
        day_data = self.response_to_df(response, False)

        for bkresult in self.bkresult_list:
            if bkresult.instrument == instrument:
                bkresult.set_1min_buff(day_data)
                return
        raise ValueError("Instrument Not Found")

    def get_historical_data(self, df, end_time, granularity, num_periods):
        """
        从指定时间开始，按时间粒度向前获取指定数量的数据

        参数：
            df: 输入的DataFrame，索引为DatetimeIndex
            end_time: 结束时间（字符串或datetime对象）
            granularity: 时间粒度 ('1s', '1min'等)
            num_periods: 需要获取的数据条数

        返回：
            指定时间范围内的DataFrame
        """
        # 确保索引是DatetimeIndex并按时间排序
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df = df.sort_index(ascending=False)  # 降序排列，最新的数据在前

        # 转换end_time为datetime对象
        end_time = pd.to_datetime(end_time)

        # 定义聚合规则
        agg_rules = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }

        # 计算开始时间（根据粒度和数量）
        if granularity == '1s':
            delta = pd.Timedelta(seconds=int(granularity[:-1]) * num_periods) # 取'1s'中的'1'
        elif granularity == '1min':
            delta = pd.Timedelta(minutes=int(granularity[:-3]) * num_periods) # 取'1min'中的'1'
        else:
            raise ValueError("不支持的频率格式")

        start_time = end_time - delta

        # 筛选时间范围内的数据
        filtered = df[(df.index >= start_time) & (df.index <= end_time)]

        # 重采样
        resampled = filtered.resample(granularity).agg(agg_rules)

        # 确保返回指定数量的数据点
        result = resampled.tail(num_periods)

        return result

    def clear_positions(self, instrument: str, clear_price: float):

        for bkresult in self.bkresult_list:
            if bkresult.instrument == instrument:
                bkresult.clear_positions(clear_price)
                return
        raise ValueError("Instrument Not Found")
