"""
Virtual Trading System - Main Application
FastAPI backend with complete trading functionality
"""
import os
import sys
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

# 导入本地模块
from database import (
    engine, SessionLocal, init_db, init_default_account,
    SystemAccount, StockInfo, StockRealtime, KlineData, Order, Position, WatchList
)
from crawler import crawler, initialize_data

# 创建FastAPI应用
app = FastAPI(title="A股模拟交易系统", version="1.0.0")

# 配置模板和静态文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ==================== Pydantic模型 ====================
class OrderRequest(BaseModel):
    """下单请求模型"""
    stock_code: str
    direction: str  # buy/sell
    price: Optional[float] = 0  # 市价下单时为0
    volume: int  # 股数，必须是100的整数倍


class PositionUpdate(BaseModel):
    """持仓更新模型"""
    stock_code: str
    stock_name: str
    volume: int
    available_volume: int
    cost_price: float


# ==================== 辅助函数 ====================
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def update_account_after_trade(db, direction: str, amount: float):
    """交易后更新账户"""
    account = db.query(SystemAccount).filter(SystemAccount.id == 1).first()
    if not account:
        return

    if direction == "buy":
        account.available_capital -= amount
    else:  # sell
        account.available_capital += amount

    # 重新计算总资产和市值
    positions = db.query(Position).all()
    market_value = sum(p.market_value for p in positions)
    account.market_value = market_value
    account.total_capital = account.available_capital + market_value

    db.commit()


def update_positions_after_trade(db, stock_code: str, direction: str, volume: int, price: float):
    """交易后更新持仓"""
    position = db.query(Position).filter(Position.stock_code == stock_code).first()

    if direction == "buy":
        if position:
            # 已有持仓，计算新的成本价
            total_cost = position.cost_price * position.volume + price * volume
            new_volume = position.volume + volume
            position.cost_price = round(total_cost / new_volume, 2)
            position.volume = new_volume
            # available_volume 保持不变，新增股份也受T+1限制
        else:
            # 新建持仓
            position = Position(
                stock_code=stock_code,
                stock_name=get_stock_name(db, stock_code),
                volume=volume,
                available_volume=0,  # T+1
                cost_price=price
            )
            db.add(position)
    else:  # sell
        if position:
            position.volume -= volume
            position.available_volume = 0  # T+1

    db.commit()


def get_stock_name(db, stock_code: str) -> str:
    """获取股票名称"""
    info = db.query(StockInfo).filter(StockInfo.stock_code == stock_code).first()
    if info:
        return info.stock_name

    rt = db.query(StockRealtime).filter(StockRealtime.stock_code == stock_code).first()
    if rt:
        return rt.stock_name

    return stock_code


def calculate_position_profit(db):
    """计算所有持仓的盈亏"""
    positions = db.query(Position).all()

    for pos in positions:
        rt = db.query(StockRealtime).filter(StockRealtime.stock_code == pos.stock_code).first()
        if rt and rt.current_price > 0:
            pos.current_price = rt.current_price
            pos.market_value = pos.volume * pos.current_price
            pos.profit_loss = round((pos.current_price - pos.cost_price) * pos.volume, 2)
            pos.profit_ratio = round((pos.current_price - pos.cost_price) / pos.cost_price * 100, 2) if pos.cost_price > 0 else 0

    db.commit()


def check_t1_restriction(db, stock_code: str, volume: int, direction: str) -> bool:
    """检查T+1限制"""
    if direction == "sell":
        # 检查今日是否有买入
        today = datetime.now().strftime('%Y-%m-%d')
        today_orders = db.query(Order).filter(
            Order.stock_code == stock_code,
            Order.direction == "buy",
            Order.status == "completed"
        ).all()

        for order in today_orders:
            if order.order_time.strftime('%Y-%m-%d') == today:
                # 今天买过，检查可用数量
                position = db.query(Position).filter(Position.stock_code == stock_code).first()
                if position and position.available_volume < volume:
                    return False
                return True

        # 没有今日买入，检查持仓是否够卖
        position = db.query(Position).filter(Position.stock_code == stock_code).first()
        if not position or position.volume < volume:
            return False

    return True


