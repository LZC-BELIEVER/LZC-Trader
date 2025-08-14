from datetime import datetime, timedelta

class EntitySpec(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.buff = None

    def candles(self, instrument, granularity, count):
        if self.ctx.sse_client is None:
            print("SSE客户端尚未连接")
            return None

        # 这里不需要异步，可以直接调用
        response = self.ctx.sse_client.get_data(
            symbol=instrument,
            candlenums=count,
            granularity=granularity
        )
        return response

    def candles_according_time(self, instrument, granularity, start_time, end_time):
        if self.ctx.sse_client is None:
            print("SSE客户端尚未连接")
            return None

        # 这里不需要异步，可以直接调用
        response = self.ctx.sse_client.get_data_according_time(
            symbol=instrument,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time
        )
        return response

    def positions(self, instrument):
        if self.ctx.sse_client is None:
            print("SSE客户端尚未连接")
            return None

        # 这里不需要异步，可以直接调用
        response = self.ctx.sse_client.get_position(
            symbol=instrument
        )
        return response




