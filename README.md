# LZCTrader User Manual

## Introduction
- LZCTrader is a trading and backtesting client system designed for quantitative strategy researchers. The system can fetch futures market data and execute automated trading based on custom strategies.
- The system architecture is based on [AutoTrader](https://github.com/kieran-mackle/AutoTrader). Currently, it only supports multi-futures trading in the Chinese mainland market.
- Author: LZC from XJTU
- This is the client-side system; the server-side is supported by Popper Technology (Xi’an).

## File Structure
- **API**: Broker interface module
- **brokers**: Broker definition module
- **LZCTrader**: Main system module
- **preliminary**: Preliminary strategy module
- **preliminary_config**: Preliminary strategy configuration module
- **strategies**: Trading strategy module
- **strategies_config**: Trading strategy configuration module
- **run.py**: Script for single execution of the system
- **day_and_night.py**: Script for scheduled daily trading

## Trading Deployment
1. Install PyCharm and prepare a Python environment version 3.12 or above.
2. Install all required libraries using pip in the environment.
3. Follow the example in the **strategies** folder (example.py) to write your own strategy file. Similarly, follow the **strategies_config** folder (example.yaml) to complete your strategy configuration file. **Note:** The filenames of the strategy and configuration files must match exactly and should preferably be in lowercase.
4. In **run.py**, configure `configue`, `set_preliminary_select`, and `set_strategy` according to the comments. Then, in **day_and_night.py**, adjust the running path in the `run_strategy()` function as indicated in the comments.
5. Run **day_and_night.py**.
6. Supported trading instruments are listed in **LZCTrader/tools/instrument_map.yaml**.
7. When the server sends the message `'ready'`, it indicates the system is running normally. There is no additional interface; successful orders will display an order number.

## Backtesting Deployment
1. Install PyCharm and prepare a Python environment version 3.12 or above.
2. Install all required libraries using pip in the environment.
3. Follow the **backtest_strategies** folder (bdwz.py) to write your own backtesting strategy file. Similarly, follow the **strategies_config** folder (bdwz.yaml) to complete the configuration file. **Note:** Filenames must match exactly and preferably be lowercase.
4. In **run_backtest.py**, configure `configue` and `set_strategy` according to the comments.
5. Run **run_backtest.py**.
6. Supported trading instruments are listed in **LZCTrader/tools/instrument_map.yaml**.

---

# LZCTrader 使用文档

## 简介
- LZCTrader是面向量化策略研究人员所使用的交易及回测客户端系统，系统可以实现获取期货行情数据并根据自定义策略实现自动化交易。
- 系统参考[AutoTrader](https://github.com/kieran-mackle/AutoTrader)架构实现。现在只支持中国大陆期货市场多期货品种交易。
- Author: LZC from XJTU 
- 系统为客户端部分，服务器端由波普尔技术（西安）提供支持。

## 文件结构
- **API**:券商接口模块
- **brokers**:券商定义模块
- **LZCTrader**：系统主模块
- **preliminary**:初筛策略模块
- **preliminary_config**:初筛策略配置模块
- **strategies**:交易策略模块
- **strategies_config**:交易策略配置模块
- **run.py**:系统单次运行文件
- **day_and_night.py**:系统交易日定时运行文件

## 交易部署方法
1. 下载PyCharm，并最好准备一个3.12以上的Python环境
2. 在环境中下载(pip)系统运行所需的所有库文件
3. 仿照strategies文件夹下的example.py，写一个属于你自己的策略文件。并仿照strategies_config文件夹下的example.yaml，完成策略的配置文件。注意！策略文件和配置文件的文件名必须完全一致，最好为全部小写。
4. 在run.py中，配置configue，set_preliminary_select以及set_strategy，配置方法见注释。接着，在day_and_night.py中run_strategy()函数中按照注释修改运行路径。 
5. 运行day_and_night.py
6. 支持的交易品种见LZCTrader/tools/instrument_map.yaml
7. 当收到服务器端 message='ready' 信息时，表示系统已经开始正常运行。系统无额外运行界面，下单成功时，会显示单号。

## 回测部署方法
1. 下载PyCharm，并最好准备一个3.12以上的Python环境
2. 在环境中下载(pip)系统运行所需的所有库文件
3. 仿照backtest_strategies文件夹下的bdwz.py，写一个属于你自己的策略文件。并仿照strategies_config文件夹下的bdwz.yaml，完成策略的配置文件。注意！策略文件和配置文件的文件名必须完全一致，最好为全部小写。
4. 在run_backtest.py中，配置configue以及set_strategy，配置方法见注释。
5. 运行run_backtest.py
6. 支持的交易品种见LZCTrader/tools/instrument_map.yaml


