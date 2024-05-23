# Playwright-Grid

这个项目展示了一个基于WebSocket的通信系统，该系统使用FastAPI和Playwright实现中央hub和多个节点之间的通信。Hub管理连接、分发请求并处理响应，而节点执行网页抓取任务并将数据返回给hub。当前功能只涉及到采集列表页、详情页、搜索、截图、配置代理功能。

## 主要功能

- **网页抓取**: 根据选择器抓取网页内容，包括标题、正文、日期等。
- **搜索操作**: 模拟网页中的搜索操作，自动填充搜索关键词并点击搜索按钮。
- **截图功能**: 对指定网页进行截图，并返回Base64编码的截图数据。
- **代理配置**: 配置代理即可使用代理访问网站。

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

根据节点和Hub的网络部署情况，选择合适的方法来启动节点并发现Hub地址：
- 如果知道Hub的具体地址和端口，使用命令行参数方法。
- 如果在同一网段并希望自动发现Hub地址，使用UDP广播方法。

#### 方法一：命令行参数

1. **描述**：
   节点在启动脚本时可以通过命令行参数接收Hub地址。地址格式为 `host:port`。

2. **为什么使用这种方法**：
   这种方法适用于在启动节点时已经知道Hub地址或Hub与Node不在同一网段内的情况，可以通过命令行直接传递，简单且直接。

3. **运行命令**：
   启动一个节点，运行以下命令：
   ```bash
   python node_playwright.py --hub <hub_ip>:<hub_port>
   ```
   将 `<hub_ip>` 和 `<hub_port>` 替换为Hub服务器的IP地址和端口。

#### 方法二：UDP广播

1. **描述**：
   节点在运行是没有指定Hub地址时使用特定端口监听UDP广播消息以发现Hub地址。这种方法在启动时无法预先知道Hub地址并需要在运行时动态发现时特别有用。

2. **为什么使用这种方法**：
   这种方法适用于节点和Hub在同一网段的情况，可以通过广播机制自动发现Hub地址，无需手动配置，方便动态环境下的节点发现。

3. **运行命令**：
   启动一个节点，运行以下命令：
   ```bash
   python node_playwright.py
   ```
   在这种情况下，不需要额外的参数配置。节点会自动监听预定义的广播端口并接收包含Hub地址的消息。

### 示例请求

发送POST请求到`/capture`，完整请求体示例如下：
```json
{
  "url": "https://example.com",                 // 必填项：需要访问的网页地址
  "browser": "chromium",                        // 可选项：使用的浏览器类型，可以是'chromium', 'firefox', 或 'webkit'，不填默认为'chromium'
  "screenshot": true,                           // 可选项：是否对页面进行截图
  "proxy": {                                    // 可选项：代理服务器配置
    "server": "http://<proxy_ip>:<proxy_port>/",  // 代理服务器URL
    "username": "<username>",                     // 代理用户名，如没有用户名可不填
    "password": "<password>"                      // 代理密码，如没有密码可不填
  },
  "search_in": {                                // 可选项：站内搜索配置
    "search": true,                               // 启用搜索功能
    "search_input_selector": "#search",           // 搜索输入框的选择器，可以是CSS选择器或XPath
    "search_button_selector": "#search-btn",      // 搜索按钮的选择器，可以是CSS选择器或XPath
    "search_term": "example search"               // 搜索词
  },
  "items_config": {                             // 可选项：列表页抓取配置
    "enabled": true,                              // 是否启用列表页抓取
    "item_selector": ".item",                     // 每个列表的选择器，可以是CSS选择器或XPath
    "title_selector": ".title",                   // 项目标题的选择器，可以是CSS选择器或XPath
    "date_selector": ".date"                      // 项目日期的选择器，可以是CSS选择器或XPath
  },
  "body_config": {                              // 可选项：正文抓取配置
    "enabled": false,                             // 是否启用正文抓取
    "body_selectors": ["#content"],               // 正文内容的选择器，可以配置多个，可以是CSS选择器或XPath
    "title_selectors": ["h1"],                    // 正文标题的选择器，可以配置多个，可以是CSS选择器或XPath
    "date_selectors": [".date"]                   // 正文日期的选择器，可以配置多个，可以是CSS选择器或XPath
  }
}

```
注：列表页和详情页不可同时采集。

