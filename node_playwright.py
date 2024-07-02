#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time : 2024/5/21 11:40
# @Author : xinnn
# @File : node_playwright.py
# @Describe:
import asyncio
import base64
import json
import socket
import uuid
import argparse
import sys
from typing import List, Optional
from datetime import datetime

import websockets
from loguru import logger
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fake_useragent import UserAgent

# 配置
BROADCAST_PORT = 37020
HEARTBEAT_INTERVAL = 3
NODE_ID = str(uuid.uuid4())

# 日志配置
logger.remove()
logger.add(sys.stdout, level="INFO")
logger.add("node_playwright.log", rotation="100 MB", retention="10 days", level="INFO")


class ProxyConfig(BaseModel):
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


class SearchIn(BaseModel):
    search: bool = False
    search_input_selector: Optional[str] = Field(default=None, description="搜索输入框的选择器")
    search_button_selector: Optional[str] = Field(default=None, description="搜索按钮的选择器")
    search_term: Optional[str] = Field(default=None, description="搜索关键词")


class ItemsConfig(BaseModel):
    enabled: bool = False
    item_selector: Optional[str] = Field(default=None, description="项目的选择器")
    title_selector: Optional[str] = Field(default=None, description="项目标题的选择器")
    date_selector: Optional[str] = Field(default=None, description="项目日期的选择器")


class BodyConfig(BaseModel):
    enabled: bool = False
    body_selectors: List[str] = Field(default_factory=list, description="正文内容的选择器列表")
    title_selectors: List[str] = Field(default_factory=list, description="标题内容的选择器列表")
    date_selectors: List[str] = Field(default_factory=list, description="日期内容的选择器列表")


class RequestBody(BaseModel):
    url: str
    browser: str = Field(default="chromium", description="要使用的浏览器类型: 'chromium', 'firefox', 或 'webkit'")
    proxy: Optional[ProxyConfig] = None
    screenshot: bool = False
    search_in: SearchIn = SearchIn()
    items_config: ItemsConfig = ItemsConfig()
    body_config: BodyConfig = BodyConfig()


class PlaywrightNode:
    def __init__(self):
        self.hub_address = None
        self.node_state = "idle"
        self.request_queue = asyncio.Queue()

    async def listen_for_hub(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.bind(("", BROADCAST_PORT))
            while True:
                message, _ = s.recvfrom(1024)
                hub_info = message.decode('utf-8').split(':')
                if hub_info[0] == 'hub':
                    self.hub_address = (hub_info[1], int(hub_info[2]))
                    logger.info(f"发现hub地址: {self.hub_address}")
                    break

    async def send_heartbeat(self, websocket, browser_type: str):
        while True:
            try:
                heartbeat_data = {
                    "node_id": NODE_ID,
                    "ip": socket.gethostbyname(socket.gethostname()),
                    "browser": browser_type,
                    "method": "Playwright",
                    "timestamp": datetime.now().isoformat(),
                    "state": self.node_state
                }
                await websocket.send(json.dumps({"type": "heartbeat", "data": heartbeat_data}))
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"发送心跳失败: {e}")
                await asyncio.sleep(5)

    async def handle_websocket(self):
        uri = f"ws://{self.hub_address[0]}:{self.hub_address[1]}/ws/{NODE_ID}"
        async with websockets.connect(uri) as websocket:
            heartbeat_task = asyncio.create_task(self.send_heartbeat(websocket, "chromium"))
            try:
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if data.get("type") == "request":
                        await self.request_queue.put(data["data"])
                    elif data.get("type") == "heartbeat_ack":
                        logger.debug("Received heartbeat acknowledgement")
            except websockets.exceptions.ConnectionClosed:
                logger.info("WebSocket connection closed")
            finally:
                heartbeat_task.cancel()

    async def process_requests(self):
        while True:
            request_data = await self.request_queue.get()
            try:
                page_info = await self.get_page_info(RequestBody(**request_data))
                response = {"type": "response", "data": page_info}
                uri = f"ws://{self.hub_address[0]}:{self.hub_address[1]}/ws/{NODE_ID}"
                async with websockets.connect(uri) as websocket:
                    await websocket.send(json.dumps(response))
            except Exception as e:
                logger.error(f"处理请求时发生错误: {e}")
            finally:
                self.request_queue.task_done()

    async def get_page_info(self, request_data: RequestBody):
        async with async_playwright() as p:
            browser_type = getattr(p, request_data.browser)
            browser = await browser_type.launch(headless=True)
            context = await browser.new_context(
                user_agent=UserAgent().random,
                proxy=request_data.proxy.dict() if request_data.proxy else None
            )
            page = await context.new_page()

            try:
                await page.goto(request_data.url, wait_until="networkidle")

                # 执行搜索
                if request_data.search_in.search:
                    await page.fill(request_data.search_in.search_input_selector, request_data.search_in.search_term)
                    await page.click(request_data.search_in.search_button_selector)
                    await page.wait_for_load_state("networkidle")

                # 获取项目列表
                items = []
                if request_data.items_config.enabled:
                    elements = await page.query_selector_all(request_data.items_config.item_selector)
                    for element in elements:
                        title = await element.query_selector(request_data.items_config.title_selector)
                        date = await element.query_selector(request_data.items_config.date_selector)
                        items.append({
                            "title": await title.inner_text() if title else None,
                            "date": await date.inner_text() if date else None
                        })

                # 获取正文内容
                body_content = {}
                if request_data.body_config.enabled:
                    for selector in request_data.body_config.body_selectors:
                        element = await page.query_selector(selector)
                        if element:
                            body_content[selector] = await element.inner_text()

                    for selector in request_data.body_config.title_selectors:
                        element = await page.query_selector(selector)
                        if element:
                            body_content[f"title_{selector}"] = await element.inner_text()

                    for selector in request_data.body_config.date_selectors:
                        element = await page.query_selector(selector)
                        if element:
                            body_content[f"date_{selector}"] = await element.inner_text()

                # 截图
                screenshot = None
                if request_data.screenshot:
                    screenshot = await page.screenshot(full_page=True)
                    screenshot = base64.b64encode(screenshot).decode('utf-8')

                return {
                    "url": page.url,
                    "items": items,
                    "body_content": body_content,
                    "screenshot": screenshot
                }

            except PlaywrightTimeoutError:
                logger.error(f"访问 {request_data.url} 超时")
                return {"error": "Timeout"}
            except Exception as e:
                logger.error(f"处理 {request_data.url} 时发生错误: {e}")
                return {"error": str(e)}
            finally:
                await browser.close()

    async def run(self):
        if not self.hub_address:
            logger.info("没有指定hub地址，监听广播以获取地址")
            await self.listen_for_hub()
        else:
            logger.info(f"使用指定的hub地址: {self.hub_address}")

        tasks = [
            asyncio.create_task(self.handle_websocket()),
            asyncio.create_task(self.process_requests())
        ]
        await asyncio.gather(*tasks)


def parse_arguments():
    parser = argparse.ArgumentParser(description="启动参数")
    parser.add_argument('--hub', type=str, help='指定hub地址，格式为 host:port')
    args = parser.parse_args()
    if args.hub:
        try:
            host, port = args.hub.split(':')
            return host, int(port)
        except ValueError:
            raise ValueError("Hub 地址格式应该为 host:port")
    return None


if __name__ == "__main__":
    node = PlaywrightNode()
    node.hub_address = parse_arguments()
    try:
        asyncio.run(node.run())
    except KeyboardInterrupt:
        logger.info("主程序被用户中断")