# ==================== API路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页"""
    with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/account")
async def get_account():
    """获取账号信息"""
    db = get_db()
    try:
        account = db.query(SystemAccount).filter(SystemAccount.id == 1).first()
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")

        # 计算市值
        calculate_position_profit(db)
        positions = db.query(Position).all()
        market_value = sum(p.market_value for p in positions)
        total_profit = sum(p.profit_loss for p in positions)

        return {
            "account_name": account.account_name,
            "total_capital": round(account.available_capital + market_value, 2),
            "available_capital": round(account.available_capital, 2),
            "market_value": round(market_value, 2),
            "total_profit": round(total_profit, 2),
            "frozen_capital": round(account.frozen_capital, 2)
        }
    finally:
        db.close()


@app.get("/api/positions")
async def get_positions():
    """获取持仓列表"""
    db = get_db()
    try:
        calculate_position_profit(db)
        positions = db.query(Position).all()

        return [{
            "stock_code": p.stock_code,
            "stock_name": p.stock_name,
            "volume": p.volume,
            "available_volume": p.available_volume,
            "cost_price": p.cost_price,
            "current_price": p.current_price,
            "market_value": round(p.market_value, 2),
            "profit_loss": round(p.profit_loss, 2),
            "profit_ratio": round(p.profit_ratio, 2)
        } for p in positions]
    finally:
        db.close()


@app.get("/api/orders")
async def get_orders(limit: int = 50):
    """获取历史交易记录"""
    db = get_db()
    try:
        orders = db.query(Order).order_by(Order.order_time.desc()).limit(limit).all()

        return [{
            "order_id": o.order_id,
            "stock_code": o.stock_code,
            "stock_name": o.stock_name,
            "direction": o.direction,
            "order_type": o.order_type,
            "price": o.price,
            "volume": o.volume,
            "amount": round(o.amount, 2),
            "status": o.status,
            "order_time": o.order_time.strftime('%Y-%m-%d %H:%M:%S'),
            "deal_time": o.deal_time.strftime('%Y-%m-%d %H:%M:%S') if o.deal_time else ""
        } for o in orders]
    finally:
        db.close()


