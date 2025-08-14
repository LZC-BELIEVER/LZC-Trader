from LZCTrader.classes.order import Order
from datetime import datetime

class Bkresult:

    def __init__(
        self,
        instrument: str = None,
        balance: int = 0,
        value_per_point: int = 10,
        point_change: int = 1,
    ):

        # Required attributes
        self.instrument = instrument
        self.balance = balance
        self.value_per_point = value_per_point
        self.point_change = point_change
        self.long_position = 0
        self.short_position = 0
        self.long_enter_price = 0
        self.short_enter_price = 0
        self.data_1s_buff = None
        self.data_1min_buff = None
        self.point = 0

    def update_result(self, order: Order):
        profit = 0
        if order.offset == 1:
            if order.direction == 2:
                self.long_enter_price = order.price
                self.long_position += order.volume
            else:
                self.short_enter_price = order.price
                self.short_position += order.volume
        elif order.offset == 4:
            if order.direction == 2:
                self.short_position -= order.volume
                profit = self.short_enter_price - order.price
            else:
                self.long_position -= order.volume
                profit = order.price - self.long_enter_price
        else:
            raise ValueError("Invalid offset")

        if self.long_position < 0 or self.short_position < 0:
            raise ValueError("Invalid position")

        profit = profit / self.point_change
        self.balance += profit * self.value_per_point * order.volume
        self.point += profit

    def clear_positions(self, clear_price):
        if self.long_position > 0:
            profit = clear_price - self.long_enter_price
            self.balance += profit * self.value_per_point * self.long_position
            self.point += profit
            self.long_position = 0
        if self.short_position > 0:
            profit = self.short_enter_price - clear_price
            self.balance += profit * self.value_per_point * self.short_position
            self.point += profit
            self.short_position = 0
        return

    def set_1s_buff(self, buff_data):
        self.data_1s_buff = buff_data

    def get_1s_buff(self):
        return self.data_1s_buff

    def set_1min_buff(self, buff_data):
        self.data_1min_buff = buff_data

    def get_1min_buff(self):
        return self.data_1min_buff

