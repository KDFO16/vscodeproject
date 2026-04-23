"""
Virtual Trading System - Database Module
Windows compatible SQLite database setup with SQLAlchemy 2.0
"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'trading_system.db')

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SystemAccount(Base):
    """系统单一账号表"""
    __tablename__ = 'system_account'

    id = Column(Integer, primary_key=True, index=True)
    account_name = Column(String(50), default="系统账号")
    total_capital = Column(Float, default=100000.0)  # 总资产
    available_capital = Column(Float, default=100000.0)  # 可用资金
    frozen_capital = Column(Float, default=0.0)  # 冻结资金
    market_value = Column(Float, default=0.0)  # 市值
    total_profit = Column(Float, default=0.0)  # 总盈亏
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class StockInfo(Base):
    """股票基础信息表"""
    __tablename__ = 'stock_info'

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), unique=True, index=True)  # 股票代码
    stock_name = Column(String(100))  # 股票名称
    listing_date = Column(String(20))  # 上市日期
    total_shares = Column(Float)  # 总股本
    float_shares = Column(Float)  # 流通股本
    industry = Column(String(50))  # 所属行业
    sector = Column(String(50))  # 板块分类


class StockRealtime(Base):
    """实时行情表"""
    __tablename__ = 'stock_rt'

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), unique=True, index=True)
    stock_name = Column(String(100))
    open_price = Column(Float)  # 开盘价
    close_price = Column(Float)  # 昨收价
    current_price = Column(Float)  # 当前价
    high_price = Column(Float)  # 最高价
    low_price = Column(Float)  # 最低价
    volume = Column(Float)  # 成交量
    amount = Column(Float)  # 成交额
    bid_price1 = Column(Float)  # 买一价
    bid_price2 = Column(Float)
    bid_price3 = Column(Float)
    bid_price4 = Column(Float)
    bid_price5 = Column(Float)
    ask_price1 = Column(Float)  # 卖一价
    ask_price2 = Column(Float)
    ask_price3 = Column(Float)
    ask_price4 = Column(Float)
    ask_price5 = Column(Float)
    bid_volume1 = Column(Integer)  # 买一量
    bid_volume2 = Column(Integer)
    bid_volume3 = Column(Integer)
    bid_volume4 = Column(Integer)
    bid_volume5 = Column(Integer)
    ask_volume1 = Column(Integer)  # 卖一量
    ask_volume2 = Column(Integer)
    ask_volume3 = Column(Integer)
    ask_volume4 = Column(Integer)
    ask_volume5 = Column(Integer)
    change_pct = Column(Float)  # 涨跌幅
    change_amount = Column(Float)  # 涨跌额
    turnover_rate = Column(Float)  # 换手率
    pe_ratio = Column(Float)  # 市盈率
    pb_ratio = Column(Float)  # 市净率
    market_cap = Column(Float)  # 总市值
    float_market_cap = Column(Float)  # 流通市值
    limit_up_price = Column(Float)  # 涨停价
    limit_down_price = Column(Float)  # 跌停价
    volume_ratio = Column(Float)  # 量比
    updated_at = Column(DateTime, default=datetime.now)


class KlineData(Base):
    """K线数据表"""
    __tablename__ = 'kline_data'

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), index=True)
    kline_type = Column(String(10))  # day/week/month/minute
    kline_date = Column(String(20))  # K线日期
    open_price = Column(Float)
    close_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    updated_at = Column(DateTime, default=datetime.now)


class Order(Base):
    """交易订单表"""
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(50), unique=True)  # 订单号
    stock_code = Column(String(10))
    stock_name = Column(String(100))
    direction = Column(String(10))  # buy/sell
    order_type = Column(String(20))  # market/limit
    price = Column(Float)  # 成交价格
    volume = Column(Integer)  # 成交量（股数）
    amount = Column(Float)  # 成交金额
    status = Column(String(20))  # pending/completed/cancelled
    order_time = Column(DateTime, default=datetime.now)
    deal_time = Column(DateTime)


class Position(Base):
    """持仓表"""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), unique=True)
    stock_name = Column(String(100))
    volume = Column(Integer)  # 持仓数量
    available_volume = Column(Integer)  # 可用数量（T+1）
    cost_price = Column(Float)  # 成本价
    current_price = Column(Float)  # 当前价
    market_value = Column(Float)  # 市值
    profit_loss = Column(Float)  # 浮动盈亏
    profit_ratio = Column(Float)  # 盈亏比例
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WatchList(Base):
    """自选股表"""
    __tablename__ = 'watchlist'

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(10), unique=True, index=True)
    stock_name = Column(String(100))
    added_at = Column(DateTime, default=datetime.now)


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def init_default_account():
    """初始化默认账号"""
    db = SessionLocal()
    try:
        account = db.query(SystemAccount).filter(SystemAccount.id == 1).first()
        if not account:
            account = SystemAccount(
                id=1,
                account_name="系统账号",
                total_capital=100000.0,
                available_capital=100000.0,
                frozen_capital=0.0,
                market_value=0.0,
                total_profit=0.0
            )
            db.add(account)
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    init_default_account()
    print("数据库初始化完成！")