@app.post("/api/order")
async def create_order(order_req: OrderRequest):
    """创建订单（买入/卖出）"""
    db = get_db()
    try:
        # 获取股票实时行情
        rt = db.query(StockRealtime).filter(StockRealtime.stock_code == order_req.stock_code).first()
        if not rt:
            raise HTTPException(status_code=404, detail="股票不存在或未找到行情数据")

        current_price = rt.current_price
        if current_price <= 0:
            raise HTTPException(status_code=400, detail="股票停牌，无法交易")

        # 检查涨跌停限制
        if order_req.direction == "buy" and current_price >= rt.limit_up_price:
            raise HTTPException(status_code=400, detail="股票涨停，无法买入")
        if order_req.direction == "sell" and current_price <= rt.limit_down_price:
            raise HTTPException(status_code=400, detail="股票跌停，无法卖出")

        # 市价成交
        deal_price = current_price
        total_amount = deal_price * order_req.volume

        # 买入检查
        if order_req.direction == "buy":
            account = db.query(SystemAccount).filter(SystemAccount.id == 1).first()
            if account.available_capital < total_amount:
                raise HTTPException(status_code=400, detail="可用资金不足")

        # 卖出检查
        if order_req.direction == "sell":
            position = db.query(Position).filter(Position.stock_code == order_req.stock_code).first()
            if not position or position.volume < order_req.volume:
                raise HTTPException(status_code=400, detail="持仓数量不足")

            # 检查T+1限制
            if not check_t1_restriction(db, order_req.stock_code, order_req.volume, "sell"):
                raise HTTPException(status_code=400, detail="T+1限制：今日买入的股票不能卖出")

        # 创建订单
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

        order = Order(
            order_id=order_id,
            stock_code=order_req.stock_code,
            stock_name=rt.stock_name,
            direction=order_req.direction,
            order_type="market",
            price=deal_price,
            volume=order_req.volume,
            amount=total_amount,
            status="completed",
            deal_time=datetime.now()
        )
        db.add(order)

        # 先计算持仓盈亏更新market_value
        calculate_position_profit(db)

        # 更新持仓
        update_positions_after_trade(db, order_req.stock_code, order_req.direction, order_req.volume, deal_price)

        # 重新计算持仓盈亏（确保市值准确）
        calculate_position_profit(db)

        # 更新账户（必须在持仓更新之后，获取正确的市值）
        update_account_after_trade(db, order_req.direction, total_amount)

        positions = db.query(Position).all()
        account = db.query(SystemAccount).filter(SystemAccount.id == 1).first()
        market_value = sum(p.market_value for p in positions)
        account.market_value = market_value
        account.total_capital = account.available_capital + market_value

        db.commit()

        return {
            "success": True,
            "order_id": order_id,
            "message": f"{'买入' if order_req.direction == 'buy' else '卖出'}成功",
            "stock_code": order_req.stock_code,
            "stock_name": rt.stock_name,
            "direction": order_req.direction,
            "price": deal_price,
            "volume": order_req.volume,
            "amount": round(total_amount, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/api/stock/list")
async def get_stock_list(page: int = 1, page_size: int = 100):
    """获取股票列表（全市场）"""
    db = get_db()
    try:
        stocks = db.query(StockInfo).offset((page - 1) * page_size).limit(page_size).all()

        return [{
            "stock_code": s.stock_code,
            "stock_name": s.stock_name,
            "industry": s.industry or "",
            "sector": s.sector or ""
        } for s in stocks]
    finally:
        db.close()


@app.get("/api/stock/search")
async def search_stock(keyword: str):
    """搜索股票（代码/名称模糊搜索）"""
    db = get_db()
    try:
        # 模糊搜索
        stocks = db.query(StockInfo).filter(
            (StockInfo.stock_code.like(f"%{keyword}%")) |
            (StockInfo.stock_name.like(f"%{keyword}%"))
        ).limit(20).all()

        return [{
            "stock_code": s.stock_code,
            "stock_name": s.stock_name
        } for s in stocks]
    finally:
        db.close()


@app.get("/api/stock/realtime")
async def get_realtime(stock_code: str):
    """获取个股实时行情"""
    db = get_db()
    try:
        rt = db.query(StockRealtime).filter(StockRealtime.stock_code == stock_code).first()

        if not rt:
            # 尝试获取数据
            quotes = await crawler.get_realtime_quote([stock_code])
            if quotes:
                crawler.save_realtime_data(quotes)
                rt = db.query(StockRealtime).filter(StockRealtime.stock_code == stock_code).first()

        if not rt:
            raise HTTPException(status_code=404, detail="股票不存在")

        return {
            "stock_code": rt.stock_code,
            "stock_name": rt.stock_name,
            "open_price": rt.open_price,
            "close_price": rt.close_price,
            "current_price": rt.current_price,
            "high_price": rt.high_price,
            "low_price": rt.low_price,
            "volume": rt.volume,
            "amount": rt.amount,
            "change_pct": rt.change_pct,
            "change_amount": rt.change_amount,
            "bid_price1": rt.bid_price1, "bid_price2": rt.bid_price2, "bid_price3": rt.bid_price3,
            "bid_price4": rt.bid_price4, "bid_price5": rt.bid_price5,
            "ask_price1": rt.ask_price1, "ask_price2": rt.ask_price2, "ask_price3": rt.ask_price3,
            "ask_price4": rt.ask_price4, "ask_price5": rt.ask_price5,
            "bid_volume1": rt.bid_volume1, "bid_volume2": rt.bid_volume2, "bid_volume3": rt.bid_volume3,
            "bid_volume4": rt.bid_volume4, "bid_volume5": rt.bid_volume5,
            "ask_volume1": rt.ask_volume1, "ask_volume2": rt.ask_volume2, "ask_volume3": rt.ask_volume3,
            "ask_volume4": rt.ask_volume4, "ask_volume5": rt.ask_volume5,
            "turnover_rate": rt.turnover_rate or 0,
            "pe_ratio": rt.pe_ratio or 0,
            "pb_ratio": rt.pb_ratio or 0,
            "market_cap": rt.market_cap or 0,
            "limit_up_price": rt.limit_up_price,
            "limit_down_price": rt.limit_down_price,
            "volume_ratio": rt.volume_ratio or 0
        }
    finally:
        db.close()


@app.get("/api/stock/kline")
async def get_kline(stock_code: str, kline_type: str = "day"):
    """获取K线数据"""
    db = get_db()
    try:
        # 每次都从API获取最新数据
        new_klines = await crawler.get_kline_data(stock_code, kline_type, 100)

        # 更新或插入新数据
        for k in new_klines:
            existing = db.query(KlineData).filter(
                KlineData.stock_code == stock_code,
                KlineData.kline_type == kline_type,
                KlineData.kline_date == k['kline_date']
            ).first()
            if existing:
                # 更新已有数据
                existing.open_price = k['open_price']
                existing.close_price = k['close_price']
                existing.high_price = k['high_price']
                existing.low_price = k['low_price']
                existing.volume = k['volume']
                existing.amount = k['amount']
            else:
                db.add(KlineData(**k))

        db.commit()

        # 返回数据库中的数据
        klines = db.query(KlineData).filter(
            KlineData.stock_code == stock_code,
            KlineData.kline_type == kline_type
        ).order_by(KlineData.kline_date).all()

        return [{
            "date": k.kline_date,
            "open": k.open_price,
            "close": k.close_price,
            "high": k.high_price,
            "low": k.low_price,
            "volume": k.volume,
            "amount": k.amount
        } for k in klines]
    finally:
        db.close()


@app.get("/api/stock/timeline")
async def get_timeline(stock_code: str):
    """获取分时数据"""
    db = get_db()
    try:
        rt = db.query(StockRealtime).filter(StockRealtime.stock_code == stock_code).first()

        base_price = rt.current_price if rt and rt.current_price > 0 else 10.0

        timeline = []
        # 从9:30开始
        current_time = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
        now = datetime.now()
        # 结束时间：当前时间或15:00（收盘），取较早者
        end_time = min(now.replace(second=0, microsecond=0), datetime.now().replace(hour=15, minute=0, second=0, microsecond=0))

        i = 0
        while current_time <= end_time:
            # 跳过午休时间 11:30-13:00
            if current_time.hour == 11 and current_time.minute >= 30:
                current_time = current_time.replace(hour=13, minute=0, second=0, microsecond=0)
                continue
            if current_time.hour >= 11 and current_time.hour < 13:
                current_time += timedelta(minutes=1)
                continue

            # 使用时间作为hash种子，保证同一时间每次生成相同数据
            time_hash = hash(f"{stock_code}{current_time.strftime('%H%M')}")
            change = (time_hash % 100 - 50) / 1000
            price = round(base_price * (1 + change), 2)

            timeline.append({
                "time": current_time.strftime('%H:%M'),
                "price": price,
                "volume": (time_hash % 10000) + 1000,
                "amount": round(price * (time_hash % 10000 + 1000), 2)
            })

            current_time += timedelta(minutes=1)
            i += 1

        return timeline
    finally:
        db.close()


@app.get("/api/sectors")
async def get_sectors():
    """获取板块分类"""
    sectors = [
        {"code": "industry_tech", "name": "科技", "stocks": ["600000", "600036", "600519", "601318", "600028"]},
        {"code": "industry_finance", "name": "金融", "stocks": ["601398", "000001", "600030"]},
        {"code": "industry_consume", "name": "消费", "stocks": ["600887", "000858", "601888"]},
        {"code": "industry_new_energy", "name": "新能源", "stocks": ["002594", "300750", "688981"]},
    ]
    return sectors


@app.get("/api/watchlist")
async def get_watchlist():
    """获取自选股列表"""
    db = get_db()
    try:
        watchlist = db.query(WatchList).all()
        return [{
            "stock_code": w.stock_code,
            "stock_name": w.stock_name,
            "added_at": w.added_at.strftime('%Y-%m-%d %H:%M:%S') if w.added_at else ""
        } for w in watchlist]
    finally:
        db.close()


@app.post("/api/watchlist")
async def add_to_watchlist(stock_code: str, stock_name: str):
    """添加自选股"""
    db = get_db()
    try:
        existing = db.query(WatchList).filter(WatchList.stock_code == stock_code).first()
        if existing:
            return {"success": True, "message": "已在自选列表中"}

        watch = WatchList(stock_code=stock_code, stock_name=stock_name)
        db.add(watch)
        db.commit()
        return {"success": True, "message": "添加成功"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}
    finally:
        db.close()


@app.delete("/api/watchlist/{stock_code}")
async def remove_from_watchlist(stock_code: str):
    """移除自选股"""
    db = get_db()
    try:
        watch = db.query(WatchList).filter(WatchList.stock_code == stock_code).first()
        if watch:
            db.delete(watch)
            db.commit()
            return {"success": True, "message": "移除成功"}
        return {"success": False, "message": "股票不在自选列表中"}
    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}
    finally:
        db.close()


@app.get("/api/market/overview")
async def get_market_overview():
    """获取市场概况"""
    db = get_db()
    try:
        stocks = db.query(StockRealtime).limit(100).all()

        if not stocks:
            return {
                "up_count": 0,
                "down_count": 0,
                "total_count": 0,
                "hot_stocks": []
            }

        up = sum(1 for s in stocks if s.change_pct > 0)
        down = sum(1 for s in stocks if s.change_pct < 0)

        hot = sorted(stocks, key=lambda x: abs(x.change_pct or 0), reverse=True)[:10]

        return {
            "up_count": up,
            "down_count": down,
            "total_count": len(stocks),
            "hot_stocks": [{
                "stock_code": s.stock_code,
                "stock_name": s.stock_name,
                "change_pct": s.change_pct,
                "current_price": s.current_price
            } for s in hot]
        }
    finally:
        db.close()


# ==================== 定时任务 ====================
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def update_realtime_data():
    """定时更新实时行情"""
    db = get_db()
    try:
        # 获取所有需要更新的股票
        stocks = db.query(StockRealtime).all()
        stock_codes = [s.stock_code for s in stocks]

        if stock_codes:
            quotes = await crawler.get_realtime_quote(stock_codes)
            if quotes:
                crawler.save_realtime_data(quotes)
                print(f"更新了 {len(quotes)} 只股票的行情")
    except Exception as e:
        print(f"更新行情失败: {e}")
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("正在初始化系统...")

    # 初始化数据库
    init_db()
    init_default_account()

    # 初始化爬虫数据
    await initialize_data()

    # 获取并保存行情数据
    stock_codes = [
        '600000', '600036', '600519', '601318', '601398', '600028',
        '600887', '000002', '000858', '002594', '300750', '688981',
        '000001', '600030', '601888', '601012', '600309', '600900',
        '601988', '601628', '600016', '601166', '600015', '601288'
    ]

    try:
        quotes = await crawler.get_realtime_quote(stock_codes)
        if quotes:
            crawler.save_realtime_data(quotes)
            print(f"获取了 {len(quotes)} 只股票的实时行情")
    except Exception as e:
        print(f"获取行情数据失败: {e}")

    # 启动定时任务
    scheduler.add_job(update_realtime_data, 'interval', seconds=30, id='update_realtime')
    scheduler.start()

    print("系统启动完成！")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    scheduler.shutdown()
    await crawler.close_session()
    print("系统已关闭")


# ==================== 启动应用 ====================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000, reload=False)