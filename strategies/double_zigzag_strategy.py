# coding=utf-8
# 波浪操作,zigzag操作
# time：2026.3.8 13:41
# 通过ab操作

from datetime import date
import re
import pandas as pd

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

import pandas_ta as ta

import logging
logging.basicConfig(level=logging.INFO)
class DoubleZigzagStrategy(CtaTemplate):
    """"""

    author = "qiuchun"

    # 策略参数
    macd_window: int = 50
    # 交易量
    vol: int = 10
    # 周期数量
    period: int = 30
    # zigzag的波峰长度
    legs: int = 15
    # custom window
    custom_window: int = 15

    # 计算 ZigZag 指标（默认偏差为 5%，10 段）
    deviation: float = 0.1

    # 策略变量
    #做多，止盈
    breakpoint_buy: float = 0
    stoppoint_buy: float = 0
    breakpoint_sell: float = 0
    stoppoint_sell:float=0

    parameters = ["period", "legs", "deviation", "custom_window"]
    variables = ["breakpoint_buy", "stoppoint_buy", "breakpoint_sell", "stoppoint_sell"]

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.bg: BarGenerator = BarGenerator(
            self.on_bar, 
            window=self.custom_window, 
            on_window_bar=self.on_15minute_bar
            )

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
        print("on tick")
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData) -> None:
        self.bg.update_bar(bar)

    def on_15minute_bar(self, bar: BarData) -> None:
        """
        Callback of new bar data update.
        """
        self.cancel_all()
        am: ArrayManager = self.am
        am.update_bar(bar)
        if not am.inited:
            return
        try:
            # 合约交易最后一天
            expiry_date: date = self.infer_expiry_date(self.vt_symbol)
            if not expiry_date:
                return
            # 合约交易第一天
            begin_date: date = date(
                expiry_date.year - 1, 
                month=expiry_date.month, 
                day=expiry_date.day)

            # 开盘时间
            days_to_began = (bar.datetime.date() - begin_date).days
            # 合约前期不活跃，不交易
            if days_to_began < 60:
                return

            # 计算剩余天数
            days_to_expiry = (expiry_date - bar.datetime.date()).days
            # 合约到期的前7天，全部清仓
            if days_to_expiry < 7:
                # 接近到期时平仓
                self.clearAll(bar.close_price)
                return

            # macd=diff,signal=dea,hist
            macd, signal, hist = am.macd(
                fast_period=12, 
                slow_period=26, 
                signal_period=9, 
                array=True)

            # 波谷重合，按照序号顺序，交替出现，用于后门算法判断
            zigzag, max_index, min_index = self.getZigzag(legs=self.legs, period=self.period)
            if zigzag.size == 0:
                raise ValueError("zigzag is null")
            # print(context.now)
            dir, stop_loss, break_point, F = self.isJoin(zigzag, bar.close_price, max_index, min_index)
            print("dir", dir)
            print("pos", self.pos)
            if dir == 1:
                self.breakpoint_buy = break_point
                self.stoppoint_buy = stop_loss
            elif dir == 2:
                self.breakpoint_sell = break_point
                self.stoppoint_sell = stop_loss
            elif dir == -1:
                raise ValueError("zigzag length is too short!")


            #操作
            if self.pos == 0:
                #空仓
                if bar.close_price > self.stoppoint_buy and bar.close_price < self.breakpoint_buy:
                    self.buy(bar.close_price, self.vol)
                elif bar.close_price < self.stoppoint_sell and bar.close_price > self.breakpoint_sell:
                    self.short(bar.close_price, self.vol)
            elif self.pos < 0:
                #做空
                if bar.close_price > self.stoppoint_sell or bar.close_price < self.breakpoint_sell:
                    self.cover(bar.close_price, abs(self.pos))
            else:
                #做多
                if bar.close_price > self.stoppoint_buy and bar.close_price < self.breakpoint_buy:
                    self.sell(bar.close_price, self.vol)

            self.put_event()

        except Exception as e:
            print(e)
        

        

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

    # find points
    def getZigzag(self, legs=5, period=300):
        try: 
            am: ArrayManager = self.am

            zigzag: pd.DataFrame = ta.zigzag(high=pd.Series(am.high), low=pd.Series(am.low), deviation=self.deviation, legs=legs)
            
            if zigzag.empty == False and zigzag.size > 0: 
                zigzag = zigzag.dropna()
                # print("zigzag", zigzag)
                # print(zigzag.to_string())
                # print(type(zigzag.index))
                # print(zigzag.index[-1])
                # print(zigzag.iloc[:2])
                colName = 'ZIGZAGv_{:.1f}%_{:d}'.format(self.deviation, legs)
                max_value = zigzag[colName].max()
                min_value = zigzag[colName].min()
                max_index:int = 0
                min_index:int = 0
                
                temp:pd.DataFrame = zigzag[zigzag[colName] == max_value]
                if temp.empty == False and temp.size > 0:
                    max_index = temp.index[0]
                
                temp1:pd.DataFrame = zigzag[zigzag[colName] == min_value]
                if temp1.empty == False and temp.size > 0:
                    min_index = temp1.index[0]

                return zigzag, max_index, min_index
            else:
                return pd.DataFrame(), -1, -1
        except ZeroDivisionError as e: 
            print(e)
            return pd.DataFrame(), -1, -1
        except Exception as e: 
            print(e)
            return pd.DataFrame(), -1, -1


    # 判断是上升波浪还是下降波浪,确定入场点
    # param
    # zigzag:波浪数组
    # current:当前价格
    # max_index
    # min_index 最顶点索引
    # return
    # type：波浪类型，1:表示上升波浪，2：表示下降波浪，0：表示其他波浪形态，-1：错误异常
    # joinpoint：入场点
    # stoppoint:止损点
    def isJoin(
            self, 
            zigzag: pd.DataFrame, 
            current: float, 
            max_index: int, 
            min_index: int
            ):
        try:
            row = zigzag.shape[0]
            if row < 5:
                print('Function isBuy zigzag exception.row={0}'.format(row))
                return -1, 0, 0, 0
            
            # 上升波浪
            if  min_index > max_index and zigzag.index[row-3] == min_index and zigzag.iat[row-1, 0] < 0 and zigzag.iat[row-1, 1] > zigzag.iat[row-3, 1]: 
                x:float = zigzag.iat[row-3,1] - zigzag.iat[row-2,1]
                #F天
                F:int = zigzag.index[row - 2] - zigzag.index[row - 3]
                y:float = (zigzag.iat[row-1, 1] - zigzag.iat[row-2,1])/2
                break_point:float = zigzag.iat[row-1, 1] - x
                stop_loss:float = zigzag.iat[row-1, 1] - y
                return 1, stop_loss, break_point, F
                    
                
            # 下降波浪
            elif min_index < max_index and zigzag.index[row-3] == max_index and zigzag.iat[row-1, 0] > 0 and zigzag.iat[row-1, 1] < zigzag.iat[row-3, 1]: 
                x:float = zigzag.iat[row-3, 1] - zigzag.iat[row-2, 1]
                #F天
                F:int = zigzag.index[row - 2] - zigzag.index[row - 3]
                y:float = (zigzag.iat[row-1, 1] - zigzag.iat[row-2, 1])/2
                break_point:float = zigzag.iat[row-1, 1] - x
                stop_loss:float = zigzag.iat[row-1, 1] - y
                return 2, stop_loss, break_point, F
                    
            # print("没有碰到目标形态。")
            return 0, 0, 0, 0
        except Exception as e:
            print(e)

    
    # 只能算一个大概
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