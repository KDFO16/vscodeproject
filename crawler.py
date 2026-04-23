"""
Virtual Trading System - Data Crawler Module
Async crawler for Sina Finance A-share market data
"""
import asyncio
import aiohttp
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from database import SessionLocal, StockInfo, StockRealtime, KlineData, init_default_account


# 新浪财经A股列表URL
STOCK_LIST_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

# 新浪财经板块分类URL
SECTOR_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount"

# 实时行情URL
REALTIME_URL = "https://hq.sinajs.cn/list="

# K线数据URL - JSON格式
KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"


class StockCrawler:
    """股票数据爬虫类"""

    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn/',
        }

    async def init_session(self):
        """初始化异步HTTP会话"""
        if self.session is None:
            self.session = aiohttp.ClientSession(headers=self.headers)

    async def close_session(self):
        """关闭异步HTTP会话"""
        if self.session:
            await self.session.close()

    def _safe_float(self, val):
        """安全转换为浮点数"""
        try:
            return float(val) if val and val.strip() else 0.0
        except (ValueError, AttributeError):
            return 0.0

    def _safe_int(self, val):
        """安全转换为整数"""
        try:
            return int(val) if val and val.strip() else 0
        except (ValueError, AttributeError):
            return 0

    async def fetch(self, url, params=None):
        """异步获取页面数据"""
        await self.init_session()
        try:
            async with self.session.get(url, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def _add_prefix(self, code):
        """添加沪深前缀"""
        code = code.strip()
        if code.startswith('sh') or code.startswith('sz'):
            return code
        if code.startswith('6') or code.startswith('5') or code.startswith('9'):
            return 'sh' + code
        return 'sz' + code

    def _strip_prefix(self, code):
        """去除前缀"""
        if code.startswith('sh') or code.startswith('sz'):
            return code[2:]
        return code

    async def get_realtime_quote(self, stock_codes):
        """获取实时行情数据"""
        if not stock_codes:
            return []

        # 添加前缀
        codes_with_prefix = [self._add_prefix(c) for c in stock_codes]
        codes_str = ','.join(codes_with_prefix)
        url = REALTIME_URL + codes_str
        content = await self.fetch(url)

        if not content:
            return []

        quotes = []
        lines = content.strip().split('\n')

        for line in lines:
            match = re.search(r'hq_str_(\w+)=\"([^\"]+)\"', line)
            if match:
                code_with_prefix = match.group(1)
                code = self._strip_prefix(code_with_prefix)
                data_str = match.group(2)
                fields = data_str.split(',')

                if len(fields) >= 32:
                    quote = {
                        'stock_code': code,
                        'stock_name': fields[0],
                        'open_price': self._safe_float(fields[1]),
                        'close_price': self._safe_float(fields[2]),
                        'current_price': self._safe_float(fields[3]),
                        'high_price': self._safe_float(fields[4]),
                        'low_price': self._safe_float(fields[5]),
                        'volume': self._safe_float(fields[8]),
                        'amount': self._safe_float(fields[9]),
                        'bid_price1': self._safe_float(fields[10]),
                        'bid_price2': self._safe_float(fields[11]),
                        'bid_price3': self._safe_float(fields[12]),
                        'bid_price4': self._safe_float(fields[13]),
                        'bid_price5': self._safe_float(fields[14]),
                        'ask_price1': self._safe_float(fields[15]),
                        'ask_price2': self._safe_float(fields[16]),
                        'ask_price3': self._safe_float(fields[17]),
                        'ask_price4': self._safe_float(fields[18]),
                        'ask_price5': self._safe_float(fields[19]),
                        'bid_volume1': self._safe_int(fields[20]),
                        'bid_volume2': self._safe_int(fields[21]),
                        'bid_volume3': self._safe_int(fields[22]),
                        'bid_volume4': self._safe_int(fields[23]),
                        'bid_volume5': self._safe_int(fields[24]),
                        'ask_volume1': self._safe_int(fields[25]),
                        'ask_volume2': self._safe_int(fields[26]),
                        'ask_volume3': self._safe_int(fields[27]),
                        'ask_volume4': self._safe_int(fields[28]),
                        'ask_volume5': self._safe_int(fields[29]),
                    }

                    # 计算涨跌幅
                    if quote['close_price'] > 0:
                        quote['change_amount'] = round(quote['current_price'] - quote['close_price'], 2)
                        quote['change_pct'] = round((quote['change_amount'] / quote['close_price']) * 100, 2)
                    else:
                        quote['change_amount'] = 0
                        quote['change_pct'] = 0

                    # 涨停跌停价
                    quote['limit_up_price'] = round(quote['close_price'] * 1.1, 2) if quote['close_price'] > 0 else 0
                    quote['limit_down_price'] = round(quote['close_price'] * 0.9, 2) if quote['close_price'] > 0 else 0

                    quotes.append(quote)

        return quotes

    async def get_stock_list(self, page=1, num=100):
        """获取A股股票列表"""
        params = {
            'page': page,
            'num': num,
            'sort': 'symbol',
            'asc': 1,
            'node': 'hs_a'
        }
        content = await self.fetch(STOCK_LIST_URL, params)

        if not content:
            return []

        stocks = []
        try:
            # 解析JSON数据
            import json
            data = json.loads(content)
            for item in data:
                stock = {
                    'stock_code': item.get('symbol', '').replace('sh', '').replace('sz', ''),
                    'stock_name': item.get('name', ''),
                    'open_price': float(item.get('open', 0)),
                    'close_price': float(item.get('settlement', 0)),
                    'current_price': float(item.get('trade', 0)),
                    'high_price': float(item.get('high', 0)),
                    'low_price': float(item.get('low', 0)),
                    'volume': float(item.get('volume', 0)),
                    'amount': float(item.get('amount', 0)),
                }
                stocks.append(stock)
        except Exception as e:
            print(f"解析股票列表失败: {e}")

        return stocks

    async def get_kline_data(self, stock_code, kline_type='day', count=100):
        """获取K线数据"""
        import json

        # 添加股票前缀
        if stock_code.startswith('sh') or stock_code.startswith('sz'):
            symbol = stock_code
        elif stock_code.startswith('6') or stock_code.startswith('5') or stock_code.startswith('9'):
            symbol = 'sh' + stock_code
        else:
            symbol = 'sz' + stock_code

        # 根据K线类型设置数据量
        # 日K 3个月：约65条交易日
        # 周K 1年3个月：约325条交易日
        # 月K 5年3个月：约1260条交易日
        if kline_type == 'day':
            datalen = 100
        elif kline_type == 'week':
            datalen = 500
        elif kline_type == 'month':
            datalen = 1500
        else:
            datalen = 100

        params = {
            'symbol': symbol,
            'scale': 240,  # 日K
            'ma': 'no',
            'datalen': datalen
        }

        content = await self.fetch(KLINE_URL, params)

        if not content:
            return self._generate_fallback_kline(stock_code, kline_type, count)

        try:
            data = json.loads(content)
            if not data or len(data) == 0:
                return self._generate_fallback_kline(stock_code, kline_type, count)

            # 新浪API返回数据是升序（最老→最新）
            # 反转为倒序（最新→最老）
            data = list(reversed(data))

            # 转换日期格式
            for item in data:
                item['day'] = item.get('day', '')[:10]

            # 周K/月K：使用全部数据聚合，不在这里截取
            if kline_type == 'week':
                klines = self._aggregate_daily_to_weekly(data, stock_code)
            elif kline_type == 'month':
                klines = self._aggregate_daily_to_monthly(data, stock_code)
            else:
                # 日K：取最近的count条
                data = data[:count]
                # 再反转回升序（最老→最新）返回给前端
                data = list(reversed(data))
                klines = [{
                    'stock_code': stock_code,
                    'kline_type': 'day',
                    'kline_date': item.get('day', ''),
                    'open_price': float(item.get('open', 0)),
                    'close_price': float(item.get('close', 0)),
                    'high_price': float(item.get('high', 0)),
                    'low_price': float(item.get('low', 0)),
                    'volume': float(item.get('volume', 0)),
                    'amount': float(item.get('amount', 0)),
                } for item in data]

            # 周K/月K：返回最近的count条（聚合后）
            if kline_type in ['week', 'month']:
                klines = klines[-count:] if len(klines) > count else klines

            return klines
        except Exception as e:
            print(f"解析K线数据失败: {e}")
            return self._generate_fallback_kline(stock_code, kline_type, count)

    def _aggregate_to_week(self, data, stock_code):
        """聚合日K为周K"""
        if not data:
            return []

        from collections import defaultdict
        from datetime import datetime

        # 按周分组
        week_data = defaultdict(list)
        for item in data:
            day = item.get('day', '')
            if not day:
                continue
            try:
                d = datetime.strptime(day, '%Y-%m-%d')
                week_key = d.strftime('%Y-W%W')
                week_data[week_key].append(item)
            except:
                continue

        result = []
        for week_key in sorted(week_data.keys()):
            items = week_data[week_key]
            if items:
                result.append({
                    'stock_code': stock_code,
                    'kline_type': 'week',
                    'kline_date': week_key,
                    'open_price': float(items[0].get('open', 0)),
                    'close_price': float(items[-1].get('close', 0)),
                    'high_price': max(float(i.get('high', 0)) for i in items),
                    'low_price': min(float(i.get('low', 0)) for i in items if float(i.get('low', 0)) > 0),
                    'volume': sum(float(i.get('volume', 0)) for i in items),
                    'amount': sum(float(i.get('amount', 0)) for i in items),
                })

        return result

    def _aggregate_to_month(self, data, stock_code):
        """聚合日K为月K"""
        if not data:
            return []

        from collections import defaultdict

        # 按月分组
        month_data = defaultdict(list)
        for item in data:
            day = item.get('day', '')
            if not day:
                continue
            month_key = day[:7]  # YYYY-MM
            month_data[month_key].append(item)

        result = []
        for month_key in sorted(month_data.keys()):
            items = month_data[month_key]
            if items:
                result.append({
                    'stock_code': stock_code,
                    'kline_type': 'month',
                    'kline_date': month_key,
                    'open_price': float(items[0].get('open', 0)),
                    'close_price': float(items[-1].get('close', 0)),
                    'high_price': max(float(i.get('high', 0)) for i in items),
                    'low_price': min(float(i.get('low', 0)) for i in items if float(i.get('low', 0)) > 0),
                    'volume': sum(float(i.get('volume', 0)) for i in items),
                    'amount': sum(float(i.get('amount', 0)) for i in items),
                })

        return result

    def _aggregate_daily_to_weekly(self, data, stock_code):
        """将日K数据聚合为周K（data是升序，最老→最新）"""
        if not data:
            return []

        from collections import defaultdict
        from datetime import datetime

        # 按周分组
        week_data = defaultdict(list)
        for item in data:
            day = item.get('day', '')
            if not day:
                continue
            try:
                d = datetime.strptime(day, '%Y-%m-%d')
                # 周一作为一周的开始
                week_start = d - timedelta(days=d.weekday())
                week_key = week_start.strftime('%Y-%m-%d')
                week_data[week_key].append(item)
            except:
                continue

        result = []
        for week_key in sorted(week_data.keys()):
            items = week_data[week_key]
            if items:
                result.append({
                    'stock_code': stock_code,
                    'kline_type': 'week',
                    'kline_date': week_key,
                    'open_price': float(items[0].get('open', 0)),  # 这周第一天开盘价
                    'close_price': float(items[-1].get('close', 0)),  # 这周最后一天收盘价
                    'high_price': max(float(i.get('high', 0)) for i in items),
                    'low_price': min(float(i.get('low', 0)) for i in items if float(i.get('low', 0)) > 0),
                    'volume': sum(float(i.get('volume', 0)) for i in items),
                    'amount': sum(float(i.get('amount', 0)) for i in items),
                })

        return result

    def _aggregate_daily_to_monthly(self, data, stock_code):
        """将日K数据聚合为月K（data是升序，最老→最新）"""
        if not data:
            return []

        from collections import defaultdict

        # 按月分组
        month_data = defaultdict(list)
        for item in data:
            day = item.get('day', '')
            if not day:
                continue
            month_key = day[:7]  # YYYY-MM
            month_data[month_key].append(item)

        result = []
        for month_key in sorted(month_data.keys()):
            items = month_data[month_key]
            if items:
                result.append({
                    'stock_code': stock_code,
                    'kline_type': 'month',
                    'kline_date': month_key,
                    'open_price': float(items[0].get('open', 0)),  # 这个月第一天开盘价
                    'close_price': float(items[-1].get('close', 0)),  # 这个月最后一天收盘价
                    'high_price': max(float(i.get('high', 0)) for i in items),
                    'low_price': min(float(i.get('low', 0)) for i in items if float(i.get('low', 0)) > 0),
                    'volume': sum(float(i.get('volume', 0)) for i in items),
                    'amount': sum(float(i.get('amount', 0)) for i in items),
                })

        return result

    def _generate_fallback_kline(self, stock_code, kline_type, count):
        """生成模拟K线数据作为备用"""
        all_data = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=count * 2)

        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        base_price = 10.0
        for date in dates[-count:]:
            change = (hash(stock_code + date) % 100 - 50) / 100
            base_price = max(1, base_price * (1 + change * 0.02))

            kline = {
                'stock_code': stock_code,
                'kline_type': kline_type,
                'kline_date': date,
                'open_price': round(base_price * (1 - change * 0.01), 2),
                'close_price': round(base_price, 2),
                'high_price': round(base_price * (1 + abs(change) * 0.02), 2),
                'low_price': round(base_price * (1 - abs(change) * 0.015), 2),
                'volume': (hash(stock_code + date + 'v') % 10000000) + 1000000,
                'amount': (hash(stock_code + date + 'a') % 100000000) + 10000000,
            }
            all_data.append(kline)

        return all_data

    def save_realtime_data(self, quotes):
        """保存实时行情数据到数据库"""
        db = SessionLocal()
        try:
            for quote in quotes:
                existing = db.query(StockRealtime).filter(
                    StockRealtime.stock_code == quote['stock_code']
                ).first()

                if existing:
                    # 更新现有记录 - 只更新模型中存在的字段
                    for key in ['stock_name', 'open_price', 'close_price', 'current_price',
                                'high_price', 'low_price', 'volume', 'amount',
                                'bid_price1', 'bid_price2', 'bid_price3', 'bid_price4', 'bid_price5',
                                'ask_price1', 'ask_price2', 'ask_price3', 'ask_price4', 'ask_price5',
                                'bid_volume1', 'bid_volume2', 'bid_volume3', 'bid_volume4', 'bid_volume5',
                                'ask_volume1', 'ask_volume2', 'ask_volume3', 'ask_volume4', 'ask_volume5',
                                'change_pct', 'change_amount', 'turnover_rate', 'pe_ratio', 'pb_ratio',
                                'market_cap', 'float_market_cap', 'limit_up_price', 'limit_down_price', 'volume_ratio']:
                        if key in quote:
                            setattr(existing, key, quote[key])
                    existing.updated_at = datetime.now()
                else:
                    # 创建新记录 - 只使用模型中存在的字段
                    new_quote = StockRealtime(
                        stock_code=quote['stock_code'],
                        stock_name=quote.get('stock_name', ''),
                        open_price=quote.get('open_price', 0),
                        close_price=quote.get('close_price', 0),
                        current_price=quote.get('current_price', 0),
                        high_price=quote.get('high_price', 0),
                        low_price=quote.get('low_price', 0),
                        volume=quote.get('volume', 0),
                        amount=quote.get('amount', 0),
                        bid_price1=quote.get('bid_price1', 0),
                        bid_price2=quote.get('bid_price2', 0),
                        bid_price3=quote.get('bid_price3', 0),
                        bid_price4=quote.get('bid_price4', 0),
                        bid_price5=quote.get('bid_price5', 0),
                        ask_price1=quote.get('ask_price1', 0),
                        ask_price2=quote.get('ask_price2', 0),
                        ask_price3=quote.get('ask_price3', 0),
                        ask_price4=quote.get('ask_price4', 0),
                        ask_price5=quote.get('ask_price5', 0),
                        bid_volume1=quote.get('bid_volume1', 0),
                        bid_volume2=quote.get('bid_volume2', 0),
                        bid_volume3=quote.get('bid_volume3', 0),
                        bid_volume4=quote.get('bid_volume4', 0),
                        bid_volume5=quote.get('bid_volume5', 0),
                        ask_volume1=quote.get('ask_volume1', 0),
                        ask_volume2=quote.get('ask_volume2', 0),
                        ask_volume3=quote.get('ask_volume3', 0),
                        ask_volume4=quote.get('ask_volume4', 0),
                        ask_volume5=quote.get('ask_volume5', 0),
                        change_pct=quote.get('change_pct', 0),
                        change_amount=quote.get('change_amount', 0),
                        turnover_rate=quote.get('turnover_rate', 0),
                        pe_ratio=quote.get('pe_ratio', 0),
                        pb_ratio=quote.get('pb_ratio', 0),
                        market_cap=quote.get('market_cap', 0),
                        float_market_cap=quote.get('float_market_cap', 0),
                        limit_up_price=quote.get('limit_up_price', 0),
                        limit_down_price=quote.get('limit_down_price', 0),
                        volume_ratio=quote.get('volume_ratio', 0),
                    )
                    db.add(new_quote)

            db.commit()
        except Exception as e:
            print(f"保存实时数据失败: {e}")
            db.rollback()
        finally:
            db.close()

    def save_stock_info(self, stocks):
        """保存股票基本信息到数据库"""
        db = SessionLocal()
        try:
            for stock in stocks:
                existing = db.query(StockInfo).filter(
                    StockInfo.stock_code == stock['stock_code']
                ).first()

                if not existing:
                    info = StockInfo(
                        stock_code=stock['stock_code'],
                        stock_name=stock['stock_name']
                    )
                    db.add(info)

            db.commit()
        except Exception as e:
            print(f"保存股票信息失败: {e}")
            db.rollback()
        finally:
            db.close()

    async def update_all_quotes(self, stock_codes):
        """更新所有股票行情"""
        quotes = await self.get_realtime_quote(stock_codes)
        if quotes:
            self.save_realtime_data(quotes)
        return quotes


# 全局爬虫实例
crawler = StockCrawler()


async def initialize_data():
    """初始化数据"""
    print("正在初始化数据...")

    # 初始化默认账号
    init_default_account()

    # 初始化一些常见股票
    common_stocks = [
        ('600000', '浦发银行'), ('600036', '招商银行'), ('600519', '贵州茅台'),
        ('601318', '中国平安'), ('601398', '工商银行'), ('600028', '中国石化'),
        ('600887', '伊利股份'), ('000002', '万科A'), ('000858', '五粮液'),
        ('002594', '比亚迪'), ('300750', '宁德时代'), ('688981', '中芯国际'),
        ('000001', '平安银行'), ('600030', '中信证券'), ('601888', '中国中免'),
    ]

    db = SessionLocal()
    try:
        for code, name in common_stocks:
            existing = db.query(StockInfo).filter(StockInfo.stock_code == code).first()
            if not existing:
                info = StockInfo(stock_code=code, stock_name=name)
                db.add(info)

        db.commit()
    finally:
        db.close()

    print("数据初始化完成！")


if __name__ == "__main__":
    asyncio.run(initialize_data())
