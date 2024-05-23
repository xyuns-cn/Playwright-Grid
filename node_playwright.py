#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time : 2024/5/21 11:40
# @Author : xinnn
# @File : node_playwright.py
# @Describe:
import asyncio
import base64
import websockets
import json
import socket
import uuid
import argparse

from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

BROADCAST_PORT = 37020
hub_address = None
node_id = str(uuid.uuid4())
heartbeat_interval = 3


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


async def listen_for_hub():
    global hub_address
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", BROADCAST_PORT))
        while True:
            message, _ = s.recvfrom(1024)
            hub_info = message.decode('utf-8').split(':')
            if hub_info[0] == 'hub':
                hub_address = (hub_info[1], int(hub_info[2]))
                print(f"发现hub地址: {hub_address}")
                break


async def send_heartbeat(websocket, browser_type):
    while True:
        heartbeat_data = {
            "node_id": node_id,
            "ip": socket.gethostbyname(socket.gethostname()),
            "browser": browser_type,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send(json.dumps({"type": "heartbeat", "data": heartbeat_data}))
        await asyncio.sleep(heartbeat_interval)


async def wait_for_network_idle(page, timeout):
    try:
        await asyncio.wait_for(page.wait_for_load_state('networkidle'), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"在 {timeout} 秒内未达到网络空闲状态，继续执行...")


def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.2f} MB"
    return f"{size / 1024 ** 3:.2f} GB"


async def capture_screenshot(page):
    screenshot = await page.screenshot()
    screenshot_size = len(screenshot)
    formatted_size = format_size(screenshot_size)
    screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
    return {
        "size": formatted_size,
        "base64": screenshot_base64
    }


async def get_items_content(page, item_selector, title_selector=None, date_selector=None):
    await page.wait_for_selector(item_selector, timeout=10000)
    items = await page.query_selector_all(item_selector)
    items_content = []
    for item in items:
        item_content = {}

        if title_selector:
            title_element = await item.query_selector(title_selector)
            if title_element:
                item_content['title'] = (await title_element.text_content()).replace("\n", " ").strip()
            else:
                item_content['title'] = "无标题"

        link_elements = await item.query_selector_all("a")
        if link_elements:
            item_content['links'] = [await link.get_attribute("href") for link in link_elements]
        else:
            item_content['links'] = ["无链接"]

        if date_selector:
            date_element = await item.query_selector(date_selector)
            if date_element:
                item_content['date'] = (await date_element.text_content()).replace("\n", " ").strip()
            else:
                item_content['date'] = "无日期"

        items_content.append(item_content)
    return items_content


async def get_content_by_selectors(page, selectors):
    results = []
    for selector in selectors:
        try:
            await page.wait_for_selector(selector, timeout=5000)
            element = await page.query_selector(selector)
            if element:
                content = (await element.text_content()).replace("\n", " ").strip()
                results.append({"selector": selector, "content": content})
        except PlaywrightTimeoutError:
            results.append({"selector": selector, "content": None})
    return results


async def get_body_content(page, body_selectors, title_selectors, date_selectors):
    body_content = await get_content_by_selectors(page, body_selectors) if body_selectors else [
        {"selector": None, "content": "无正文内容"}]
    title_content = await get_content_by_selectors(page, title_selectors) if title_selectors else [
        {"selector": None, "content": "无标题"}]
    date_content = await get_content_by_selectors(page, date_selectors) if date_selectors else [
        {"selector": None, "content": "无日期"}]

    return {
        "title": title_content,
        "body": body_content,
        "date": date_content
    }


async def get_page_info(request_data: RequestBody):
    page_info = {}
    async with async_playwright() as p:
        browser_type = getattr(p, request_data.browser, None)
        if not browser_type:
            raise HTTPException(status_code=400, detail="无效的浏览器类型")

        # Configure proxy if provided
        proxy = None
        if request_data.proxy:
            proxy = {
                "server": request_data.proxy.server
            }
            if request_data.proxy.username and request_data.proxy.password:
                proxy["username"] = request_data.proxy.username
                proxy["password"] = request_data.proxy.password

        browser = await browser_type.launch(headless=False, proxy=proxy)
        page = await browser.new_page()

        await page.goto(request_data.url)

        if request_data.search_in.search:
            try:
                await page.fill(request_data.search_in.search_input_selector, request_data.search_in.search_term)
                await page.click(request_data.search_in.search_button_selector)
            except Exception as e:
                print(f"搜索操作失败: {e}")

        await wait_for_network_idle(page, timeout=10)

        if request_data.items_config.enabled and request_data.body_config.enabled:
            raise HTTPException(status_code=400, detail="列表页和详情页配置只能启用一个")

        if request_data.items_config.enabled:
            try:
                page_info["items"] = await get_items_content(
                    page,
                    request_data.items_config.item_selector,
                    request_data.items_config.title_selector,
                    request_data.items_config.date_selector)
            except PlaywrightTimeoutError:
                page_info["items"] = []

        if request_data.body_config.enabled:
            page_info["body"] = await get_body_content(
                page,
                request_data.body_config.body_selectors,
                request_data.body_config.title_selectors,
                request_data.body_config.date_selectors)

        if request_data.screenshot:
            page_info["screenshot"] = await capture_screenshot(page)

        await browser.close()
    return page_info


async def handle_requests(websocket):
    async for message in websocket:
        try:
            data = json.loads(message)
            if data.get("type") == "request":
                request_data = RequestBody(**data["data"])
                page_info = await get_page_info(request_data)
                response = {"type": "response", "data": page_info}
                await websocket.send(json.dumps(response))
            else:
                print(f"Unknown message type: {data.get('type')}")
        except Exception as e:
            error_message = {"type": "error", "data": str(e)}
            await websocket.send(json.dumps(error_message))


async def main():
    global hub_address
    hub_address = parse_arguments()  # 解析命令行输入的hub地址
    if not hub_address:
        print("没有指定hub地址，监听广播以获取地址")
        await listen_for_hub()
    else:
        print(f"使用指定的hub地址: {hub_address}")

    uri = f"ws://{hub_address[0]}:{hub_address[1]}/ws/{node_id}"
    async with websockets.connect(uri) as websocket:
        try:
            await asyncio.gather(
                send_heartbeat(websocket, "chromium"),  # 默认使用chromium浏览器
                handle_requests(websocket)
            )
        except KeyboardInterrupt:
            print("程序被用户中断")
        finally:
            print("关闭浏览器和网络连接等资源")
            await websocket.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("主程序被用户中断")
