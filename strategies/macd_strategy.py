#macd策略

import numpy as np

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class MACDStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    macd_window: int = 50

    parameters = ["macd_window"]
    variables = []

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

        self.bg: BarGenerator = BarGenerator(self.on_bar)
        self.am: ArrayManager = ArrayManager()

        self.load_bar(10)

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        """
        Callback of new bar data update.
        """
        self.cancel_all()

        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return
        
        pre = -4
        macd, signal, hist = am.macd(fast_period = 12, slow_period = 26, signal_period = 9, array = True) 

        is_positive:bool = macd[pre] > 0 and signal[pre] > 0 and macd[-1] > 0 and signal[-1] > 0
        is_negative:bool = macd[pre] < 0 and signal[pre] < 0 and macd[-1] < 0 and signal[-1] < 0

        cross_over: bool = hist[-1] > 0 and (macd[pre] < signal[pre] and macd[-1] > signal[-1])
        cross_below: bool = hist[-1] < 0 and macd[pre] > signal[pre] and macd[-1] < signal[-1]

        if is_positive and cross_over:
            if self.pos == 0:
                self.buy(bar.close_price, 1)
            elif self.pos < 0:
                self.cover(bar.close_price, 1)
                self.buy(bar.close_price, 1)

        elif is_negative and cross_below:
            if self.pos == 0:
                self.short(bar.close_price, 1)
            elif self.pos > 0:
                self.sell(bar.close_price, 1)
                self.short(bar.close_price, 1)

        self.put_event()

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData) -> None:
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        """
        Callback of stop order update.
        """
        pass
