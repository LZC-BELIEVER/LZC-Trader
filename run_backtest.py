from LZCTrader.lzctrader import LZCTrader

zc = LZCTrader()
zc.configure(broker_name='backtest',  # 期货券商接口，目前仅'future'一个选项
             mode='backtest',  # 模式选择，虚拟为'virtualtrading'，实盘为'realtrading'
             enter_license='s3az29vbx5w3',  # 登录通行证。暂设为此值即可
             backtest_start_time='7/7/2025',
             backtest_end_time='14/7/2025',
             backtest_min_granularity= '5s',
             backtest_start_balance=10000
             )
zc.set_backtest_strategy('bdwz')  # 此处引入策略。注意：必须和交易策略py文件的命名严格一致
zc.backtest()

# 此为系统主运行文件。以上的所有函数，均为必需。
