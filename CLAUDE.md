# A股模拟交易系统 - 项目文档

## 版本信息
- **版本号**：v1.0.1
- **发布日期**：2026-04-23
- **状态**：正式发布

## 项目概述
- **项目路径**：`D:\WorkSpace\Virtual Trading System`
- **技术栈**：FastAPI + Vue3 + ECharts + SQLAlchemy
- **环境**：Windows + Python虚拟环境

## 项目结构
```
├── venv/                    # Python虚拟环境
├── app.py                   # FastAPI主应用
├── database.py              # 数据库模块
├── crawler.py               # 异步爬虫模块
├── requirements.txt         # 依赖清单
├── .env                     # 环境变量
├── README.md                # 项目说明
├── CLAUDE.md                # 开发文档
├── trading_system.db        # SQLite数据库
├── templates/
│   └── index.html           # 前端主页面
└── static/
    ├── css/
    │   └── style.css        # 深色主题样式
    └── js/
        └── app.js           # Vue3前端逻辑
```

## 已完成 ✅

| 文件 | 状态 | 说明 |
|------|------|------|
| `requirements.txt` | ✅ | 依赖清单：FastAPI, Uvicorn, SQLAlchemy, aiohttp, BeautifulSoup4, pandas, APScheduler |
| `.env` | ✅ | 环境变量文件 |
| `database.py` | ✅ | 数据库模块：6张表 |
| `crawler.py` | ✅ | 异步爬虫模块（新浪财经API） |
| `app.py` | ✅ | FastAPI主应用 |
| `templates/index.html` | ✅ | 前端主页面（三栏布局） |
| `static/css/style.css` | ✅ | 深色主题专业样式 |
| `static/js/app.js` | ✅ | Vue3 + Axios + ECharts |
| `README.md` | ✅ | 项目说明文档 |

## 数据库表结构

1. **system_account** - 系统单一账号（资金、总资产）
2. **stock_info** - 股票基础信息
3. **stock_rt** - 实时行情（含五档盘口）
4. **kline_data** - K线数据
5. **orders** - 交易订单
6. **positions** - 持仓

## 后端API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/account` | GET | 账号信息 |
| `/api/positions` | GET | 持仓列表 |
| `/api/orders` | GET | 历史交易记录 |
| `/api/order` | POST | 创建订单（买入/卖出） |
| `/api/stock/list` | GET | 股票列表 |
| `/api/stock/search` | GET | 股票搜索 |
| `/api/stock/realtime` | GET | 实时行情 |
| `/api/stock/kline` | GET | K线数据（日/周/月） |
| `/api/stock/timeline` | GET | 分时数据（实时到当前时间） |
| `/api/sectors` | GET | 板块分类 |
| `/api/market/overview` | GET | 市场概况 |
| `/api/watchlist` | GET/POST/DELETE | 自选股管理 |

## 交易规则
- T+1交易制度（当日买入次日才能卖出）
- 100股整数倍交易
- 可用资金判断
- 涨跌停限制
- 市价成交

## K线图时间范围
- **日K**：约3个月（65条数据）
- **周K**：约1年3个月（65条数据）
- **月K**：约5年3个月（63条数据）

## 用户界面功能

### 左侧栏
- **自选股**：用户添加的自选股票列表
- **全市场**：常用股票快速浏览
- **板块**：行业板块分类

### 中间栏
- **分时图**：实时更新到当前时间
- **K线图**：日K（真实数据）、周K/月K（聚合日K生成）
- **滑动条**：支持缩放和拖动查看历史

### 右侧栏
- **个股信息**：开盘、收盘、最高、最低、成交量等
- **五档盘口**：买卖各五档价格和数量
- **我的持仓**：显示所有持仓股票，点击快速切换

## 数据刷新机制
- **刷新间隔**：5秒
- **刷新内容**：账户资金、持仓盈亏、自选股行情、全市场行情、当前股票图表

## 启动命令
```bash
cd "d:/WorkSpace/Virtual Trading System"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
访问: http://localhost:5000

## 快捷操作
- `-100` / `+100`：调整交易数量
- `1手` / `5手` / `10手`：快速设置（100/500/1000股）
- `全仓`：最大可交易数量

## 版本更新记录

### v1.0.1 (2026-04-23)
- 修复新浪API数据顺序问题（升序→倒序→升序正确处理）
- 修复周K/月K聚合逻辑，确保正确从日K聚合生成
- 修复K线图时间范围

### v1.0.0 (2026-04-23)
- 初始版本正式发布
- 完整的行情、交易、持仓功能
- 修复交易逻辑资金计算问题
- 修复T+1限制绕过问题
- 修复分时图只到13:29的问题
- 修复K线图数据源问题
- 添加K线图滑动条
- 右侧栏添加"我的持仓"模块
