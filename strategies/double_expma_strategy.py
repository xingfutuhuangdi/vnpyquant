#双expma策略交易
#time:2026.3.7 1:08

#i2605.DCE 营利不是很多，但是收益曲线大部分是正的。
from datetime import datetime as Datetime, date
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


class DoubleEXPMaStrategy(CtaTemplate):
    """"""

    author = "qiuchun"

    fast_window: int = 20
    slow_window: int = 60

    fast_ma0: float = 0.0
    fast_ma1: float = 0.0
    slow_ma0: float = 0.0
    slow_ma1: float = 0.0

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1"]

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

        fast_ma: np.ndarray = am.ema(self.fast_window, array=True)
        self.fast_ma0 = fast_ma[-1]
        self.fast_ma1 = fast_ma[-2]

        slow_ma: np.ndarray = am.ema(self.slow_window, array=True)
        self.slow_ma0 = slow_ma[-1]
        self.slow_ma1 = slow_ma[-2]

        cross_over: bool = self.fast_ma0 > self.slow_ma0 and self.fast_ma1 < self.slow_ma1
        cross_below: bool = self.fast_ma0 < self.slow_ma0 and self.fast_ma1 > self.slow_ma1

        if cross_over:
            if self.pos == 0:
                self.buy(bar.close_price, 1)
            elif self.pos < 0:
                self.cover(bar.close_price, 1)
                self.buy(bar.close_price, 1)

        elif cross_below:
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
    
    
    #清仓
    def clearAll(self, close_price) -> None:
        # 接近到期时平仓
        if self.pos != 0:
            if self.pos > 0:
                self.sell(close_price - 5, abs(self.pos))
            else:
                self.cover(close_price + 5, abs(self.pos))
            self.write_log(f"平仓，剩余持仓: {self.pos}")

    #只能算一个大概
    def infer_expiry_date(self, symbol):
        """从合约代码推断到期日期"""
        # 匹配合约代码中的年月信息
        match = re.search(r'[A-Z]+(\d+)', symbol.upper())
        if not match:
            return None
            
        expiry_code = match.group(1)
        if len(expiry_code) < 4:
            return None
            
        # 解析年月信息
        year_suffix = int(expiry_code[-4:-2])
        month = int(expiry_code[-2:])
        
        # 处理年份
        year = 2000 + year_suffix if year_suffix < 50 else 1900 + year_suffix
        
        # 返回该月第一天作为到期日
        return date(year, month, 1)
