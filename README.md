# Playwright-Grid

这个项目展示了一个基于WebSocket的通信系统，该系统使用FastAPI和Playwright实现中央hub和多个节点之间的通信。Hub管理连接、分发请求并处理响应，而节点执行网页抓取任务并将数据返回给hub。当前功能只涉及到采集列表页、详情页、搜索、截图、配置代理功能。

## 目录

- [安装](#安装)
- [使用](#使用)
- [Hub 详情](#hub-详情)
- [Node 详情](#node-详情)

## 安装

1. 克隆仓库：
    ```bash
    git clone https://github.com/xyuns-cn/Playwright-Grid.git
    cd Playwright-Grid
    ```

2. 安装所需依赖：
    ```bash
    pip install -r requirements.txt
    ```

3. 确保已安装并设置好 `Playwright`：
    ```bash
    playwright install
    ```

## 使用

### 运行 Hub

启动hub服务器，使用以下命令：
```bash
python hub.py
```

### 运行 Node

启动一个节点，运行以下命令：
```bash
python node_playwright.py --hub <hub_ip>:<hub_port>
```
如果 Hub 和 Node 在同一网段，则无需配置 Hub 地址，Node 会自动找到 Hub 并建立心跳连接。如果它们部署在不同网段，则需要将 `<hub_ip>` 和 `<hub_port>` 替换为 Hub 服务器的 IP 地址和端口。

## Hub 详情

Hub负责管理WebSocket连接并向连接的节点分发请求。它使用FastAPI处理WebSocket连接并提供HTTP端点用于发送请求。

### API 端点：

- **WebSocket 端点**: `/ws/{node_id}`
    - 与由 `node_id` 标识的节点建立WebSocket连接。

- **HTTP 端点**: `/request`
    - 接受包含JSON负载的POST请求，以向节点分发任务。

## Node 详情

节点负责使用Playwright执行网页抓取任务，并通过WebSocket与hub通信。

### 关键组件：

- **网页抓取**: 利用Playwright从网页中提取数据。
- **WebSocket 通信**: 连接到hub并处理传入的请求和传出的响应。

### 主要功能：

- **send_heartbeat**: 定期向hub发送心跳消息以维持连接。
- **handle_requests**: 监听来自hub的请求并执行所需的网页抓取任务。
- **get_page_info**: 根据提供的选择器和配置从网页中提取信息。

### 命令行参数：

- **--hub**: 指定要连接的hub地址。

