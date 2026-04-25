/**
 * A股模拟交易系统 - 前端应用
 * Vue3 + Axios + ECharts
 */
const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;

// 创建Vue应用
const app = createApp({
    setup() {
        // ==================== 状态定义 ====================
        const currentTime = ref('');
        const viewMode = ref('timeline'); // timeline / kline
        const klineType = ref('day'); // day / week / month
        const leftTab = ref('watch'); // watch / market / sector

        // 账户信息
        const accountInfo = ref({
            total_capital: 0,
            available_capital: 0,
            market_value: 0,
            total_profit: 0
        });

        // 股票相关
        const searchKeyword = ref('');
        const searchResults = ref([]);
        const watchList = ref([]);
        const marketStocks = ref([]);
        const sectors = ref([]);
        const selectedStock = ref(null);
        const currentStock = ref(null);

        // 持仓相关
        const positions = ref([]);
        const selectedPosition = computed(() => {
            if (!selectedStock.value) return null;
            return positions.value.find(p => p.stock_code === selectedStock.value);
        });

        // 交易相关
        const tradeDirection = ref('buy');
        const tradeVolume = ref(100);
        const tradePrice = ref(0);  // 周末挂单价
        const orderResult = ref({ success: false, message: '' });

        // ECharts实例
        let chart = null;
        const chartRef = ref(null);

        // 分时数据
        const timelineData = ref([]);

        // K线数据
        const klineData = ref([]);

        // ==================== 工具函数 ====================
        const keep2Decimals = (val) => {
            if (val === null || val === undefined || val === '') return '0.00';
            return parseFloat(val).toFixed(2);
        };

        const getPriceClass = (changePct) => {
            if (changePct > 0) return 'up';
            if (changePct < 0) return 'down';
            return 'flat';
        };

        const formatVolume = (vol) => {
            if (!vol) return '0';
            if (vol >= 100000000) return (vol / 100000000).toFixed(2) + '亿';
            if (vol >= 10000) return (vol / 10000).toFixed(2) + '万';
            return vol.toString();
        };

        const formatAmount = (amount) => {
            if (!amount) return '0.00';
            if (amount >= 100000000) return (amount / 100000000).toFixed(2) + '亿';
            if (amount >= 10000) return (amount / 10000).toFixed(2) + '万';
            return amount.toFixed(2);
        };

        // ==================== 计算属性 ====================
        // 是否非交易时段（需要挂单价）：周末 + 工作日9:15前 + 工作日15:00后
        const isOffHours = computed(() => {
            const now = new Date();
            const day = now.getDay();
            const hours = now.getHours();
            const minutes = now.getMinutes();
            const time = hours * 60 + minutes;

            // 周六(6)周日(0)全天休市
            if (day === 0 || day === 6) return true;

            // 工作日：9:15前(夜市委托) 或 15:00后(收盘后委托)
            if (time < 9 * 60 + 15) return true;  // 9:15前
            if (time >= 15 * 60) return true;     // 15:00后

            return false;
        });

        const estimatedAmount = computed(() => {
            if (!currentStock.value) return 0;
            const price = isOffHours.value && tradePrice.value > 0 ? tradePrice.value : currentStock.value.current_price;
            return tradeVolume.value * price;
        });

        const availableToTrade = computed(() => {
            if (!currentStock.value) return 0;
            if (tradeDirection.value === 'buy') {
                const code = currentStock.value.stock_code;
                if (isKCBStock(code)) {
                    // 科创板：至少200股
                    return Math.max(200, Math.floor(accountInfo.value.available_capital / currentStock.value.current_price));
                }
                return Math.floor(accountInfo.value.available_capital / currentStock.value.current_price / 100) * 100;
            } else {
                return selectedPosition.value ? selectedPosition.value.available_volume : 0;
            }
        });

        // ==================== API调用 ====================
        const api = {
            getAccount: async () => {
                try {
                    const res = await axios.get('/api/account');
                    accountInfo.value = res.data;
                } catch (e) {
                    console.error('获取账户信息失败', e);
                }
            },

            getPositions: async () => {
                try {
                    const res = await axios.get('/api/positions');
                    positions.value = res.data;
                } catch (e) {
                    console.error('获取持仓失败', e);
                }
            },

            getOrders: async (limit = 50) => {
                try {
                    const res = await axios.get('/api/orders', { params: { limit } });
                    return res.data;
                } catch (e) {
                    console.error('获取订单失败', e);
                    return [];
                }
            },

            searchStock: async (keyword) => {
                if (!keyword.trim()) {
                    searchResults.value = [];
                    return;
                }
                try {
                    const res = await axios.get('/api/stock/search', { params: { keyword } });
                    searchResults.value = res.data;
                } catch (e) {
                    console.error('搜索失败', e);
                }
            },

            getRealtime: async (stockCode) => {
                try {
                    const res = await axios.get('/api/stock/realtime', { params: { stock_code: stockCode } });
                    return res.data;
                } catch (e) {
                    console.error('获取实时行情失败', e);
                    return null;
                }
            },

            getKline: async (stockCode, type = 'day') => {
                try {
                    const res = await axios.get('/api/stock/kline', { params: { stock_code: stockCode, kline_type: type } });
                    return res.data;
                } catch (e) {
                    console.error('获取K线失败', e);
                    return [];
                }
            },

            getTimeline: async (stockCode) => {
                try {
                    const res = await axios.get('/api/stock/timeline', { params: { stock_code: stockCode } });
                    return res.data;
                } catch (e) {
                    console.error('获取分时数据失败', e);
                    return [];
                }
            },

            getSectors: async () => {
                try {
                    const res = await axios.get('/api/sectors');
                    sectors.value = res.data;
                } catch (e) {
                    console.error('获取板块失败', e);
                }
            },

            getMarketOverview: async () => {
                try {
                    const res = await axios.get('/api/market/overview');
                    return res.data;
                } catch (e) {
                    console.error('获取市场概况失败', e);
                    return null;
                }
            },

            getWatchList: async () => {
                try {
                    const res = await axios.get('/api/watchlist');
                    return res.data;
                } catch (e) {
                    console.error('获取自选股失败', e);
                    return [];
                }
            },

            addToWatchListApi: async (stockCode, stockName) => {
                try {
                    const res = await axios.post('/api/watchlist', null, { params: { stock_code: stockCode, stock_name: stockName } });
                    return res.data;
                } catch (e) {
                    console.error('添加自选股失败', e);
                    return { success: false, message: '添加失败' };
                }
            },

            removeFromWatchList: async (stockCode) => {
                try {
                    const res = await axios.delete(`/api/watchlist/${stockCode}`);
                    return res.data;
                } catch (e) {
                    console.error('移除自选股失败', e);
                    return { success: false, message: '移除失败' };
                }
            },

            submitOrder: async (orderData) => {
                try {
                    const res = await axios.post('/api/order', orderData);
                    return res.data;
                } catch (e) {
                    return { success: false, message: e.response?.data?.detail || '下单失败' };
                }
            }
        };

        // ==================== 股票选择 ====================
        const selectStock = async (stockCode) => {
            selectedStock.value = stockCode;
            searchResults.value = [];
            searchKeyword.value = '';

            // 获取实时行情
            const rt = await api.getRealtime(stockCode);
            if (rt) {
                currentStock.value = rt;

                // 检查是否在自选股列表中，没有则添加
                const idx = watchList.value.findIndex(s => s.stock_code === stockCode);
                if (idx >= 0) {
                    watchList.value[idx] = { ...watchList.value[idx], ...rt };
                } else {
                    watchList.value.push(rt);
                    // 同时保存到数据库
                    await api.addToWatchListApi(stockCode, rt.stock_name);
                }

                // 加载图表数据
                if (viewMode.value === 'timeline') {
                    await loadTimelineData(stockCode);
                } else {
                    await loadKlineData(stockCode, klineType.value);
                }
            }
        };

        const selectSector = async (sector) => {
            // 切换到全市场标签页
            leftTab.value = 'market';
            // 清空现有股票
            marketStocks.value = [];
            // 加载板块内股票
            for (const code of sector.stocks) {
                const rt = await api.getRealtime(code);
                if (rt) {
                    marketStocks.value.push(rt);
                }
            }
        };

        const isInWatchList = (stockCode) => {
            return watchList.value.some(s => s.stock_code === stockCode);
        };

        const addToWatchList = async (stock) => {
            if (isInWatchList(stock.stock_code)) return;

            // 保存到数据库
            const result = await api.addToWatchListApi(stock.stock_code, stock.stock_name);
            if (result.success) {
                // 获取完整行情数据
                const rt = await api.getRealtime(stock.stock_code);
                if (rt) {
                    watchList.value.push(rt);
                } else {
                    // 如果没有实时数据，用基本信息创建
                    watchList.value.push({
                        stock_code: stock.stock_code,
                        stock_name: stock.stock_name,
                        current_price: 0,
                        change_pct: 0
                    });
                }
            }
        };

        const removeFromWatchList = async (stockCode) => {
            const result = await api.removeFromWatchList(stockCode);
            if (result.success) {
                // 从本地列表移除
                const idx = watchList.value.findIndex(s => s.stock_code === stockCode);
                if (idx >= 0) {
                    watchList.value.splice(idx, 1);
                }
                // 如果移除的是当前选中的股票，清空currentStock
                if (selectedStock.value === stockCode) {
                    selectedStock.value = null;
                    currentStock.value = null;
                }
            }
        };

        // ==================== 数据加载 ====================
        const loadTimelineData = async (stockCode) => {
            const data = await api.getTimeline(stockCode);
            if (data && data.length > 0) {
                timelineData.value = data;
                renderTimelineChart(data);
            }
        };

        const loadKlineData = async (stockCode, type) => {
            const data = await api.getKline(stockCode, type);
            if (data && data.length > 0) {
                klineData.value = data;
                renderKlineChart(data);
            }
        };

        const loadMarketStocks = async () => {
            // 加载常用股票到全市场列表（不添加到自选）
            const codes = [
                '600000', '600036', '600519', '601318', '601398', '600028',
                '600887', '000002', '000858', '002594', '300750', '688981',
                '000001', '600030', '601888'
            ];

            for (const code of codes) {
                const rt = await api.getRealtime(code);
                if (rt) {
                    if (!marketStocks.value.find(s => s.stock_code === code)) {
                        marketStocks.value.push(rt);
                    }
                }
            }
        };

        // ==================== 图表渲染 ====================
        const renderTimelineChart = (data) => {
            if (!chartRef.value) return;

            if (!chart) {
                chart = echarts.init(chartRef.value);
            }

            const times = data.map(d => d.time);
            const prices = data.map(d => d.price);
            const volumes = data.map(d => d.volume);

            const option = {
                backgroundColor: '#1E1E1E',
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    backgroundColor: '#252526',
                    borderColor: '#3C3C3C',
                    textStyle: { color: '#fff' }
                },
                grid: [
                    { left: '60', right: '20', top: '20', height: '60%' },
                    { left: '60', right: '20', top: '75%', height: '20%' }
                ],
                xAxis: [
                    {
                        type: 'category',
                        data: times,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { color: '#858585', fontSize: 10 },
                        splitLine: { show: false }
                    },
                    {
                        type: 'category',
                        data: times,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { show: false },
                        splitLine: { show: false }
                    }
                ],
                yAxis: [
                    {
                        type: 'value',
                        gridIndex: 0,
                        scale: true,
                        position: 'left',
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { color: '#858585', fontSize: 10 },
                        splitLine: { lineStyle: { color: '#2D2D30' } }
                    },
                    {
                        type: 'value',
                        gridIndex: 1,
                        scale: true,
                        position: 'left',
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { show: false },
                        splitLine: { show: false }
                    }
                ],
                series: [
                    {
                        name: '价格',
                        type: 'line',
                        data: prices,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        smooth: true,
                        symbol: 'none',
                        lineStyle: {
                            width: 2,
                            color: '#F23645'
                        },
                        areaStyle: {
                            color: {
                                type: 'linear',
                                x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    { offset: 0, color: 'rgba(242, 54, 69, 0.3)' },
                                    { offset: 1, color: 'rgba(242, 54, 69, 0.05)' }
                                ]
                            }
                        }
                    },
                    {
                        name: '成交量',
                        type: 'bar',
                        data: volumes,
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        itemStyle: { color: '#F23645' }
                    }
                ]
            };

            chart.setOption(option, { notMerge: true });
        };

        const renderKlineChart = (data) => {
            if (!chartRef.value) return;

            if (!chart) {
                chart = echarts.init(chartRef.value);
            }

            const dates = data.map(d => d.date);
            const ohlc = data.map(d => [d.open, d.close, d.low, d.high]);
            const volumes = data.map(d => d.volume);

            const upColor = '#F23645';
            const downColor = '#089B73';

            const option = {
                backgroundColor: '#1E1E1E',
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    backgroundColor: '#252526',
                    borderColor: '#3C3C3C',
                    textStyle: { color: '#fff' }
                },
                dataZoom: [
                    {
                        type: 'slider',
                        show: true,
                        xAxisIndex: [0, 1],
                        start: 0,
                        end: 100,
                        bottom: 10,
                        height: 25,
                        backgroundColor: '#252526',
                        borderColor: '#3C3C3C',
                        fillerColor: 'rgba(79, 195, 247, 0.2)',
                        handleStyle: { color: '#4FC3F7' },
                        textStyle: { color: '#858585', fontSize: 10 }
                    },
                    {
                        type: 'inside',
                        xAxisIndex: [0, 1],
                        start: 0,
                        end: 100
                    }
                ],
                grid: [
                    { left: '60', right: '20', top: '20', height: '55%' },
                    { left: '60', right: '20', top: '75%', height: '15%' }
                ],
                xAxis: [
                    {
                        type: 'category',
                        data: dates,
                        gridIndex: 0,
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { color: '#858585', fontSize: 10 },
                        splitLine: { show: false }
                    },
                    {
                        type: 'category',
                        data: dates,
                        gridIndex: 1,
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { show: false },
                        splitLine: { show: false }
                    }
                ],
                yAxis: [
                    {
                        type: 'value',
                        gridIndex: 0,
                        scale: true,
                        position: 'left',
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { color: '#858585', fontSize: 10 },
                        splitLine: { lineStyle: { color: '#2D2D30' } }
                    },
                    {
                        type: 'value',
                        gridIndex: 1,
                        scale: true,
                        position: 'left',
                        axisLine: { lineStyle: { color: '#3C3C3C' } },
                        axisLabel: { show: false },
                        splitLine: { show: false }
                    }
                ],
                series: [
                    {
                        name: 'K线',
                        type: 'candlestick',
                        data: ohlc,
                        xAxisIndex: 0,
                        yAxisIndex: 0,
                        itemStyle: {
                            color: upColor,
                            color0: downColor,
                            borderColor: upColor,
                            borderColor0: downColor
                        }
                    },
                    {
                        name: '成交量',
                        type: 'bar',
                        data: volumes,
                        xAxisIndex: 1,
                        yAxisIndex: 1,
                        itemStyle: {
                            color: (params) => {
                                const d = data[params.dataIndex];
                                return d.close >= d.open ? upColor : downColor;
                            }
                        }
                    }
                ]
            };

            chart.setOption(option, { notMerge: true });
        };

        // ==================== 视图切换 ====================
        const setViewMode = async (mode) => {
            viewMode.value = mode;
            if (currentStock.value) {
                if (mode === 'timeline') {
                    await loadTimelineData(currentStock.value.stock_code);
                } else {
                    await loadKlineData(currentStock.value.stock_code, klineType.value);
                }
            }
        };

        const setKlineType = async (type) => {
            klineType.value = type;
            if (viewMode.value === 'kline' && currentStock.value) {
                await loadKlineData(currentStock.value.stock_code, type);
            }
        };

        // ==================== 搜索功能 ====================
        let searchTimer = null;
        const searchStock = () => {
            if (searchTimer) clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                api.searchStock(searchKeyword.value);
            }, 300);
        };

        // ==================== 交易功能 ====================
        // 判断是否为科创板股票
        const isKCBStock = (code) => {
            return code && code.startsWith('688');
        };

        // 判断是否可交易（买入）
        const canBuyVolume = (code, volume) => {
            if (!code || volume <= 0) return false;
            if (isKCBStock(code)) {
                return volume >= 200; // 科创板首次买入≥200股
            }
            return volume % 100 === 0; // 其他板块100的整数倍
        };

        // 调整交易数量
        const adjustVolume = (delta) => {
            const code = currentStock.value?.stock_code;
            if (isKCBStock(code)) {
                // 科创板：可1股递增
                tradeVolume.value = Math.max(200, tradeVolume.value + delta);
            } else {
                // 其他板块：100的整数倍
                tradeVolume.value = Math.max(100, tradeVolume.value + delta);
                tradeVolume.value = Math.floor(tradeVolume.value / 100) * 100;
            }
        };

        const setMaxVolume = () => {
            if (tradeDirection.value === 'buy') {
                if (currentStock.value && currentStock.value.current_price > 0) {
                    const code = currentStock.value.stock_code;
                    let maxVol = Math.floor(accountInfo.value.available_capital / currentStock.value.current_price);
                    if (isKCBStock(code)) {
                        maxVol = Math.max(200, maxVol); // 科创板最少200
                    } else {
                        maxVol = Math.floor(maxVol / 100) * 100;
                    }
                    tradeVolume.value = maxVol;
                }
            } else {
                if (selectedPosition.value) {
                    tradeVolume.value = selectedPosition.value.available_volume;
                }
            }
        };

        const submitOrder = async () => {
            if (!currentStock.value || !tradeVolume.value) return;

            const code = currentStock.value.stock_code;

            // 买入数量检查
            if (tradeDirection.value === 'buy') {
                if (isKCBStock(code)) {
                    if (tradeVolume.value < 200) {
                        showToast('科创板首次买入必须≥200股', 'error');
                        return;
                    }
                } else {
                    if (tradeVolume.value % 100 !== 0) {
                        showToast('买入数量必须是100的整数倍', 'error');
                        return;
                    }
                }
            }

            // 周末挂单检查
            if (isOffHours.value) {
                if (!tradePrice.value || tradePrice.value <= 0) {
                    showToast('周末挂单必须输入价格', 'error');
                    return;
                }
                if (tradePrice.value < currentStock.value.limit_down_price || tradePrice.value > currentStock.value.limit_up_price) {
                    showToast(`挂单价必须在 [${currentStock.value.limit_down_price}, ${currentStock.value.limit_up_price}] 范围内`, 'error');
                    return;
                }
            }

            const orderData = {
                stock_code: code,
                direction: tradeDirection.value,
                price: isOffHours.value ? tradePrice.value : 0, // 周末用挂单价
                volume: tradeVolume.value
            };

            const result = await api.submitOrder(orderData);
            orderResult.value = result;

            if (result.success) {
                // 显示成功modal
                const modal = new bootstrap.Modal(document.getElementById('orderModal'));
                modal.show();

                // 刷新数据
                await api.getAccount();
                await api.getPositions();

                // 如果是买入，刷新持仓
                if (tradeDirection.value === 'buy') {
                    const pos = positions.value.find(p => p.stock_code === code);
                    if (pos) {
                        selectedPosition.value = pos;
                    }
                }
            } else {
                // 显示错误
                const modal = new bootstrap.Modal(document.getElementById('orderModal'));
                modal.show();
            }
        };

        // Toast提示
        const showToast = (message, type = 'success') => {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        };

        // ==================== 定时更新 ====================
        const updateTime = () => {
            const now = new Date();
            currentTime.value = now.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        };

        const refreshData = async () => {
            // 更新账户信息
            await api.getAccount();

            // 更新持仓（盈亏、市值等）
            await api.getPositions();

            // 更新所有自选股实时行情
            for (const stock of watchList.value) {
                const rt = await api.getRealtime(stock.stock_code);
                if (rt) {
                    const idx = watchList.value.findIndex(s => s.stock_code === stock.stock_code);
                    if (idx >= 0) {
                        Object.assign(watchList.value[idx], rt);
                    }
                }
            }

            // 更新全市场列表行情
            for (const stock of marketStocks.value) {
                const rt = await api.getRealtime(stock.stock_code);
                if (rt) {
                    const idx = marketStocks.value.findIndex(s => s.stock_code === stock.stock_code);
                    if (idx >= 0) {
                        Object.assign(marketStocks.value[idx], rt);
                    }
                }
            }

            // 更新当前股票行情
            if (currentStock.value) {
                const rt = await api.getRealtime(currentStock.value.stock_code);
                if (rt) {
                    Object.assign(currentStock.value, rt);

                    // 更新列表中的数据
                    const idx = watchList.value.findIndex(s => s.stock_code === currentStock.value.stock_code);
                    if (idx >= 0) {
                        Object.assign(watchList.value[idx], rt);
                    }

                    // 如果是分时图，更新图表数据
                    if (viewMode.value === 'timeline') {
                        await loadTimelineData(currentStock.value.stock_code);
                    }
                }
            }
        };

        // ==================== 生命周期 ====================
        onMounted(async () => {
            // 初始化时间
            updateTime();
            setInterval(updateTime, 1000);

            // 加载初始数据
            await api.getAccount();
            await api.getPositions();
            await api.getSectors();
            await loadMarketStocks();

            // 从数据库加载自选股
            await loadWatchListFromDb();

            // 定时刷新
            setInterval(refreshData, 5000);

            // 响应窗口大小变化
            window.addEventListener('resize', () => {
                if (chart) chart.resize();
            });
        });

        // 从数据库加载自选股
        const loadWatchListFromDb = async () => {
            const dbWatchList = await api.getWatchList();
            for (const item of dbWatchList) {
                const rt = await api.getRealtime(item.stock_code);
                if (rt) {
                    if (!watchList.value.find(s => s.stock_code === item.stock_code)) {
                        watchList.value.push(rt);
                    }
                } else {
                    if (!watchList.value.find(s => s.stock_code === item.stock_code)) {
                        watchList.value.push({
                            stock_code: item.stock_code,
                            stock_name: item.stock_name,
                            current_price: 0,
                            change_pct: 0
                        });
                    }
                }
            }
        };

        // ==================== 返回 ====================
        return {
            // 状态
            currentTime,
            viewMode,
            klineType,
            leftTab,
            accountInfo,
            searchKeyword,
            searchResults,
            watchList,
            marketStocks,
            sectors,
            selectedStock,
            currentStock,
            positions,
            selectedPosition,
            tradeDirection,
            tradeVolume,
            tradePrice,
            isOffHours,
            orderResult,
            chartRef,

            // 计算属性
            estimatedAmount,
            availableToTrade,

            // 方法
            keep2Decimals,
            getPriceClass,
            formatVolume,
            formatAmount,
            selectStock,
            selectSector,
            setViewMode,
            setKlineType,
            searchStock,
            adjustVolume,
            setMaxVolume,
            submitOrder,
            isInWatchList,
            addToWatchList,
            removeFromWatchList
        };
    }
});

// 挂载应用
app.mount('#app');
