# coding=utf-8
#波浪操作,zigzag操作
# 频率3600s，150周期，order=10 碳酸锂：123%
# 频率3600s，150周期，order=10 DCE.I：-29%
# 频率3600s，37周期，order=5,DCE.I：-34%
# 频率3600s，150周期，order=10 焦煤：42.86%
# 频率3600s，37周期，order=5,焦煤：10.95%
# 频率3600s，37周期，order=5,多晶硅：-72%

from datetime import datetime as Datetime, date
import re
import numpy as np
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


class ZigzagStrategy(CtaTemplate):
    """"""

    author = "qiuchun"

    #策略参数
    macd_window: int = 50
    #交易量
    vol:int = 10
    #周期数量
    period:int = 20
    #zigzag的波峰长度
    legs:int = 10

    #策略变量
    # 计算 ZigZag 指标（默认偏差为 5%，10 段）
    deviation:float = 0.1

    parameters = ["period", "legs", "deviation"]
    variables = []

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.write_log(self.vt_symbol)

        self.bg: BarGenerator = BarGenerator(self.on_bar)
        self.am: ArrayManager = ArrayManager()


        self.load_bar(self.period)

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

        #合约到期的前十天，全部清仓
        expiry_date:date  = self.infer_expiry_date(self.vt_symbol)
        if not expiry_date:
            return
        # 计算剩余天数
        days_to_expiry = (expiry_date - bar.datetime.date()).days 
        if days_to_expiry < 7:
            # 接近到期时平仓
            if self.pos != 0:
                if self.pos > 0:
                    self.sell(bar.close_price - 5, abs(self.pos))
                else:
                    self.cover(bar.close_price + 5, abs(self.pos))
                self.write_log(f"因临近到期平仓，剩余持仓: {self.pos}")
            return

        #macd=diff,signal=dea,hist
        macd, signal, hist = am.macd(fast_period = 12, slow_period = 26, signal_period = 9, array = True) 

        #波谷重合，按照序号顺序，交替出现，用于后门算法判断
        zigzag, max_val, min_val = self.getZigzag(legs= self.legs, period = self.period)
        if zigzag.size == 0:
            print("zigzag is null")
            return 
        # print(context.now)
        dir, joinpoint, stoppoint = self.isBuy(zigzag, bar.close_price, max_val, min_val)
        if dir == 1:
            self.stoppoint_buy = stoppoint
        elif dir == 2:
            self.stoppoint_sell = stoppoint
        
        #做多
        is_positive = (dir == 1 and macd[-1] > 0)
        #做空
        is_negative = (dir == 2 and macd[-1] < 0)

        if is_positive:
            if self.pos == 0:
                self.buy(bar.close_price, self.vol)
                self.stoploss_long = bar.close_price
            elif self.pos < 0:
                self.cover(bar.close_price, abs(self.pos))
                self.buy(bar.close_price, self.vol)

        elif is_negative:
            if self.pos == 0:
                self.short(bar.close_price, self.vol)
            elif self.pos > 0:
                self.sell(bar.close_price, abs(self.pos))
                self.short(bar.close_price, self.vol)

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

    # find points
    def getZigzag(self, legs=5, period=300):
        am: ArrayManager = self.am

        print('pd')
        print(am.high)
        zigzag:pd.DataFrame = ta.zigzag(high=pd.Series(am.high), low=pd.Series(am.low), close=pd.Series(am.close), deviation=self.deviation, legs=legs)
        
        if zigzag.empty == False and zigzag.size > 0:
            zigzag = zigzag.dropna()
            print("zigzag", zigzag)
            # print(zigzag.to_string())
            # print(type(zigzag.index))
            # print(zigzag.index[-1])
            # print(zigzag.iloc[:2])
            colName = 'ZIGZAGv_{:.1f}%_{:d}'.format(self.deviation, legs)
            return zigzag, zigzag[colName].max(), zigzag[colName].min()
            
        return zigzag, 0, 0

    #判断是上升波浪还是下降波浪,确定入场点
    #param
    #price_series：k线队列
    #pv_idx:波浪index数组
    #current:当前价格
    #index_maxpeak：最高点索引
    #index_minvalley： 最顶点索引
    #return
    # type：波浪类型，1:表示上升波浪，2：表示下降波浪，0：表示其他波浪形态，-1：错误异常
    # joinpoint：入场点
    # stoppoint:止损点
    def isBuy(self, zigzag:pd.DataFrame, current, maxpeak, minvalley):
        row = zigzag.shape[0]
        if row < 5:
            print('Function isBuy zigzag exception.row={0}'.format(row))
            return -1, 0, 0
        
        # print(zigzag)

        # print(zigzag.iat[row-1,0])
        # print(zigzag.iat[row-1,1])
        # print(zigzag.iat[row-3,1])
        #上升波浪
        if zigzag.iat[row-1,0] < 0 and zigzag.iat[row-1,1] > zigzag.iat[row-3,1]:
            if abs(minvalley - zigzag.iat[row-3,1]) < zigzag.iat[row-3,1]*0.05 and current - zigzag.iat[row-1,1] > (zigzag.iat[row-2,1] - zigzag.iat[row-1,1])/2:
                #入场点
                print("底部")
                print("出现上升波段,最低波谷：{0}入场点：{1},止损点：{2},股价：{3}".format(minvalley, zigzag.iat[row-2,1], zigzag.iat[row-1,1], current))
                print("索引.入场点：{0},止损点：{1}".format(zigzag.index[row-2], zigzag.index[row-1]))
                return 1, zigzag.iat[row-2,1], zigzag.iat[row-1,1]
            
        #下降波浪
        elif zigzag.iat[row-1,0] > 0 and zigzag.iat[row-1,1] < zigzag.iat[row-3,1]: 
            if abs(maxpeak - zigzag.iat[row-3,1]) < zigzag.iat[row-3,1]*0.05 and current - zigzag.iat[row-1,1] < (zigzag.iat[row-2,1] - zigzag.iat[row-1,1])/2:            
                #入场点
                print("出现顶部")
                print("出现下降波段,最高波峰：{0},入场点：{1},止损点：{2},股价：{3}".format(maxpeak, zigzag.iat[row-2,1], zigzag.iat[row-1,1], current))
                print("索引.入场点：{0},止损点：{1}".format(zigzag.index[row-2], zigzag.index[row-1]))
                return 2, zigzag.iat[row-2,1], zigzag.iat[row-1,1]
        print("没有碰到目标形态。")
        return 0, 0, 0

    #根据波形确定止损点
    def isStop(self, zigzag:pd.DataFrame, stoppoint, current, state):
        row = zigzag.shape[0]

        if row < 2:
            print('Function isStop zigzag exception.row = '.format(row))
            return -1, 0
        #做多
        if state == 1:
            #更新止损点
            nearestValley = min(zigzag.iat[row-1, 1], zigzag.iat[row-2, 1])
            if nearestValley > stoppoint:
                print("更新止损点，旧止损点：{0}，新止损点：{1}".format(stoppoint,nearestValley))
                stoppoint = nearestValley
                
            if current < stoppoint:
                print("做多止损，出场点：{0}，止损点：{1}".format(current,stoppoint))
                return 1, stoppoint #多平
            else:
                #打印
                # print("继续做多，当前价格：{0}".format(current,stoppoint))
                return 2, stoppoint
        
        #做空
        elif state == 2:
            #更新止损点
            nearestPeak = max(zigzag.iat[row-1, 1], zigzag.iat[row-2, 1])
            if nearestPeak < stoppoint:
                print("更新止损点，旧止损点：{0}，新止损点：{1}".format(stoppoint,nearestPeak))
                stoppoint = nearestPeak
                
            if current > stoppoint:
                print("做空止损，出场点：{0}，止损点：{1}".format(current,stoppoint))
                return 3, 0 #空平
            else:
                #打印
                # print("继续做空，当前价格：{0}".format(current,stoppoint))
                return 4,stoppoint
            
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