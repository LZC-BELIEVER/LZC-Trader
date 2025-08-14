import asyncio
import aiohttp
from aiohttp_sse_client import client as sse_client
import json
import requests

class SSEClient:
    def __init__(self, license_key=''):
        """
        初始化交易客户端
        :param base_url: API基础地址
        :param license_key: 许可证密钥
        """
        self.real_base_url = "https://www.quantum-hedge.com"
        self.virtual_base_url = "https://www.popper-fintech.com"

        self.license_key = license_key
        self.is_connected = False
        self.is_logged_in = False
        self.is_ready = False
        self.asy_session = None
        self.syn_session = requests.Session()
        self.syn_session.headers.update({
            'license': license_key
        })
        self.user_id = None
        self.fc_code = None
        self.password = None
        self.is_mkt_open = True
        self._loop = asyncio.get_event_loop()

        self.order_conditions = {}

    async def connect_sse(self):
        """
        连接SSE交易通道
        :param fc_code: 柜台代码
        :param user_id: 用户ID
        """
        if self.is_connected:
            print("SSE连接已存在，无需重复连接")
            return True

        url = f"https://www.quantum-hedge.com/apollo-trade/sse/tdConnect?fcCode=rh&userId=202500100"

        try:
            self.asy_session = aiohttp.ClientSession(
                headers={
                    'license': self.license_key  # 使用传入的 license_key
                }
            )
            self.event_source = await sse_client.EventSource(
                url,
                session=self.asy_session,
                headers={
                    'Content-Type': 'text/event-stream',
                    'Accept': 'text/event-stream',
                    'license': self.license_key  # 使用传入的 license_key
                }
                # timeout=10
            ).__aenter__()

            # 启动事件监听任务
            self.receive_task = asyncio.create_task(self._listen_events())
            return True

        except Exception as e:
            print(f"SSE连接失败: {e}")
            await self._cleanup()
            return False

    async def _listen_events(self):
        """监听服务器推送事件"""
        while True:
            try:
                print("listening")
                async for event in self.event_source:
                    print("event", event)

                    # 跳过连接确认/心跳等非业务事件
                    if event.type == 'sseTdConnected':
                        self.is_connected = True
                        print(f"SSE连接确认: {event.data}")
                        continue
                    if event.type == 'logged_in':
                        self.is_logged_in = True
                        print(f"登陆成功: {event.data}")
                    if event.type == "ready":
                        self.is_ready = True
                        print(f"结算单已确认，可以开始交易:{event.data}")
                    if event.type == "isMarketOpen":
                        self.is_mkt_open = False
                        print(f"现在{event.data}交易时间")
                    if event.type == "trade":
                        print("成交单回报:", event.data)
                        print("已成交单号", event.dara.originOrderId)

                    # 只处理业务事件
                    if event.type in ('logged_out', 'order', 'excption'):
                        try:
                            data = json.loads(event.data) if event.data else {}
                            print(f"收到业务事件: {event.type} - {data}")

                            if event.type == "logged_out":
                                self.is_logged_in = False
                                print("退出成功")
                            elif event.type == "order":
                                print("委托单回报:", data)

                        except json.JSONDecodeError:
                            print(f"非JSON格式的业务数据: {event.data}")
                        except Exception as e:
                            print(f"处理业务事件时出错: {e}")

            except Exception as e:
                print(f"事件监听错误: {e['characters_written']}")
                await self._cleanup()

    def get_data(self, symbol, candlenums, granularity):
        """
        期货下单（同步）
        """
        url = f"{self.real_base_url}/apollo-market/api/v1/futureData/queryData"

        data = {
            "symbol": symbol,
            "candleNums": candlenums,
            "period": granularity,
        }

        try:
            resp = self.syn_session.post(
                url,
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'license': self.license_key
                },
                timeout=10
            )

            result = resp.json()
            if result.get('code') == 0:
                return result.get('data')
            else:
                print(f"获取数据失败: {result.get('message')}")
                return None
        except Exception as e:
            print(f"获取数据请求出错: {e}")
            return None

    def get_data_according_time(self, symbol, granularity, start_time, end_time):
        """
        期货下单（同步）
        """
        url = f"{self.real_base_url}/apollo-market/api/v1/futureData/queryData"

        if start_time is not None and end_time is not None:
            start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time = end_time.strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "symbol": symbol,
                "period": granularity,
                "startTime": start_time,
                "endTime": end_time,
            }
        else:
            raise ValueError("Invalid start or end time")

        try:
            resp = self.syn_session.post(
                url,
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'license': self.license_key
                },
                timeout=10
            )

            result = resp.json()
            if result.get('code') == 0:
                # print("成功")
                return result.get('data')
            else:
                print(f"获取数据失败: {result.get('message')}")
                return None
        except Exception as e:
            print(f"获取数据请求出错: {e}")
            return None

    async def disconnect(self):
        """断开SSE连接"""
        if not self.is_connected:
            print("SSE连接不存在，无需断开")
            return True

        await self._cleanup()
        print("SSE连接已断开")
        return True

    async def _cleanup(self):
        """清理资源"""
        try:
            print("开始清理资源")
            if hasattr(self, 'receive_task'):
                self.receive_task.cancel()
                try:
                    await self.receive_task
                except asyncio.CancelledError:
                    pass

            if hasattr(self, 'event_source'):
                await self.event_source.__aexit__(None, None, None)

            if self.asy_session:
                await self.asy_session.close()

        except Exception as e:
            print(f"清理资源时出错: {e}")

        finally:
            self.is_connected = False
            self.is_ready = False
            self.asy_session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()