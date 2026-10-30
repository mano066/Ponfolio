"""
Ponfolio — 9-Agent Analysis Engine (A+ Grade)

Data Sources:
  - yfinance: t.info (120+ fields), t.history (OHLCV), t.quarterly_income_stmt,
              t.income_stmt, t.cashflow, t.balance_sheet
  - Kite MCP: Real-time LTP/OHLC (if connected, fetched by main.py)
  - DuckDuckGo: Live news headlines

Math Engine (11 functions, ~120 data points):
  calculate_technical_indicators()   → 14 metrics (RSI, MACD, SMA, Bollinger, Volume, S/R)
  calculate_risk_metrics()           → 7 metrics (Volatility, VaR, MaxDD, Beta)
  calculate_dcf()                    → 12 metrics (DCF, Graham, PEG, EV/EBITDA, FCF)
  extract_quarterly_trends()         → 4 metrics (QoQ EPS, Revenue trends)
  calculate_momentum_indicators()    → 6 metrics (Stochastic, Williams %R, ADX, CCI, OBV)
  calculate_ichimoku()               → 9 metrics (Cloud, Tenkan, Kijun, TK Cross)
  calculate_fibonacci_levels()       → 7 metrics (Fib retracement 23.6%-78.6%)
  calculate_sharpe_sortino()         → 5 metrics (Sharpe, Sortino, Calmar ratios)
  calculate_altman_z()               → 2 metrics (Z-Score, bankruptcy zone)
  extract_balance_sheet_health()     → 6 metrics (Current/Quick ratio, Interest Coverage)
  calculate_dupont()                 → 5 metrics (Net Margin × Turnover × Leverage = ROE)

Architecture (9 Agents, 8 LLM calls):
  Agent 1: Data Collection (computes ALL ~120 data points with math)
  Agent 2: Fundamental (P/E, ROE, CAGR, DuPont, Altman Z, Balance Sheet — 26 metrics)
  Agent 3: Technical (RSI, MACD, Stochastic, ADX, Ichimoku, Fibonacci — 25 metrics)
  Agent 4: Sentiment (News + analyst consensus + target upside — 12 metrics)
  Agent 5: Macro (Sector, beta, sensitivity flags, cycle position — 14 metrics)
  Agent 6: Quant (DCF, Graham, PEG, FCF yield, reverse DCF — 18 metrics)
  Agent 7: Risk (Volatility, VaR, Sharpe, Sortino, Calmar, Liquidity — 15 metrics)
  Agent 8: Execution (Fibonacci entries, Ichimoku stops, risk:reward — 10 metrics)
  Agent 9: Master CIO (Weighted scoring, bull/bear case, confidence breakdown)

Key Principle: COMPUTE numbers with math, then ask LLM to INTERPRET with scoring rubrics.
"""

import json
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, Any, List
import yfinance as yf
from duckduckgo_search import DDGS
import aiohttp
import sys

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3.6:35b"


def _safe_print(*args, **kwargs):
    """Print wrapper that handles OSError [Errno 22] on Windows.

    Background threads on Windows can lose their stdout handle, causing
    print(..., flush=True) to raise OSError: [Errno 22] Invalid argument.
    This wrapper catches that silently so logging never crashes the pipeline.
    """
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except OSError:
        # stdout handle is invalid (common in Windows background threads)
        try:
            sys.stderr.write(str(args[0]) + "\n") if args else None
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  LLM CALL
# ═══════════════════════════════════════════════════════════════════

async def async_llm_call(prompt: str) -> dict:
    """Async wrapper for Ollama API call, robustly parsing JSON.
    NOTE: Do NOT use format:'json' — qwen3.6:35b returns empty responses with it.
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            payload = {
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
            }
            async with session.post(OLLAMA_API_URL, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    print(f"Ollama error {response.status}: {text}")
                    return {}
                data = await response.json()
                response_text = data.get("response", "")
                
                if not response_text or not response_text.strip():
                    print(f"[LLM] WARNING: Empty response from model")
                    return {}
                
                # Try direct parse first
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    pass
                
                # Extract JSON from surrounding text/thinking tags
                # Strip <think>...</think> blocks that qwen3 models produce
                import re
                cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
                
                # Try parsing cleaned text
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    pass
                
                # Extract the first JSON object from the text
                start_idx = cleaned.find('{')
                end_idx = cleaned.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = cleaned[start_idx:end_idx+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        print(f"[LLM] Failed to parse extracted JSON: {json_str[:200]}")
                        return {}
                
                print(f"[LLM] No JSON found in response: {cleaned[:200]}")
                return {}
    except Exception as e:
        print(f"LLM Call Exception: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════
#  MATH ENGINE — All computations done here, NOT by LLM
# ═══════════════════════════════════════════════════════════════════

def _safe_round(val, digits=2):
    """Safely round a value, returning None if not a number."""
    if val is None:
        return None
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return None
        return round(v, digits)
    except (TypeError, ValueError):
        return None

def _fmt(val, suffix="", digits=2):
    """Format a value as a string for display, returning None if not available."""
    r = _safe_round(val, digits)
    if r is None:
        return None
    return f"{r}{suffix}"


def _revenue_cagr_line(dcf: dict) -> str:
    """Prompt line for revenue CAGR — labelled correctly (3-Year or 2-Year fallback)."""
    if dcf.get('revenue_cagr_3yr') is not None:
        return f"3-Year Revenue CAGR: {dcf.get('revenue_cagr_3yr')}%"
    if dcf.get('revenue_cagr_2yr') is not None:
        return f"2-Year Revenue CAGR: {dcf.get('revenue_cagr_2yr')}%"
    return "Revenue CAGR: N/A"


def calculate_technical_indicators(df: pd.DataFrame, info: dict = None) -> dict:
    """Computes ALL technical indicators from OHLCV data + info.
    
    Returns 14+ technical metrics including volume analysis, 52-week context,
    and Bollinger Bands.
    """
    if df.empty or len(df) < 14:
        return {}
    
    close = df['Close']
    volume = df['Volume'] if 'Volume' in df.columns else pd.Series(dtype=float)
    high = df['High'] if 'High' in df.columns else close
    low = df['Low'] if 'Low' in df.columns else close
    
    # ── RSI (14) ──
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    # ── MACD ──
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    current_macd = macd.iloc[-1]
    current_signal = signal.iloc[-1]
    macd_crossover = "Bullish" if current_macd > current_signal else "Bearish"
    
    # ── SMA ──
    sma_20 = close.rolling(window=20).mean().iloc[-1] if len(close) >= 20 else None
    sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None
    sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
    
    # ── Bollinger Bands (20, 2) ──
    bb_middle = sma_20
    bb_std = close.rolling(window=20).std().iloc[-1] if len(close) >= 20 else None
    bb_upper = _safe_round(bb_middle + 2 * bb_std) if bb_middle and bb_std else None
    bb_lower = _safe_round(bb_middle - 2 * bb_std) if bb_middle and bb_std else None
    bb_width = _safe_round((bb_upper - bb_lower) / bb_middle * 100) if bb_upper and bb_lower and bb_middle else None
    
    # ── Volume Analysis (#21-#24) ──
    current_volume = int(volume.iloc[-1]) if not volume.empty and not pd.isna(volume.iloc[-1]) else None
    avg_volume_20 = int(volume.rolling(window=20).mean().iloc[-1]) if len(volume) >= 20 and not pd.isna(volume.rolling(window=20).mean().iloc[-1]) else None
    volume_ratio = _safe_round(current_volume / avg_volume_20, 2) if current_volume and avg_volume_20 and avg_volume_20 > 0 else None
    volume_signal = None
    if volume_ratio:
        if volume_ratio > 2.0:
            volume_signal = "Very High (>2x avg — institutional activity)"
        elif volume_ratio > 1.5:
            volume_signal = "High (1.5x avg)"
        elif volume_ratio > 0.7:
            volume_signal = "Normal"
        else:
            volume_signal = "Low (below avg — low conviction)"
    
    # ── Volume-Price Divergence (#30) ──
    vp_divergence = None
    if len(close) >= 20 and not volume.empty and len(volume) >= 20:
        price_trend = close.iloc[-1] - close.iloc[-20]
        vol_trend = volume.iloc[-5:].mean() - volume.iloc[-20:-15].mean()
        if price_trend > 0 and vol_trend < 0:
            vp_divergence = "Bearish Divergence (price up, volume declining — weak rally)"
        elif price_trend < 0 and vol_trend > 0:
            vp_divergence = "Bullish Divergence (price down, volume rising — accumulation)"
        elif price_trend > 0 and vol_trend > 0:
            vp_divergence = "Confirmed Uptrend (price and volume rising)"
        else:
            vp_divergence = "Confirmed Downtrend (price and volume falling)"
    
    # ── 52-Week Context from info (#24-#27) ──
    fifty_two_high = info.get('fiftyTwoWeekHigh') if info else None
    fifty_two_low = info.get('fiftyTwoWeekLow') if info else None
    pct_from_52w_high = None
    if info and info.get('fiftyTwoWeekHighChangePercent'):
        pct_from_52w_high = _safe_round(info['fiftyTwoWeekHighChangePercent'] * 100)
    all_time_high = info.get('allTimeHigh') if info else None
    
    # ── Trend Detection ──
    current_price = close.iloc[-1]
    trend = "Neutral"
    if sma_50 and sma_200:
        if current_price > sma_50 > sma_200:
            trend = "Strong Uptrend"
        elif current_price > sma_50:
            trend = "Uptrend"
        elif current_price < sma_50 < sma_200:
            trend = "Strong Downtrend"
        elif current_price < sma_50:
            trend = "Downtrend"
    
    # ── Momentum ──
    momentum = "Neutral"
    if current_rsi > 70:
        momentum = "Overbought"
    elif current_rsi < 30:
        momentum = "Oversold"
    elif current_rsi > 55:
        momentum = "Bullish"
    elif current_rsi < 45:
        momentum = "Bearish"
    
    # ── Support / Resistance from Pivot Points (#63-#64) ──
    recent_high = high.iloc[-20:].max() if len(high) >= 20 else high.max()
    recent_low = low.iloc[-20:].min() if len(low) >= 20 else low.min()
    pivot = (recent_high + recent_low + current_price) / 3
    support_1 = _safe_round(2 * pivot - recent_high)
    resistance_1 = _safe_round(2 * pivot - recent_low)
    
    return {
        "current_price": round(float(current_price), 2),
        "rsi_14": round(float(current_rsi), 2),
        "momentum": momentum,
        "macd": _safe_round(current_macd),
        "macd_signal": _safe_round(current_signal),
        "macd_histogram": _safe_round(histogram.iloc[-1]),
        "macd_crossover": macd_crossover,
        "sma_50": _safe_round(sma_50),
        "sma_200": _safe_round(sma_200),
        "trend": trend,
        # Bollinger (#29)
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width_pct": bb_width,
        # Volume (#21-#24)
        "current_volume": current_volume,
        "avg_volume_20d": avg_volume_20,
        "volume_ratio": volume_ratio,
        "volume_signal": volume_signal,
        "volume_price_divergence": vp_divergence,
        "avg_volume_10d": info.get('averageDailyVolume10Day') if info else None,
        "avg_volume_3m": info.get('averageVolume') if info else None,
        # 52-Week (#24-#27)
        "fifty_two_week_high": _safe_round(fifty_two_high),
        "fifty_two_week_low": _safe_round(fifty_two_low),
        "pct_from_52w_high": pct_from_52w_high,
        "all_time_high": _safe_round(all_time_high),
        "fifty_day_avg": _safe_round(info.get('fiftyDayAverage') if info else sma_50),
        "two_hundred_day_avg": _safe_round(info.get('twoHundredDayAverage') if info else sma_200),
        # Computed S/R (#63-#64)
        "support_level": support_1,
        "resistance_level": resistance_1,
    }


def calculate_risk_metrics(df: pd.DataFrame, info: dict = None) -> dict:
    """Computes risk metrics mathematically (#55-#61).
    
    Historical volatility, max drawdown, VaR — all from actual data.
    """
    if df.empty or len(df) < 14:
        return {}
    
    close = df['Close']
    daily_returns = close.pct_change().dropna()
    
    if daily_returns.empty:
        return {}
    
    # ── Historical Volatility (#57) ──
    daily_vol = daily_returns.std()
    annual_vol = daily_vol * np.sqrt(252)
    
    # ── Max Drawdown (#58) ──
    cumulative = (1 + daily_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min() * 100
    
    # ── Value at Risk 95% (#59) ──
    var_95 = np.percentile(daily_returns, 5) * 100
    # ── Value at Risk 99% — real empirical 1st percentile (matches var_95's 5th) ──
    var_99 = np.percentile(daily_returns, 1) * 100
    
    # ── Risk Level ──
    risk_level = "Medium"
    if annual_vol > 0.45:
        risk_level = "Very High"
    elif annual_vol > 0.35:
        risk_level = "High"
    elif annual_vol > 0.22:
        risk_level = "Medium"
    else:
        risk_level = "Low"
    
    vol_profile = "Medium"
    if annual_vol > 0.40:
        vol_profile = "Very High"
    elif annual_vol > 0.30:
        vol_profile = "High"
    elif annual_vol > 0.18:
        vol_profile = "Medium"
    else:
        vol_profile = "Low"
    
    return {
        "annual_volatility_pct": _safe_round(annual_vol * 100, 1),
        "daily_volatility_pct": _safe_round(daily_vol * 100, 2),
        "max_drawdown_estimate_pct": _safe_round(abs(max_drawdown), 1),
        "var_95_daily_pct": _safe_round(abs(var_95), 2),
        "var_99_daily_pct": _safe_round(abs(var_99), 2),
        "risk_level": risk_level,
        "volatility_profile": vol_profile,
        "beta": _safe_round(info.get('beta')) if info else None,
        "current_ratio": _safe_round(info.get('currentRatio')) if info else None,
        "quick_ratio": _safe_round(info.get('quickRatio')) if info else None,
    }


def calculate_dcf(info: dict, cashflow_df: pd.DataFrame = None, income_df: pd.DataFrame = None) -> dict:
    """Computes real DCF valuation mathematically (#31-#42).
    
    Uses actual FCF, revenue growth, shares outstanding — NOT LLM guessing.
    """
    result = {
        "dcf_intrinsic_value": None,
        "graham_number": None,
        "margin_of_safety_pct": None,
        "fcf_ttm": None,
        "fcf_history": None,
        "revenue_cagr_3yr": None,
        "revenue_cagr_2yr": None,
        "peg_ratio": None,
        "peg_computed": None,
        "peg_source": None,
        "ev_ebitda": None,
        "total_debt": None,
        "total_cash": None,
        "net_debt": None,
        "enterprise_value": None,
    }
    
    if not info:
        return result
    
    current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
    shares = info.get('sharesOutstanding', 0)
    
    # ── Graham Number (#36) ──
    eps = info.get('trailingEps')
    bvps = info.get('bookValue')
    if eps and bvps and eps > 0 and bvps > 0:
        result["graham_number"] = round((22.5 * eps * bvps) ** 0.5, 2)
    
    # ── PEG Ratio (#37) ──
    # yfinance pegRatio is often None/stale for Indian tickers. Fall back to a
    # computed PEG = trailingPE / (earningsGrowth * 100) when it's missing.
    peg_yf = info.get('pegRatio')
    if peg_yf is not None:
        result["peg_ratio"] = _safe_round(peg_yf)
        result["peg_source"] = "yfinance"
    else:
        trailing_pe = info.get('trailingPE')
        earnings_growth = info.get('earningsGrowth')
        if trailing_pe and earnings_growth and earnings_growth != 0:
            growth_pct = earnings_growth * 100
            if growth_pct != 0:
                result["peg_computed"] = _safe_round(trailing_pe / growth_pct)
                result["peg_ratio"] = result["peg_computed"]
                result["peg_source"] = "computed"
        # If neither available, peg_ratio / peg_source stay None
    
    # ── EV/EBITDA (#42) ──
    result["ev_ebitda"] = _safe_round(info.get('enterpriseToEbitda'))
    
    # ── Debt & Cash (#39-#41) ──
    result["total_debt"] = info.get('totalDebt')
    result["total_cash"] = info.get('totalCash')
    if result["total_debt"] and result["total_cash"]:
        result["net_debt"] = result["total_debt"] - result["total_cash"]
    result["enterprise_value"] = info.get('enterpriseValue')
    
    # ── FCF from info (#31) ──
    fcf_ttm = info.get('freeCashflow')
    result["fcf_ttm"] = fcf_ttm
    
    # ── FCF History from cashflow (#32) ──
    if cashflow_df is not None and not cashflow_df.empty and 'Free Cash Flow' in cashflow_df.index:
        fcf_series = cashflow_df.loc['Free Cash Flow'].dropna()
        result["fcf_history"] = {str(d.date()): _safe_round(float(v) / 1e9, 1) for d, v in fcf_series.items()}
    
    # ── Revenue CAGR 3yr (#8) ──
    # True 3-year CAGR needs 4 annual points (n=3 periods → exponent 1/3).
    # yfinance income_stmt normally returns 4 annual columns. Fall back to a
    # 2-year CAGR (3 points, exponent 1/2) only if 4 points aren't available.
    if income_df is not None and not income_df.empty and 'Total Revenue' in income_df.index:
        rev_series = income_df.loc['Total Revenue'].dropna().sort_index()
        if len(rev_series) >= 4:
            rev_start = float(rev_series.iloc[-4])
            rev_end = float(rev_series.iloc[-1])
            if rev_start > 0 and rev_end > 0:
                cagr = (rev_end / rev_start) ** (1 / 3) - 1
                result["revenue_cagr_3yr"] = _safe_round(cagr * 100, 1)
        elif len(rev_series) >= 3:
            rev_start = float(rev_series.iloc[-3])
            rev_end = float(rev_series.iloc[-1])
            if rev_start > 0 and rev_end > 0:
                cagr = (rev_end / rev_start) ** (1 / 2) - 1
                result["revenue_cagr_2yr"] = _safe_round(cagr * 100, 1)
    
    # ── Real DCF Calculation (#31) ──
    if fcf_ttm and fcf_ttm > 0 and shares and shares > 0:
        growth_rate = 0.10  # default 10%
        cagr_for_growth = result["revenue_cagr_3yr"] if result["revenue_cagr_3yr"] is not None else result["revenue_cagr_2yr"]
        if cagr_for_growth:
            growth_rate = min(cagr_for_growth / 100, 0.15)
            growth_rate = max(growth_rate, 0.03)

        discount_rate = 0.12  # 12% for India equity
        terminal_growth = 0.04  # 4% long-term GDP
        years = 10

        pv_fcf = sum(
            fcf_ttm * (1 + growth_rate) ** i / (1 + discount_rate) ** i
            for i in range(1, years + 1)
        )
        terminal_fcf = fcf_ttm * (1 + growth_rate) ** years
        terminal_value = terminal_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)
        pv_terminal = terminal_value / (1 + discount_rate) ** years
        # Enterprise value → equity value via net-debt bridge (missing debt/cash = 0)
        enterprise_val = pv_fcf + pv_terminal
        total_debt = info.get('totalDebt') or 0
        cash = info.get('totalCash') or info.get('cash') or 0
        net_debt = total_debt - cash
        equity_value = enterprise_val - net_debt
        intrinsic = equity_value / shares
        result["dcf_intrinsic_value"] = _safe_round(intrinsic, 2)
        
        if current_price and current_price > 0 and result["dcf_intrinsic_value"]:
            mos = (result["dcf_intrinsic_value"] - current_price) / result["dcf_intrinsic_value"] * 100
            result["margin_of_safety_pct"] = _safe_round(mos, 1)
    
    return result


def extract_quarterly_trends(quarterly_income_df: pd.DataFrame = None) -> dict:
    """Extract QoQ trends from quarterly income statement (#9, #10)."""
    result = {
        "qoq_eps": [],
        "qoq_revenue": [],
        "eps_trend": None,
        "revenue_trend": None,
    }
    
    if quarterly_income_df is None or quarterly_income_df.empty:
        return result
    
    if 'Diluted EPS' in quarterly_income_df.index:
        eps_series = quarterly_income_df.loc['Diluted EPS'].dropna().sort_index()
        result["qoq_eps"] = [
            {"quarter": str(d.date()), "eps": _safe_round(float(v), 2)}
            for d, v in eps_series.items()
        ]
        if len(eps_series) >= 2:
            recent = float(eps_series.iloc[-1])
            prev = float(eps_series.iloc[-2])
            if recent > prev * 1.05:
                result["eps_trend"] = "Growing"
            elif recent < prev * 0.95:
                result["eps_trend"] = "Declining"
            else:
                result["eps_trend"] = "Stable"
    
    if 'Total Revenue' in quarterly_income_df.index:
        rev_series = quarterly_income_df.loc['Total Revenue'].dropna().sort_index()
        result["qoq_revenue"] = [
            {"quarter": str(d.date()), "revenue_cr": _safe_round(float(v) / 1e7, 0)}
            for d, v in rev_series.items()
        ]
        if len(rev_series) >= 2:
            recent = float(rev_series.iloc[-1])
            prev = float(rev_series.iloc[-2])
            if recent > prev * 1.05:
                result["revenue_trend"] = "Growing"
            elif recent < prev * 0.95:
                result["revenue_trend"] = "Declining"
            else:
                result["revenue_trend"] = "Stable"
    
    return result


def calculate_momentum_indicators(df: pd.DataFrame) -> dict:
    """Computes advanced momentum indicators: Stochastic, Williams %R, ADX, CCI, OBV.
    
    These complement RSI/MACD by confirming or contradicting their signals.
    """
    if df.empty or len(df) < 20:
        return {}
    
    close = df['Close']
    high = df['High'] if 'High' in df.columns else close
    low = df['Low'] if 'Low' in df.columns else close
    volume = df['Volume'] if 'Volume' in df.columns else pd.Series(dtype=float)
    
    result = {}
    
    # ── Stochastic %K/%D (14,3) ──
    try:
        low_14 = low.rolling(window=14).min()
        high_14 = high.rolling(window=14).max()
        denom = high_14 - low_14
        denom = denom.replace(0, np.nan)
        stoch_k = ((close - low_14) / denom) * 100
        stoch_d = stoch_k.rolling(window=3).mean()
        result["stochastic_k"] = _safe_round(stoch_k.iloc[-1], 1)
        result["stochastic_d"] = _safe_round(stoch_d.iloc[-1], 1)
        k_val = result["stochastic_k"]
        if k_val is not None:
            if k_val > 80:
                result["stochastic_signal"] = "Overbought"
            elif k_val < 20:
                result["stochastic_signal"] = "Oversold"
            else:
                result["stochastic_signal"] = "Neutral"
    except Exception:
        pass
    
    # ── Williams %R (14) ──
    try:
        highest_high = high.rolling(window=14).max()
        lowest_low = low.rolling(window=14).min()
        denom = highest_high - lowest_low
        denom = denom.replace(0, np.nan)
        williams_r = ((highest_high - close) / denom) * -100
        result["williams_r"] = _safe_round(williams_r.iloc[-1], 1)
        wr = result["williams_r"]
        if wr is not None:
            if wr > -20:
                result["williams_signal"] = "Overbought"
            elif wr < -80:
                result["williams_signal"] = "Oversold"
            else:
                result["williams_signal"] = "Neutral"
    except Exception:
        pass
    
    # ── ADX (14) — Average Directional Index ──
    try:
        if len(df) >= 28:
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = tr.rolling(window=14).mean()
            
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
            
            plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr_14)
            minus_di = 100 * (minus_dm.rolling(window=14).mean() / atr_14)
            
            dx_denom = (plus_di + minus_di).replace(0, np.nan)
            dx = ((plus_di - minus_di).abs() / dx_denom) * 100
            adx = dx.rolling(window=14).mean()
            
            result["adx"] = _safe_round(adx.iloc[-1], 1)
            result["plus_di"] = _safe_round(plus_di.iloc[-1], 1)
            result["minus_di"] = _safe_round(minus_di.iloc[-1], 1)
            adx_val = result["adx"]
            if adx_val is not None:
                if adx_val > 40:
                    result["adx_signal"] = "Very Strong Trend"
                elif adx_val > 25:
                    result["adx_signal"] = "Strong Trend"
                elif adx_val > 20:
                    result["adx_signal"] = "Emerging Trend"
                else:
                    result["adx_signal"] = "No Clear Trend (Range-bound)"
    except Exception:
        pass
    
    # ── CCI (20) — Commodity Channel Index ──
    try:
        tp = (high + low + close) / 3
        tp_sma = tp.rolling(window=20).mean()
        tp_mad = tp.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        tp_mad = tp_mad.replace(0, np.nan)
        cci = (tp - tp_sma) / (0.015 * tp_mad)
        result["cci"] = _safe_round(cci.iloc[-1], 1)
        cci_val = result["cci"]
        if cci_val is not None:
            if cci_val > 100:
                result["cci_signal"] = "Overbought"
            elif cci_val < -100:
                result["cci_signal"] = "Oversold"
            else:
                result["cci_signal"] = "Normal"
    except Exception:
        pass
    
    # ── OBV — On-Balance Volume ──
    try:
        if not volume.empty and len(volume) >= 20:
            obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
            obv_sma_20 = obv.rolling(window=20).mean()
            result["obv_current"] = int(obv.iloc[-1]) if not pd.isna(obv.iloc[-1]) else None
            result["obv_sma_20"] = int(obv_sma_20.iloc[-1]) if not pd.isna(obv_sma_20.iloc[-1]) else None
            if result["obv_current"] is not None and result["obv_sma_20"] is not None:
                if result["obv_current"] > result["obv_sma_20"] * 1.05:
                    result["obv_signal"] = "Accumulation (bullish)"
                elif result["obv_current"] < result["obv_sma_20"] * 0.95:
                    result["obv_signal"] = "Distribution (bearish)"
                else:
                    result["obv_signal"] = "Neutral"
    except Exception:
        pass
    
    return result


def calculate_ichimoku(df: pd.DataFrame) -> dict:
    """Computes Ichimoku Cloud components for institutional-grade trend analysis.
    
    Requires at least 52 periods of data for the cloud to form properly.
    """
    if df.empty or len(df) < 52:
        return {}
    
    high = df['High'] if 'High' in df.columns else df['Close']
    low = df['Low'] if 'Low' in df.columns else df['Close']
    close = df['Close']
    
    try:
        # Tenkan-sen (Conversion Line) — 9-period midpoint
        tenkan = (high.rolling(window=9).max() + low.rolling(window=9).min()) / 2
        # Kijun-sen (Base Line) — 26-period midpoint
        kijun = (high.rolling(window=26).max() + low.rolling(window=26).min()) / 2
        # Senkou Span A (Leading Span A) — midpoint of Tenkan + Kijun
        span_a = ((tenkan + kijun) / 2)
        # Senkou Span B (Leading Span B) — 52-period midpoint
        span_b = (high.rolling(window=52).max() + low.rolling(window=52).min()) / 2
        
        current_price = close.iloc[-1]
        tenkan_val = _safe_round(tenkan.iloc[-1])
        kijun_val = _safe_round(kijun.iloc[-1])
        span_a_val = _safe_round(span_a.iloc[-1])
        span_b_val = _safe_round(span_b.iloc[-1])
        
        # Cloud status
        cloud_top = max(span_a_val or 0, span_b_val or 0)
        cloud_bottom = min(span_a_val or 0, span_b_val or 0)
        
        if current_price > cloud_top:
            cloud_status = "Above Cloud (Bullish)"
        elif current_price < cloud_bottom:
            cloud_status = "Below Cloud (Bearish)"
        else:
            cloud_status = "Inside Cloud (Uncertain)"
        
        # TK Cross
        tk_cross = "Bullish" if tenkan_val and kijun_val and tenkan_val > kijun_val else "Bearish"
        
        # Cloud color (future cloud direction)
        cloud_color = "Bullish (Green)" if span_a_val and span_b_val and span_a_val > span_b_val else "Bearish (Red)"
        
        return {
            "tenkan_sen": tenkan_val,
            "kijun_sen": kijun_val,
            "senkou_span_a": span_a_val,
            "senkou_span_b": span_b_val,
            "cloud_top": _safe_round(cloud_top),
            "cloud_bottom": _safe_round(cloud_bottom),
            "cloud_status": cloud_status,
            "tk_cross": tk_cross,
            "cloud_color": cloud_color,
        }
    except Exception:
        return {}


def calculate_fibonacci_levels(info: dict = None, df: pd.DataFrame = None) -> dict:
    """Computes Fibonacci retracement levels from 52-week high/low.
    
    These are the exact price levels where institutional traders place orders.
    """
    high_52w = None
    low_52w = None
    
    if info:
        high_52w = info.get('fiftyTwoWeekHigh') or info.get('year_high')
        low_52w = info.get('fiftyTwoWeekLow') or info.get('year_low')
    
    # Fallback to computed from history
    if (high_52w is None or low_52w is None) and df is not None and not df.empty:
        high_52w = high_52w or float(df['High'].max()) if 'High' in df.columns else float(df['Close'].max())
        low_52w = low_52w or float(df['Low'].min()) if 'Low' in df.columns else float(df['Close'].min())
    
    if high_52w is None or low_52w is None or high_52w <= low_52w:
        return {}
    
    high_52w = float(high_52w)
    low_52w = float(low_52w)
    range_val = high_52w - low_52w
    
    return {
        "fib_236": _safe_round(high_52w - range_val * 0.236),
        "fib_382": _safe_round(high_52w - range_val * 0.382),
        "fib_500": _safe_round(high_52w - range_val * 0.500),
        "fib_618": _safe_round(high_52w - range_val * 0.618),
        "fib_786": _safe_round(high_52w - range_val * 0.786),
        "fib_high": _safe_round(high_52w),
        "fib_low": _safe_round(low_52w),
    }


def calculate_sharpe_sortino(df: pd.DataFrame, risk_free_rate: float = 0.07) -> dict:
    """Computes Sharpe and Sortino ratios for risk-adjusted return analysis.
    
    Uses 7% as India risk-free rate (10Y government bond approximate).
    """
    if df.empty or len(df) < 30:
        return {}
    
    close = df['Close']
    daily_returns = close.pct_change().dropna()
    
    if daily_returns.empty or daily_returns.std() == 0:
        return {}
    
    try:
        daily_rf = risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        
        # Sharpe Ratio (annualized)
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
        
        # Sortino Ratio (annualized) — only downside deviation
        downside_returns = excess_returns[excess_returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino = (excess_returns.mean() / downside_returns.std()) * np.sqrt(252)
        else:
            sortino = None
        
        # Calmar Ratio (annualized return / max drawdown)
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_dd = abs(drawdown.min())
        annual_return = (cumulative.iloc[-1] ** (252 / len(daily_returns))) - 1
        calmar = (annual_return / max_dd) if max_dd > 0 else None
        
        # Interpret
        sharpe_val = _safe_round(sharpe, 2)
        if sharpe_val is not None:
            if sharpe_val >= 2.0:
                sharpe_rating = "Excellent"
            elif sharpe_val >= 1.0:
                sharpe_rating = "Good"
            elif sharpe_val >= 0.5:
                sharpe_rating = "Mediocre"
            else:
                sharpe_rating = "Poor"
        else:
            sharpe_rating = None
        
        return {
            "sharpe_ratio": sharpe_val,
            "sharpe_rating": sharpe_rating,
            "sortino_ratio": _safe_round(sortino, 2),
            "calmar_ratio": _safe_round(calmar, 2),
            "annualized_return_pct": _safe_round(annual_return * 100, 1),
        }
    except Exception:
        return {}


def calculate_altman_z(info: dict, balance_sheet: pd.DataFrame = None,
                       income_stmt: pd.DataFrame = None) -> dict:
    """Computes Altman Z-Score — a bankruptcy predictor combining 5 ratios.
    
    Z > 2.99 = Safe, 1.81-2.99 = Grey Zone, < 1.81 = Distress.
    """
    try:
        market_cap = info.get('marketCap', 0) or 0

        # Classic Altman Z (manufacturing model) is invalid for banks/NBFCs —
        # their balance sheets (deposits, loans) break the working-capital and
        # asset-turnover assumptions. Flag as not applicable rather than mislead.
        sector = (info.get('sector') or '').lower()
        industry = (info.get('industry') or '').lower()
        is_financial = any(kw in sector or kw in industry for kw in ('bank', 'financial'))
        if is_financial:
            return {
                "altman_z_score": None,
                "altman_zone": None,
                "altman_applicable": False,
            }

        # Try to get data from financial statements
        total_assets = None
        total_liabilities = None
        current_assets = None
        current_liabilities = None
        retained_earnings = None
        ebit = None
        revenue = None
        
        if balance_sheet is not None and not balance_sheet.empty:
            latest = balance_sheet.iloc[:, 0]  # Most recent column
            total_assets = _get_stmt_value(latest, ['Total Assets'])
            total_liabilities = _get_stmt_value(latest, ['Total Liabilities Net Minority Interest', 'Total Liabilities'])
            current_assets = _get_stmt_value(latest, ['Current Assets'])
            current_liabilities = _get_stmt_value(latest, ['Current Liabilities'])
            retained_earnings = _get_stmt_value(latest, ['Retained Earnings'])
        
        if income_stmt is not None and not income_stmt.empty:
            latest_income = income_stmt.iloc[:, 0]
            ebit = _get_stmt_value(latest_income, ['EBIT', 'Operating Income'])
            revenue = _get_stmt_value(latest_income, ['Total Revenue'])
        
        # Fallback to info dict
        if total_assets is None:
            total_assets = info.get('totalAssets', 0) or 0
        if total_liabilities is None:
            total_liabilities = (info.get('totalDebt', 0) or 0)
        if revenue is None:
            revenue = info.get('totalRevenue', 0) or 0
        if ebit is None:
            # Use operating income / EBIT — NOT ebitda (EBITDA inflates the 3.3*C term).
            # yfinance has no direct operating-income field in info, so derive it from
            # operating margin × revenue when the income statement is unavailable.
            op_margin = info.get('operatingMargins')
            if op_margin is not None and revenue:
                ebit = op_margin * revenue
            else:
                ebit = 0
        
        if not total_assets or total_assets <= 0:
            return {}
        
        working_capital = (current_assets or 0) - (current_liabilities or 0)
        
        # Altman Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        A = working_capital / total_assets
        B = (retained_earnings or 0) / total_assets
        C = (ebit or 0) / total_assets
        D = market_cap / total_liabilities if total_liabilities and total_liabilities > 0 else 0
        E = (revenue or 0) / total_assets
        
        z_score = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
        
        if z_score > 2.99:
            zone = "Safe Zone"
        elif z_score > 1.81:
            zone = "Grey Zone (Caution)"
        else:
            zone = "Distress Zone (Bankruptcy Risk)"
        
        return {
            "altman_z_score": _safe_round(z_score, 2),
            "altman_zone": zone,
            "altman_applicable": True,
        }
    except Exception:
        return {}


def _get_stmt_value(series: pd.Series, possible_keys: list):
    """Helper: get first matching value from a financial statement row."""
    for key in possible_keys:
        if key in series.index:
            val = series[key]
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                return float(val)
    return None


def calculate_roce(info: dict, balance_sheet: pd.DataFrame = None,
                   income_stmt: pd.DataFrame = None) -> dict:
    """Computes TRUE ROCE = EBIT / (Total Assets − Current Liabilities).

    Uses the same income statement (EBIT / Operating Income) and balance sheet
    (Total Assets, Current Liabilities) as the Altman Z-Score.

    If true-ROCE inputs are unavailable, falls back to returnOnAssets emitted as
    `roa` (NOT roce), and sets roce=None so the metric is never mislabeled.
    Always returns both `roce` (true, or None) and `roa`.
    """
    result = {"roce": None, "roa": None}
    try:
        # ROA fallback from info (kept for reference, correctly named)
        roa_raw = info.get('returnOnAssets')
        if roa_raw is not None:
            result["roa"] = _safe_round(roa_raw * 100 if abs(roa_raw) < 1 else roa_raw, 1)

        ebit = None
        total_assets = None
        current_liabilities = None

        if income_stmt is not None and not income_stmt.empty:
            latest_income = income_stmt.iloc[:, 0]
            ebit = _get_stmt_value(latest_income, ['EBIT', 'Operating Income'])
        if balance_sheet is not None and not balance_sheet.empty:
            latest_bs = balance_sheet.iloc[:, 0]
            total_assets = _get_stmt_value(latest_bs, ['Total Assets'])
            current_liabilities = _get_stmt_value(latest_bs, ['Current Liabilities'])

        if ebit is not None and total_assets is not None and current_liabilities is not None:
            capital_employed = total_assets - current_liabilities
            if capital_employed and capital_employed > 0:
                result["roce"] = _safe_round((ebit / capital_employed) * 100, 1)
    except Exception:
        pass
    return result


def extract_balance_sheet_health(info: dict, balance_sheet: pd.DataFrame = None,
                                  income_stmt: pd.DataFrame = None) -> dict:
    """Extracts balance sheet health metrics directly from financial statements.
    
    More reliable than info dict which often has None values.
    """
    result = {
        "current_ratio": None,
        "quick_ratio": None,
        "interest_coverage": None,
        "working_capital_cr": None,
        "asset_turnover": None,
        "debt_to_assets": None,
    }
    
    try:
        current_assets = None
        current_liabilities = None
        inventory = None
        total_assets = None
        total_debt = None
        interest_expense = None
        ebit = None
        revenue = None
        
        if balance_sheet is not None and not balance_sheet.empty:
            latest = balance_sheet.iloc[:, 0]
            current_assets = _get_stmt_value(latest, ['Current Assets'])
            current_liabilities = _get_stmt_value(latest, ['Current Liabilities'])
            inventory = _get_stmt_value(latest, ['Inventory'])
            total_assets = _get_stmt_value(latest, ['Total Assets'])
            total_debt = _get_stmt_value(latest, ['Total Debt', 'Long Term Debt And Capital Lease Obligation'])
        
        if income_stmt is not None and not income_stmt.empty:
            latest_income = income_stmt.iloc[:, 0]
            interest_expense = _get_stmt_value(latest_income, ['Interest Expense', 'Interest Expense Non Operating'])
            ebit = _get_stmt_value(latest_income, ['EBIT', 'Operating Income'])
            revenue = _get_stmt_value(latest_income, ['Total Revenue'])
        
        # Fallback to info
        if current_assets is None:
            cr = info.get('currentRatio')
            cl = info.get('totalCurrentLiabilities')
            if cr and cl:
                current_assets = cr * cl
                current_liabilities = cl
        
        # Current Ratio
        if current_assets and current_liabilities and current_liabilities > 0:
            result["current_ratio"] = _safe_round(current_assets / current_liabilities, 2)
        elif info.get('currentRatio'):
            result["current_ratio"] = _safe_round(info['currentRatio'], 2)
        
        # Quick Ratio
        if current_assets and current_liabilities and current_liabilities > 0:
            inv = inventory or 0
            result["quick_ratio"] = _safe_round((current_assets - inv) / current_liabilities, 2)
        elif info.get('quickRatio'):
            result["quick_ratio"] = _safe_round(info['quickRatio'], 2)
        
        # Interest Coverage
        if ebit and interest_expense and interest_expense > 0:
            result["interest_coverage"] = _safe_round(ebit / interest_expense, 1)
        
        # Working Capital (in Cr)
        if current_assets and current_liabilities:
            wc = current_assets - current_liabilities
            result["working_capital_cr"] = _safe_round(wc / 1e7, 0)
        
        # Asset Turnover
        if revenue and total_assets and total_assets > 0:
            result["asset_turnover"] = _safe_round(revenue / total_assets, 2)
        
        # Debt to Assets
        if total_debt and total_assets and total_assets > 0:
            result["debt_to_assets"] = _safe_round(total_debt / total_assets * 100, 1)
        
    except Exception:
        pass
    
    return result


def calculate_dupont(info: dict, income_stmt: pd.DataFrame = None,
                     balance_sheet: pd.DataFrame = None) -> dict:
    """DuPont Decomposition: ROE = Net Margin × Asset Turnover × Equity Multiplier.
    
    Reveals whether ROE is driven by profitability, efficiency, or leverage.
    """
    try:
        net_income = None
        revenue = None
        total_assets = None
        total_equity = None
        
        if income_stmt is not None and not income_stmt.empty:
            latest = income_stmt.iloc[:, 0]
            net_income = _get_stmt_value(latest, ['Net Income', 'Net Income Common Stockholders'])
            revenue = _get_stmt_value(latest, ['Total Revenue'])
        
        if balance_sheet is not None and not balance_sheet.empty:
            latest_bs = balance_sheet.iloc[:, 0]
            total_assets = _get_stmt_value(latest_bs, ['Total Assets'])
            total_equity = _get_stmt_value(latest_bs, ['Stockholders Equity', 'Total Equity Gross Minority Interest'])
        
        # Fallback to info
        if net_income is None:
            net_income = info.get('netIncomeToCommon')
        if revenue is None:
            revenue = info.get('totalRevenue')
        if total_assets is None:
            total_assets = info.get('totalAssets')
        
        if not all([net_income, revenue, total_assets, total_equity]):
            return {}
        if revenue <= 0 or total_assets <= 0 or total_equity <= 0:
            return {}
        
        net_margin = net_income / revenue
        asset_turnover = revenue / total_assets
        equity_multiplier = total_assets / total_equity
        computed_roe = net_margin * asset_turnover * equity_multiplier
        
        # Identify the primary ROE driver
        if equity_multiplier > 3.0:
            roe_driver = "Leverage-driven (risky)"
        elif net_margin > 0.15:
            roe_driver = "Profit-driven (healthy)"
        elif asset_turnover > 1.5:
            roe_driver = "Efficiency-driven (healthy)"
        else:
            roe_driver = "Balanced"
        
        return {
            "dupont_net_margin_pct": _safe_round(net_margin * 100, 1),
            "dupont_asset_turnover": _safe_round(asset_turnover, 2),
            "dupont_equity_multiplier": _safe_round(equity_multiplier, 2),
            "dupont_computed_roe_pct": _safe_round(computed_roe * 100, 1),
            "dupont_roe_driver": roe_driver,
        }
    except Exception:
        return {}


async def fetch_news_ddgs(ticker: str) -> List[Dict]:
    """Fetch live news using duckduckgo_search."""
    try:
        ddgs = DDGS()
        results = list(ddgs.news(f"{ticker} stock NSE India", max_results=5))
        return [{"title": r.get("title", ""), "date": r.get("date", ""), "source": r.get("source", "")} for r in results]
    except Exception as e:
        print(f"News fetch error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  9 AGENTS — Each now uses full computed data + portfolio context
# ═══════════════════════════════════════════════════════════════════

def _portfolio_prompt_section(data_ctx: dict) -> str:
    """Generate a prompt section describing the user's personal position."""
    pf = data_ctx.get("portfolio", {})
    if not pf.get("is_held"):
        return "\n    USER'S POSITION: Not currently held in portfolio.\n"
    return f"""
    USER'S POSITION (CRITICAL — personalize your advice):
    Shares Held: {pf.get('shares', 0)}
    Avg Cost: ₹{pf.get('avg_cost', 0)}
    Invested: ₹{pf.get('invested', 0):,.0f}
    Current Value: ₹{pf.get('current_value', 0):,.0f}
    P&L: ₹{pf.get('pnl', 0):,.0f} ({pf.get('pnl_pct', 0):+.1f}%)
    Portfolio Weight: {pf.get('portfolio_weight_pct', 0)}%
    → Tailor your analysis to THIS investor's cost basis and position size.
"""

async def run_data_agent(symbol: str, info: dict, hist: pd.DataFrame, news_data: list, sector: str,
                         ticker_obj=None, portfolio_ctx: dict = None) -> dict:
    """1. Data Collection Agent — extracts ALL ~120 data points.
    
    Accepts optional ticker_obj to fetch quarterly/cashflow/balance_sheet data.
    Backward-compatible: works without ticker_obj (just skips financial statements).
    """
    # Compute technical indicators with full volume + 52W context
    techs = calculate_technical_indicators(hist, info)
    
    # Compute risk metrics from actual data
    risk_metrics = calculate_risk_metrics(hist, info)
    
    # ── NEW: Advanced momentum indicators ──
    momentum = calculate_momentum_indicators(hist)
    
    # ── NEW: Ichimoku Cloud ──
    ichimoku = calculate_ichimoku(hist)
    
    # ── NEW: Fibonacci retracement levels ──
    fibonacci = calculate_fibonacci_levels(info, hist)
    
    # ── NEW: Sharpe/Sortino risk-adjusted returns ──
    risk_adjusted = calculate_sharpe_sortino(hist)
    
    # Fetch quarterly + cashflow + balance_sheet data if ticker_obj provided
    quarterly_income = None
    annual_income = None
    cashflow = None
    balance_sheet = None
    if ticker_obj is not None:
        try:
            if hasattr(ticker_obj, 'quarterly_income_stmt'):
                quarterly_income = ticker_obj.quarterly_income_stmt
            if hasattr(ticker_obj, 'income_stmt'):
                annual_income = ticker_obj.income_stmt
            if hasattr(ticker_obj, 'cashflow'):
                cashflow = ticker_obj.cashflow
            if hasattr(ticker_obj, 'balance_sheet'):
                balance_sheet = ticker_obj.balance_sheet
            _safe_print(f"[DataAgent] Financial statements loaded — "
                  f"QI: {'OK' if quarterly_income is not None and not quarterly_income.empty else 'N/A'}, "
                  f"AI: {'OK' if annual_income is not None and not annual_income.empty else 'N/A'}, "
                  f"CF: {'OK' if cashflow is not None and not cashflow.empty else 'N/A'}, "
                  f"BS: {'OK' if balance_sheet is not None and not balance_sheet.empty else 'N/A'}")
        except Exception as e:
            _safe_print(f"[DataAgent] Financial statement fetch error: {e}")
    
    # Extract quarterly trends (#9, #10)
    qoq = extract_quarterly_trends(quarterly_income)
    
    # Compute DCF and valuation metrics (#31-#42)
    dcf = calculate_dcf(info, cashflow, annual_income)
    
    # ── NEW: Altman Z-Score ──
    altman = calculate_altman_z(info, balance_sheet, annual_income)
    
    # ── NEW: Balance Sheet Health ──
    bs_health = extract_balance_sheet_health(info, balance_sheet, annual_income)
    
    # ── NEW: DuPont Decomposition ──
    dupont = calculate_dupont(info, annual_income, balance_sheet)

    # ── NEW: True ROCE (EBIT / capital employed) + ROA fallback ──
    profitability = calculate_roce(info, balance_sheet, annual_income)
    
    # Fetch live news
    try:
        ddg_news = await fetch_news_ddgs(symbol)
        if ddg_news:
            news_data = ddg_news
    except Exception:
        pass
    
    new_fields = sum([
        len(momentum), len(ichimoku), len(fibonacci), len(risk_adjusted),
        len(altman), len(bs_health), len(dupont)
    ])
    _safe_print(f"[DataAgent] New metrics computed: momentum={len(momentum)}, ichimoku={len(ichimoku)}, "
          f"fibonacci={len(fibonacci)}, sharpe={len(risk_adjusted)}, altman={len(altman)}, "
          f"bs_health={len(bs_health)}, dupont={len(dupont)} — total new: {new_fields}")
    
    return {
        "ticker": symbol,
        "sector": sector,
        "industry": info.get('industry', sector),
        "info": info,
        "technicals": techs,
        "risk_metrics": risk_metrics,
        "momentum": momentum,
        "ichimoku": ichimoku,
        "fibonacci": fibonacci,
        "risk_adjusted": risk_adjusted,
        "altman": altman,
        "balance_sheet_health": bs_health,
        "dupont": dupont,
        "profitability": profitability,
        "qoq_trends": qoq,
        "dcf_valuation": dcf,
        "news": news_data[:5],
        # Pre-extracted key info fields (#13, #14, #15, #16)
        "holdings": {
            "promoter_pct": _safe_round((info.get('heldPercentInsiders', 0)) * 100, 1),
            "institutional_pct": _safe_round((info.get('heldPercentInstitutions', 0)) * 100, 1),
        },
        "analyst": {
            "rating": info.get('recommendationKey'),
            "rating_score": _safe_round(info.get('recommendationMean')),
            "num_analysts": info.get('numberOfAnalystOpinions'),
            "target_mean": _safe_round(info.get('targetMeanPrice')),
            "target_high": _safe_round(info.get('targetHighPrice')),
            "target_low": _safe_round(info.get('targetLowPrice')),
        },
        "portfolio": portfolio_ctx or {"is_held": False},
    }


async def run_fundamental_agent(data_ctx: dict) -> dict:
    """2. Fundamental Analysis Agent — 26 metrics with DuPont + Altman Z + Balance Sheet.
    
    Raw data extracted directly + LLM interprets with scoring rubric.
    """
    info = data_ctx.get("info", {})
    qoq = data_ctx.get("qoq_trends", {})
    dcf = data_ctx.get("dcf_valuation", {})
    holdings = data_ctx.get("holdings", {})
    analyst = data_ctx.get("analyst", {})
    dupont = data_ctx.get("dupont", {})
    altman = data_ctx.get("altman", {})
    bs_health = data_ctx.get("balance_sheet_health", {})
    
    # ── Extract all raw metrics (computed, not guessed) ──
    pe_ratio = _fmt(info.get('trailingPE'))
    forward_pe = _fmt(info.get('forwardPE'))
    pb_ratio = _fmt(info.get('priceToBook'))
    roe_raw = info.get('returnOnEquity')
    roe = _fmt(roe_raw * 100 if roe_raw and abs(roe_raw) < 1 else roe_raw, "%") if roe_raw else None
    de_ratio = _fmt(info.get('debtToEquity'))
    dy_raw = info.get('dividendYield')
    div_yield = _fmt(dy_raw * 100 if dy_raw and dy_raw < 1 else dy_raw, "%") if dy_raw else None
    rev_growth_raw = info.get('revenueGrowth')
    rev_growth = _fmt(rev_growth_raw * 100 if rev_growth_raw and abs(rev_growth_raw) < 5 else rev_growth_raw, "%") if rev_growth_raw else None
    earnings_growth_raw = info.get('earningsGrowth') or info.get('earningsQuarterlyGrowth')
    eps_trend_val = _fmt(earnings_growth_raw * 100 if earnings_growth_raw and abs(earnings_growth_raw) < 5 else earnings_growth_raw, "%") if earnings_growth_raw else None
    profit_margin = _fmt(info.get('profitMargins', 0) * 100, "%") if info.get('profitMargins') else None
    gross_margin = _fmt(info.get('grossMargins', 0) * 100, "%") if info.get('grossMargins') else None
    op_margin_raw = info.get('operatingMargins')
    op_margin = _fmt(op_margin_raw * 100 if op_margin_raw and abs(op_margin_raw) < 1 else op_margin_raw, "%") if op_margin_raw else None
    # TRUE ROCE = EBIT / (Total Assets − Current Liabilities), computed upstream in
    # calculate_roce(). Falls back to ROA (correctly named) when inputs are missing.
    profitability = data_ctx.get("profitability", {})
    roce_val = profitability.get("roce")
    roa_val = profitability.get("roa")
    roce = _fmt(roce_val, "%") if roce_val is not None else None
    roa = _fmt(roa_val, "%") if roa_val is not None else None
    
    qoq_eps_str = ", ".join([f"Q{i+1}: {q['eps']}" for i, q in enumerate(qoq.get('qoq_eps', [])[-4:])])
    
    # Forward PE gap signal
    pe_gap = None
    if info.get('trailingPE') and info.get('forwardPE'):
        gap = ((info['trailingPE'] - info['forwardPE']) / info['trailingPE']) * 100
        pe_gap = _safe_round(gap, 1)
    
    prompt = f"""
    ROLE: Senior Fundamental Equity Analyst (30 years, SEBI registered, CFA Charterholder)
    TASK: Interpret the fundamentals of {data_ctx['ticker']} ({data_ctx.get('industry', data_ctx['sector'])}).
    
    ALL DATA IS PRE-COMPUTED (do not recalculate — just interpret):
    
    VALUATION:
    P/E (Trailing): {pe_ratio}, P/E (Forward): {forward_pe}, P/E Gap: {pe_gap}% (positive = earnings expected to grow)
    P/B: {pb_ratio}, Dividend Yield: {div_yield}
    
    PROFITABILITY:
    ROE: {roe}, ROCE: {roce} (EBIT/capital employed), ROA: {roa}, Operating Margin: {op_margin}
    Profit Margin: {profit_margin}, Gross Margin: {gross_margin}
    
    DUPONT DECOMPOSITION (reveals WHY ROE is what it is):
    Net Margin: {dupont.get('dupont_net_margin_pct')}% × Asset Turnover: {dupont.get('dupont_asset_turnover')} × Equity Multiplier: {dupont.get('dupont_equity_multiplier')} = ROE: {dupont.get('dupont_computed_roe_pct')}%
    ROE Driver: {dupont.get('dupont_roe_driver', 'N/A')}
    
    SOLVENCY:
    Debt/Equity: {de_ratio}
    Altman Z-Score: {altman.get('altman_z_score')} ({altman.get('altman_zone', 'N/A')})
    Interest Coverage: {bs_health.get('interest_coverage')}x, Working Capital: {bs_health.get('working_capital_cr')} Cr
    Current Ratio: {bs_health.get('current_ratio')}, Debt/Assets: {bs_health.get('debt_to_assets')}%
    
    GROWTH:
    Revenue Growth: {rev_growth}, Earnings Growth: {eps_trend_val}
    {_revenue_cagr_line(dcf)}
    QoQ EPS Trend: {qoq_eps_str} ({qoq.get('eps_trend', 'N/A')})
    
    OWNERSHIP:
    Promoter: {holdings.get('promoter_pct')}%, Institutional: {holdings.get('institutional_pct')}%
    Analyst: {analyst.get('rating')} ({analyst.get('num_analysts')} analysts), Target: {analyst.get('target_mean')}
    {_portfolio_prompt_section(data_ctx)}
    SCORING RUBRIC:
    Score 9-10: P/E < sector avg AND ROE > 20% AND D/E < 0.5 AND growing earnings AND Z > 2.99
    Score 7-8: Most metrics favorable, 1-2 minor concerns
    Score 5-6: Mixed — some strengths offset by weaknesses
    Score 3-4: Multiple concerns (high debt, declining margins, leverage-driven ROE)
    Score 1-2: Severe fundamental distress (Z < 1.81, negative ROE, deteriorating earnings)
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "valuation_assessment": "Undervalued / Fair Value / Overvalued",
        "verdict": "Bullish / Neutral / Bearish",
        "score": "1-10 number following rubric above",
        "key_insight": "1-2 sentence explanation referencing the most important data point"
    }}
    """
    ai_result = await async_llm_call(prompt)
    
    return {
        "pe_ratio": pe_ratio or "--",
        "forward_pe": forward_pe or "--",
        "pb_ratio": pb_ratio or "--",
        "roe": roe or "--",
        "roce": roce or "--",
        "operating_margin": op_margin or "--",
        "debt_to_equity": de_ratio or "--",
        "dividend_yield": div_yield or "--",
        "revenue_growth": rev_growth or "--",
        "eps_trend": eps_trend_val or qoq.get("eps_trend", "--"),
        "profit_margin": profit_margin or "--",
        "gross_margin": gross_margin or "--",
        "revenue_cagr_3yr": f"{dcf.get('revenue_cagr_3yr')}%" if dcf.get('revenue_cagr_3yr') else "--",
        "qoq_eps": qoq.get("qoq_eps", []),
        "qoq_revenue": qoq.get("qoq_revenue", []),
        "promoter_holding_pct": holdings.get("promoter_pct"),
        "institutional_holding_pct": holdings.get("institutional_pct"),
        "analyst_rating": analyst.get("rating"),
        "analyst_target": analyst.get("target_mean"),
        "num_analysts": analyst.get("num_analysts"),
        # New fields
        "altman_z_score": altman.get("altman_z_score"),
        "altman_zone": altman.get("altman_zone"),
        "interest_coverage": bs_health.get("interest_coverage"),
        "working_capital_cr": bs_health.get("working_capital_cr"),
        "dupont_roe_driver": dupont.get("dupont_roe_driver"),
        "dupont_equity_multiplier": dupont.get("dupont_equity_multiplier"),
        "pe_gap_pct": pe_gap,
        # AI interpretation
        "valuation_assessment": ai_result.get("valuation_assessment", "--"),
        "verdict": ai_result.get("verdict", "Neutral"),
        "score": ai_result.get("score"),
        "key_insight": ai_result.get("key_insight", ""),
        # Keep legacy fields for frontend compatibility
        "revenue_growth_label": ai_result.get("revenue_growth_label"),
        "eps_trend_label": ai_result.get("eps_trend_label"),
        "growth_outlook": ai_result.get("growth_outlook"),
        "value_rating": ai_result.get("value_rating"),
        "financial_health": ai_result.get("financial_health"),
    }


async def run_technical_agent(data_ctx: dict) -> dict:
    """3. Technical Analysis Agent — 25 metrics with momentum, Ichimoku, Fibonacci.
    
    LLM only interprets the data, doesn't generate any numbers.
    """
    techs = data_ctx.get("technicals", {})
    mom = data_ctx.get("momentum", {})
    ichi = data_ctx.get("ichimoku", {})
    fib = data_ctx.get("fibonacci", {})
    
    # Count bullish/bearish signals for quantitative scoring
    bullish_signals = 0
    bearish_signals = 0
    total_signals = 0
    
    signal_checks = [
        (techs.get('trend', ''), ['Uptrend', 'Strong Uptrend']),
        (techs.get('momentum', ''), ['Bullish']),
        (techs.get('macd_crossover', ''), ['Bullish']),
        (techs.get('volume_signal', ''), ['High', 'Very High']),
        (mom.get('stochastic_signal', ''), ['Oversold']),  # Oversold = bullish opportunity
        (mom.get('adx_signal', ''), ['Strong Trend', 'Very Strong Trend']),
        (mom.get('obv_signal', ''), ['Accumulation']),
        (ichi.get('cloud_status', ''), ['Above Cloud']),
        (ichi.get('tk_cross', ''), ['Bullish']),
    ]
    for val, bullish_keywords in signal_checks:
        if val:
            total_signals += 1
            if any(kw.lower() in val.lower() for kw in bullish_keywords):
                bullish_signals += 1
            else:
                bearish_signals += 1
    
    signal_score = round((bullish_signals / total_signals) * 10, 1) if total_signals > 0 else 5
    
    prompt = f"""
    ROLE: CMT Level 3 Technical Analyst (20 years institutional experience)
    TASK: Interpret these pre-computed technical indicators for {data_ctx['ticker']}.
    
    ALL DATA IS PRE-COMPUTED (do not recalculate — just interpret):
    
    CORE INDICATORS:
    Price: {techs.get('current_price')}
    Trend: {techs.get('trend')} | Momentum: {techs.get('momentum')}
    RSI(14): {techs.get('rsi_14')} | MACD: {techs.get('macd')} vs Signal: {techs.get('macd_signal')} ({techs.get('macd_crossover')})
    SMA 50: {techs.get('sma_50')} | SMA 200: {techs.get('sma_200')}
    Bollinger: Upper {techs.get('bb_upper')} — Lower {techs.get('bb_lower')} (Width: {techs.get('bb_width_pct')}%)
    
    ADVANCED MOMENTUM:
    Stochastic: %K={mom.get('stochastic_k')} %D={mom.get('stochastic_d')} ({mom.get('stochastic_signal', 'N/A')})
    Williams %R: {mom.get('williams_r')} ({mom.get('williams_signal', 'N/A')})
    ADX: {mom.get('adx')} ({mom.get('adx_signal', 'N/A')}) | +DI: {mom.get('plus_di')} -DI: {mom.get('minus_di')}
    CCI: {mom.get('cci')} ({mom.get('cci_signal', 'N/A')})
    OBV Signal: {mom.get('obv_signal', 'N/A')}
    
    ICHIMOKU CLOUD:
    Cloud Status: {ichi.get('cloud_status', 'N/A')} | TK Cross: {ichi.get('tk_cross', 'N/A')}
    Cloud Color: {ichi.get('cloud_color', 'N/A')}
    Tenkan: {ichi.get('tenkan_sen')} | Kijun: {ichi.get('kijun_sen')}
    Cloud Top: {ichi.get('cloud_top')} | Cloud Bottom: {ichi.get('cloud_bottom')}
    
    FIBONACCI LEVELS:
    23.6%: {fib.get('fib_236')} | 38.2%: {fib.get('fib_382')} | 50%: {fib.get('fib_500')} | 61.8%: {fib.get('fib_618')}
    
    SUPPORT/RESISTANCE:
    Pivot Support: {techs.get('support_level')} | Pivot Resistance: {techs.get('resistance_level')}
    52W High: {techs.get('fifty_two_week_high')} | 52W Low: {techs.get('fifty_two_week_low')} | From 52W High: {techs.get('pct_from_52w_high')}%
    
    VOLUME:
    Current: {techs.get('current_volume')} (Ratio vs 20d avg: {techs.get('volume_ratio')}x) — {techs.get('volume_signal')}
    Volume-Price: {techs.get('volume_price_divergence')}
    
    QUANTITATIVE SIGNAL COUNT: {bullish_signals}/{total_signals} indicators bullish (raw score: {signal_score}/10)
    
    SCORING RUBRIC:
    Use the signal count as starting point, then adjust ±1 based on signal quality:
    - ADX > 25 with bullish DI crossover: +1
    - Price above Ichimoku cloud with bullish TK cross: +1
    - Bearish divergence (price up, OBV down): -1
    - RSI > 75 or < 25 (extreme): -1 for sustainability
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "trend": "{techs.get('trend', 'Neutral')}",
        "momentum": "{techs.get('momentum', 'Neutral')}",
        "support_level": {techs.get('support_level') or 0},
        "resistance_level": {techs.get('resistance_level') or 0},
        "verdict": "Bullish / Neutral / Bearish",
        "score": "1-10 number following rubric",
        "key_insight": "1-2 sentence actionable signal citing the strongest confirming/contradicting indicators"
    }}
    """
    ai_result = await async_llm_call(prompt)
    
    # Merge ALL computed data + AI interpretation
    merged = dict(techs)
    merged.update(mom)  # Add momentum indicators
    merged["ichimoku_status"] = ichi.get("cloud_status")
    merged["ichimoku_tk_cross"] = ichi.get("tk_cross")
    merged["fib_382"] = fib.get("fib_382")
    merged["fib_618"] = fib.get("fib_618")
    merged["signal_score_raw"] = signal_score
    merged["verdict"] = ai_result.get("verdict", techs.get("trend", "Neutral"))
    merged["score"] = ai_result.get("score")
    merged["key_insight"] = ai_result.get("key_insight", "")
    return merged


async def run_news_agent(data_ctx: dict) -> dict:
    """4. News & Sentiment Agent — enriched with analyst data and headline analysis."""
    news = data_ctx.get("news", [])
    analyst = data_ctx.get("analyst", {})
    info = data_ctx.get("info", {})
    techs = data_ctx.get("technicals", {})
    
    news_text = "\n".join([f"- {n.get('title')} ({n.get('source')})" for n in news])
    
    # Target price upside/downside
    target_upside = None
    current_price = techs.get("current_price")
    if current_price and analyst.get("target_mean"):
        target_upside = _safe_round(((analyst["target_mean"] - current_price) / current_price) * 100, 1)
    
    # Analyst target dispersion
    target_dispersion = None
    if analyst.get("target_high") and analyst.get("target_low") and analyst.get("target_mean"):
        spread = analyst["target_high"] - analyst["target_low"]
        target_dispersion = _safe_round((spread / analyst["target_mean"]) * 100, 1)
    
    prompt = f"""
    ROLE: Institutional Market Sentiment Analyst (specializes in Indian equities)
    TASK: Analyze sentiment for {data_ctx['ticker']} ({data_ctx.get('industry', data_ctx['sector'])}).
    
    RECENT NEWS HEADLINES:
    {news_text if news_text else "No recent news available"}
    
    ANALYST DATA:
    Consensus: {analyst.get('rating')} (score {analyst.get('rating_score')}/5, {analyst.get('num_analysts')} analysts)
    Target: Mean ₹{analyst.get('target_mean')}, High ₹{analyst.get('target_high')}, Low ₹{analyst.get('target_low')}
    Target Upside/Downside: {target_upside}% from current price ₹{current_price}
    Target Dispersion: {target_dispersion}% (high = analysts disagree, low = consensus is strong)
    
    SCORING RUBRIC:
    Score 8-10: Mostly positive news + analyst Buy/Strong Buy + target upside > 15% + low dispersion
    Score 6-7: Mixed news but analyst consensus positive OR strong positive news but neutral analyst
    Score 4-5: Mixed signals across news and analysts
    Score 2-3: Negative news flow + analyst downgrades or Sell ratings
    Score 1: Severe negative catalysts (fraud, regulatory action, bankruptcy risk)
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "sentiment": "Positive / Negative / Mixed",
        "catalysts": ["catalyst 1", "catalyst 2"],
        "risks": ["risk 1", "risk 2"],
        "verdict": "Bullish / Neutral / Bearish",
        "score": "1-10 number following rubric",
        "key_insight": "1 sentence sentiment view referencing specific news or analyst data"
    }}
    """
    result = await async_llm_call(prompt)
    result["analyst_rating"] = analyst.get("rating")
    result["analyst_target_mean"] = analyst.get("target_mean")
    result["num_analysts"] = analyst.get("num_analysts")
    result["target_upside_pct"] = target_upside
    result["target_dispersion_pct"] = target_dispersion
    return result


async def run_macro_agent(data_ctx: dict) -> dict:
    """5. Macro & Sector Agent — with sector-relative performance and market context."""
    info = data_ctx.get("info", {})
    sector = data_ctx.get("sector")
    industry = data_ctx.get("industry", sector)
    risk_adjusted = data_ctx.get("risk_adjusted", {})
    
    # Sector sensitivity indicators
    export_sectors = ['IT', 'Pharma', 'Auto']
    is_export_heavy = sector in export_sectors or industry in export_sectors
    commodity_sectors = ['Energy', 'Mining', 'Metals', 'Steel']
    is_commodity_dependent = sector in commodity_sectors or industry in commodity_sectors
    rate_sensitive_sectors = ['Banking', 'Financial Services', 'NBFC', 'Real Estate']
    is_rate_sensitive = sector in rate_sensitive_sectors or industry in rate_sensitive_sectors
    
    prompt = f"""
    ROLE: Global Macro Economist (India specialist, 20 years at RBI/SEBI advisory)
    TASK: Assess macro headwinds/tailwinds for {data_ctx['ticker']} in {industry} ({sector}).
    
    REAL DATA:
    Beta vs Market: {info.get('beta')} (>1.2=High, <0.8=Low market sensitivity)
    Market Cap: {_safe_round((info.get('marketCap', 0)) / 1e7, 0)} Cr
    52W Stock Performance: {_safe_round((info.get('52WeekChange', 0)) * 100)}%
    Market 52W Performance: {_safe_round((info.get('SandP52WeekChange', 0)) * 100)}%
    Outperformance vs Market: {_safe_round(((info.get('52WeekChange', 0) or 0) - (info.get('SandP52WeekChange', 0) or 0)) * 100)}%
    Annualized Return: {risk_adjusted.get('annualized_return_pct')}%
    
    SECTOR SENSITIVITY FLAGS:
    Export-heavy (INR/USD sensitive): {'YES' if is_export_heavy else 'NO'}
    Commodity-dependent (raw material cost sensitive): {'YES' if is_commodity_dependent else 'NO'}
    Interest rate sensitive (RBI policy impact): {'YES' if is_rate_sensitive else 'NO'}
    
    CONTEXT: Consider current India macro environment — RBI rate stance, FII/DII flow trends,
    government policy (PLI schemes, infrastructure push), and global factors affecting {sector}.
    
    SCORING RUBRIC:
    Score 8-10: Strong sector tailwinds + government policy support + stock outperforming market
    Score 6-7: Neutral macro with some sector-specific positives
    Score 4-5: Mixed — some headwinds offset by tailwinds
    Score 2-3: Significant headwinds (rate hikes for banking, INR appreciation for IT, commodity price spike)
    Score 1: Severe macro risk (regulatory crackdown, sector-wide policy reversal)
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "sector_outlook": "Favorable / Neutral / Unfavorable",
        "interest_rate_sensitivity": "High / Medium / Low",
        "currency_impact": "Positive / Neutral / Negative",
        "sector_cycle_position": "Early Cycle / Mid Cycle / Late Cycle",
        "verdict": "Bullish / Neutral / Bearish",
        "score": "1-10 number following rubric",
        "key_insight": "1 sentence macro view specific to this sector and stock"
    }}
    """
    result = await async_llm_call(prompt)
    result["is_export_heavy"] = is_export_heavy
    result["is_commodity_dependent"] = is_commodity_dependent
    result["is_rate_sensitive"] = is_rate_sensitive
    return result


async def run_quant_agent(data_ctx: dict) -> dict:
    """6. Quantitative Agent — ALL numbers pre-computed including FCF yield and EV/Revenue.
    
    DCF, Graham Number, CAGR, Margin of Safety — real math, not guessing.
    """
    dcf = data_ctx.get("dcf_valuation", {})
    info = data_ctx.get("info", {})
    techs = data_ctx.get("technicals", {})
    current_price = techs.get("current_price", 0)
    
    # Additional valuation metrics
    fcf_yield = None
    if dcf.get('fcf_ttm') and info.get('marketCap') and info['marketCap'] > 0:
        fcf_yield = _safe_round((dcf['fcf_ttm'] / info['marketCap']) * 100, 2)
    
    earnings_yield = None
    if info.get('trailingPE') and info['trailingPE'] > 0:
        earnings_yield = _safe_round(100 / info['trailingPE'], 2)
    
    ev_revenue = None
    if info.get('enterpriseValue') and info.get('totalRevenue') and info['totalRevenue'] > 0:
        ev_revenue = _safe_round(info['enterpriseValue'] / info['totalRevenue'], 2)
    
    price_to_sales = _safe_round(info.get('priceToSalesTrailing12Months'))
    
    # Reverse DCF: what growth rate is market pricing in?
    reverse_dcf_growth = None
    if dcf.get('fcf_ttm') and dcf['fcf_ttm'] > 0 and info.get('marketCap') and info.get('sharesOutstanding'):
        try:
            market_iv = info['marketCap'] / info['sharesOutstanding']
            # Solve for growth: simplified — what growth makes DCF = market price
            # Using approximation: growth ≈ (market_price * discount_rate) / fcf_per_share - 1
            fcf_per_share = dcf['fcf_ttm'] / info['sharesOutstanding']
            if fcf_per_share > 0:
                implied_growth = ((market_iv * 0.08) / (fcf_per_share * 10)) - 0.04
                reverse_dcf_growth = _safe_round(implied_growth * 100, 1)
        except Exception:
            pass
    
    # Count valuation signals
    undervalue_signals = 0
    total_val_signals = 0
    if dcf.get('margin_of_safety_pct'):
        total_val_signals += 1
        if dcf['margin_of_safety_pct'] > 0: undervalue_signals += 1
    if dcf.get('peg_ratio'):
        total_val_signals += 1
        if dcf['peg_ratio'] < 1: undervalue_signals += 1
    if dcf.get('ev_ebitda'):
        total_val_signals += 1
        if dcf['ev_ebitda'] < 15: undervalue_signals += 1
    if dcf.get('graham_number') and current_price:
        total_val_signals += 1
        if dcf['graham_number'] > current_price: undervalue_signals += 1

    # Revenue CAGR — true 3-year when 4 annual points exist, else 2-year fallback
    if dcf.get('revenue_cagr_3yr') is not None:
        cagr_label, cagr_val = "3yr", dcf.get('revenue_cagr_3yr')
    elif dcf.get('revenue_cagr_2yr') is not None:
        cagr_label, cagr_val = "2yr", dcf.get('revenue_cagr_2yr')
    else:
        cagr_label, cagr_val = "3yr", None

    prompt = f"""
    ROLE: Quantitative Valuation Analyst (CFA, specialized in multi-model valuation)
    TASK: Interpret these PRE-COMPUTED valuation metrics for {data_ctx['ticker']}.
    
    ALL NUMBERS ARE MATHEMATICALLY COMPUTED (do not recalculate):
    
    INTRINSIC VALUE MODELS:
    Current Price: ₹{current_price}
    DCF Intrinsic Value: ₹{dcf.get('dcf_intrinsic_value')} (12% discount, {cagr_val}% growth, net-debt adjusted)
    Graham Number: ₹{dcf.get('graham_number')} (EPS={info.get('trailingEps')}, BV={info.get('bookValue')})
    Margin of Safety: {dcf.get('margin_of_safety_pct')}%
    
    RELATIVE VALUATION:
    PEG Ratio: {dcf.get('peg_ratio')} (source: {dcf.get('peg_source', 'N/A')}; < 1 = undervalued relative to growth)
    EV/EBITDA: {dcf.get('ev_ebitda')} (< 10 = cheap, 10-15 = fair, > 20 = expensive)
    EV/Revenue: {ev_revenue} | Price/Sales: {price_to_sales}
    Earnings Yield: {earnings_yield}% (compare to 7% govt bond yield)
    FCF Yield: {fcf_yield}% (> 5% = attractive, > 8% = very cheap)
    
    CASH FLOW:
    FCF (TTM): ₹{_safe_round((dcf.get('fcf_ttm') or 0) / 1e7, 0)} Cr
    Net Debt: ₹{_safe_round((dcf.get('net_debt') or 0) / 1e7, 0)} Cr
    Enterprise Value: ₹{_safe_round((dcf.get('enterprise_value') or 0) / 1e7, 0)} Cr
    Revenue CAGR ({cagr_label}): {cagr_val}%

    REVERSE DCF: Market is pricing in ~{reverse_dcf_growth}% growth (compare to actual {cagr_label} CAGR of {cagr_val}%)
    
    MULTI-MODEL CONSENSUS: {undervalue_signals}/{total_val_signals} models suggest undervaluation
    {_portfolio_prompt_section(data_ctx)}
    SCORING RUBRIC:
    Score 9-10: 3+ models agree undervalued AND FCF yield > 5% AND MoS > 20%
    Score 7-8: Most models agree, FCF positive, reasonable valuation
    Score 5-6: Mixed signals — some models say cheap, others say fair/expensive
    Score 3-4: Most models suggest overvaluation, low FCF yield
    Score 1-2: Negative FCF, no Graham Number computable, all models say overvalued
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "overall_signal": "BUY / HOLD / SELL",
        "valuation_status": "UNDERVALUED / FAIR / OVERVALUED",
        "verdict": "Bullish / Neutral / Bearish",
        "score": "1-10 number following rubric",
        "key_insight": "1-2 sentence view referencing specific computed numbers"
    }}
    """
    ai_result = await async_llm_call(prompt)
    
    return {
        **dcf,
        "overall_signal": ai_result.get("overall_signal", "HOLD"),
        "valuation_status": ai_result.get("valuation_status", "FAIR"),
        "verdict": ai_result.get("verdict", "Neutral"),
        "score": ai_result.get("score"),
        "key_insight": ai_result.get("key_insight", ""),
        "peg_ratio": _fmt(dcf.get("peg_ratio")) if dcf.get("peg_ratio") else "--",
        # New fields
        "fcf_yield_pct": fcf_yield,
        "earnings_yield_pct": earnings_yield,
        "ev_revenue": ev_revenue,
        "price_to_sales": price_to_sales,
        "reverse_dcf_growth_pct": reverse_dcf_growth,
        "undervalue_consensus": f"{undervalue_signals}/{total_val_signals}",
        # Legacy compatibility
        "factor_grades": ai_result.get("factor_grades"),
    }


async def run_risk_agent(data_ctx: dict) -> dict:
    """7. Risk Agent — ALL metrics computed including Sharpe/Sortino/Calmar.
    
    Volatility, Max Drawdown, VaR, risk-adjusted returns — real math, not LLM guessing.
    """
    risk = data_ctx.get("risk_metrics", {})
    info = data_ctx.get("info", {})
    risk_adj = data_ctx.get("risk_adjusted", {})
    bs_health = data_ctx.get("balance_sheet_health", {})
    altman = data_ctx.get("altman", {})
    techs = data_ctx.get("technicals", {})
    
    # Liquidity risk
    liquidity_turnover = None
    if techs.get('avg_volume_3m') and techs.get('current_price'):
        daily_turnover_cr = (techs['avg_volume_3m'] * techs['current_price']) / 1e7
        liquidity_turnover = _safe_round(daily_turnover_cr, 1)
    
    # VaR 99% — real empirical 1st-percentile computed in calculate_risk_metrics
    var_99 = risk.get('var_99_daily_pct')
    
    prompt = f"""
    ROLE: Chief Risk Officer (CRO, 25 years institutional risk management)
    TASK: Interpret these PRE-COMPUTED risk metrics for {data_ctx['ticker']}.
    
    ALL NUMBERS ARE MATHEMATICALLY COMPUTED FROM 1-YEAR DAILY DATA:
    
    MARKET RISK:
    Annual Volatility: {risk.get('annual_volatility_pct')}% (annualized std dev)
    Max Drawdown: -{risk.get('max_drawdown_estimate_pct')}% (worst peak-to-trough in 1yr)
    VaR (95%): -{risk.get('var_95_daily_pct')}% per day | VaR (99%): -{var_99}% per day
    Beta: {risk.get('beta')} (>1 = more volatile than market)
    
    RISK-ADJUSTED RETURNS:
    Sharpe Ratio: {risk_adj.get('sharpe_ratio')} ({risk_adj.get('sharpe_rating', 'N/A')}) — return per unit of total risk
    Sortino Ratio: {risk_adj.get('sortino_ratio')} — return per unit of downside risk only
    Calmar Ratio: {risk_adj.get('calmar_ratio')} — annualized return / max drawdown
    Annualized Return: {risk_adj.get('annualized_return_pct')}%
    
    FINANCIAL RISK:
    Debt/Equity: {info.get('debtToEquity')}
    Interest Coverage: {bs_health.get('interest_coverage')}x (< 2 = danger)
    Current Ratio: {bs_health.get('current_ratio')} (< 1 = liquidity crisis)
    Altman Z-Score: {altman.get('altman_z_score')} ({altman.get('altman_zone', 'N/A')})
    
    LIQUIDITY RISK:
    Daily Turnover: ~{liquidity_turnover} Cr (< 5 Cr = illiquid, hard to exit large positions)
    {_portfolio_prompt_section(data_ctx)}
    SCORING RUBRIC (higher = SAFER):
    Score 9-10: Low vol (<20%), Sharpe > 1.5, Z > 2.99, max DD < 10%, high liquidity
    Score 7-8: Moderate vol, Sharpe > 1.0, no financial distress, adequate liquidity
    Score 5-6: Average risk — vol 20-30%, Sharpe 0.5-1.0, some concerns
    Score 3-4: High risk — vol > 35%, poor Sharpe, Z in grey zone, or low liquidity
    Score 1-2: Extreme — vol > 50%, negative Sharpe, Z in distress, or illiquid
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "risk_level": "{risk.get('risk_level', 'Medium')}",
        "volatility_profile": "{risk.get('volatility_profile', 'Medium')}",
        "max_drawdown_estimate_pct": {risk.get('max_drawdown_estimate_pct', 0)},
        "verdict": "Low Risk / Medium Risk / High Risk",
        "score": "1-10 number (higher = SAFER) following rubric",
        "key_insight": "1-2 sentence risk view referencing Sharpe and max drawdown"
    }}
    """
    ai_result = await async_llm_call(prompt)
    
    return {
        **risk,
        **risk_adj,
        "risk_level": ai_result.get("risk_level", risk.get("risk_level", "Medium")),
        "volatility_profile": ai_result.get("volatility_profile", risk.get("volatility_profile", "Medium")),
        "verdict": ai_result.get("verdict", risk.get("risk_level", "Medium Risk")),
        "score": ai_result.get("score"),
        "key_insight": ai_result.get("key_insight", ""),
        # New fields
        "var_99_daily_pct": var_99,
        "liquidity_turnover_cr": liquidity_turnover,
        "altman_z_score": altman.get("altman_z_score"),
        "altman_zone": altman.get("altman_zone"),
        "interest_coverage": bs_health.get("interest_coverage"),
    }


async def run_trade_structuring_agent(data_ctx: dict) -> dict:
    """8. Trade Structuring Agent — uses Fibonacci, Ichimoku, and risk metrics."""
    techs = data_ctx.get("technicals", {})
    risk = data_ctx.get("risk_metrics", {})
    risk_adj = data_ctx.get("risk_adjusted", {})
    fib = data_ctx.get("fibonacci", {})
    ichi = data_ctx.get("ichimoku", {})
    analyst = data_ctx.get("analyst", {})
    
    prompt = f"""
    ROLE: Institutional Execution Trader (15 years on NSE/BSE dealing desk)
    TASK: Create a specific, actionable trade plan for {data_ctx['ticker']}.
    
    PRE-COMPUTED PRICE LEVELS:
    Current Price: ₹{techs.get('current_price')}
    
    Pivot Support: ₹{techs.get('support_level')} | Pivot Resistance: ₹{techs.get('resistance_level')}
    
    Fibonacci Levels (from 52W range):
    23.6%: ₹{fib.get('fib_236')} | 38.2%: ₹{fib.get('fib_382')} | 50%: ₹{fib.get('fib_500')} | 61.8%: ₹{fib.get('fib_618')}
    
    Ichimoku: Cloud Top ₹{ichi.get('cloud_top')} | Cloud Bottom ₹{ichi.get('cloud_bottom')} ({ichi.get('cloud_status', 'N/A')})
    Kijun-sen (base support): ₹{ichi.get('kijun_sen')}
    
    52W High: ₹{techs.get('fifty_two_week_high')} | 52W Low: ₹{techs.get('fifty_two_week_low')}
    Analyst Target: ₹{analyst.get('target_mean')} (High: ₹{analyst.get('target_high')})
    
    RISK DATA:
    Average Daily Volume: {techs.get('avg_volume_3m')} shares
    Risk Level: {risk.get('risk_level')} | Annual Volatility: {risk.get('annual_volatility_pct')}%
    VaR(95%): -{risk.get('var_95_daily_pct')}% per day
    Sharpe: {risk_adj.get('sharpe_ratio')} | Max Drawdown: -{risk.get('max_drawdown_estimate_pct')}%
    {_portfolio_prompt_section(data_ctx)}
    RULES:
    1. Stop loss MUST be below the nearest strong support (Fibonacci or Kijun-sen)
    2. Take profit targets should align with Fibonacci or resistance levels
    3. Position size: smaller for high-vol stocks (>35% vol = max 2%, <20% vol = up to 5%)
    4. Calculate risk:reward ratio (must be > 1.5 for a BUY recommendation)
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "entry_strategy": "Market / Limit at [price] / DCA in [N] tranches",
        "suggested_entry_price": "number or range",
        "stop_loss": "number (below nearest Fibonacci/Kijun support)",
        "take_profit_targets": ["target1 (Fib/resistance level)", "target2"],
        "position_size_recommendation": "X% of portfolio",
        "risk_reward_ratio": "number (reward/risk)",
        "dca_plan": "If DCA: specify tranches and levels, else null"
    }}
    """
    result = await async_llm_call(prompt)
    # Ensure numeric fields
    if isinstance(result.get("stop_loss"), str):
        try:
            result["stop_loss"] = float(result["stop_loss"].replace("₹", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            pass
    return result


async def run_master_cio_agent(ticker: str, agents_output: dict, portfolio_ctx: dict = None) -> dict:
    """9. Master CIO Agent — synthesizes all agent reports with weighted scoring + portfolio context."""
    
    # Extract agent scores for weighted calculation
    scores = {}
    weights = {
        'fundamental': 0.25, 'technical': 0.20, 'quant': 0.15,
        'risk': 0.15, 'news': 0.10, 'macro': 0.10, 'execution': 0.05
    }
    weighted_score = 0
    total_weight = 0
    
    for agent_key, weight in weights.items():
        agent_data = agents_output.get(agent_key, {})
        score = agent_data.get('score')
        if score is not None:
            try:
                s = float(score)
                scores[agent_key] = s
                weighted_score += s * weight
                total_weight += weight
            except (ValueError, TypeError):
                pass
    
    if total_weight > 0:
        weighted_score = round(weighted_score / total_weight, 1)
    
    scores_summary = ", ".join([f"{k}: {v}/10" for k, v in scores.items()])
    
    # ── Build portfolio context + compute action math ──
    pf = portfolio_ctx or {}
    exec_data = agents_output.get("execution", {})
    current_price = None
    # Try to get current price from execution or fundamental data
    for src in [exec_data, agents_output.get("fundamental", {}), agents_output.get("technical", {})]:
        for key in ["current_price", "ltp", "price"]:
            if src.get(key):
                try:
                    current_price = float(src[key])
                    break
                except (ValueError, TypeError):
                    pass
        if current_price:
            break
    
    # Get target and stop loss from execution agent
    target_price = None
    stop_loss = None
    try:
        tp = exec_data.get("take_profit_targets") or exec_data.get("target_price")
        if isinstance(tp, list) and tp:
            target_price = float(str(tp[0]).replace(",", "").split()[0])
        elif tp:
            target_price = float(str(tp).replace(",", "").split()[0])
    except (ValueError, TypeError):
        pass
    try:
        sl = exec_data.get("stop_loss")
        if sl:
            stop_loss = float(str(sl).replace(",", "").split()[0])
    except (ValueError, TypeError):
        pass
    try:
        ep = exec_data.get("suggested_entry_price")
        if ep:
            entry_price = float(str(ep).replace(",", "").split()[0])
        else:
            entry_price = current_price
    except (ValueError, TypeError):
        entry_price = current_price
    
    # ── Compute action plan math ──
    action_math = {}
    if pf.get("is_held"):
        old_shares = pf.get("shares", 0)
        old_avg = pf.get("avg_cost", 0)
        old_invested = old_shares * old_avg
        # Suggest adding same quantity as current holding (or use execution agent recommendation)
        suggested_add = max(old_shares, 10)
        add_price = entry_price or current_price or old_avg
        if add_price and add_price > 0:
            new_shares = old_shares + suggested_add
            new_invested = old_invested + (suggested_add * add_price)
            new_avg = round(new_invested / new_shares, 2) if new_shares > 0 else old_avg
            # Risk:Reward from new avg
            risk_per_share = new_avg - stop_loss if stop_loss and new_avg else 0
            reward_per_share = target_price - new_avg if target_price and new_avg else 0
            rr_ratio = round(reward_per_share / risk_per_share, 1) if risk_per_share > 0 else 0
            target_pct = round((target_price - new_avg) / new_avg * 100, 1) if target_price and new_avg else 0
            sl_pct = round((stop_loss - new_avg) / new_avg * 100, 1) if stop_loss and new_avg else 0
            # Sell partial: what % to sell at target
            sell_qty_at_target = max(1, new_shares // 2)
            action_math = {
                "old_shares": old_shares, "old_avg": old_avg,
                "suggested_add_shares": suggested_add,
                "add_price": round(add_price, 2),
                "add_cost": round(suggested_add * add_price, 0),
                "new_total_shares": new_shares,
                "new_avg_cost": new_avg,
                "target_pct": target_pct,
                "sl_pct": sl_pct,
                "risk_reward": f"1:{rr_ratio}" if rr_ratio > 0 else "N/A",
                "sell_qty_at_target": sell_qty_at_target,
            }
        portfolio_section = f"""
    USER'S CURRENT POSITION:
    Shares: {pf.get('shares', 0)} @ avg Rs.{pf.get('avg_cost', 0)}
    Invested: Rs.{pf.get('invested', 0):,.0f} | Current Value: Rs.{pf.get('current_value', 0):,.0f}
    P&L: Rs.{pf.get('pnl', 0):,.0f} ({pf.get('pnl_pct', 0):+.1f}%)
    Portfolio Weight: {pf.get('portfolio_weight_pct', 0)}%
    
    PRE-COMPUTED ACTION SCENARIOS (use these numbers, don't recalculate):
    If BUY MORE: Add {action_math.get('suggested_add_shares', 0)} shares @ Rs.{action_math.get('add_price', 0)}
      → New avg: Rs.{action_math.get('new_avg_cost', 0)}, Total: {action_math.get('new_total_shares', 0)} shares
      → Target: {action_math.get('target_pct', 0)}% gain, SL: {action_math.get('sl_pct', 0)}% loss
      → Risk:Reward = {action_math.get('risk_reward', 'N/A')}
    If SELL PARTIAL: Sell {pf.get('shares', 0) // 2} shares (50% of position)
    If HOLD: Keep {pf.get('shares', 0)} shares, no action
    
    YOUR JOB: Pick ONE action based on the agent scores and market conditions.
"""
    else:
        # New entry calculation
        if entry_price and entry_price > 0:
            suggested_qty = 10
            risk_per_share = entry_price - stop_loss if stop_loss else 0
            reward_per_share = target_price - entry_price if target_price else 0
            rr_ratio = round(reward_per_share / risk_per_share, 1) if risk_per_share > 0 else 0
            target_pct = round((target_price - entry_price) / entry_price * 100, 1) if target_price else 0
            sl_pct = round((stop_loss - entry_price) / entry_price * 100, 1) if stop_loss else 0
            action_math = {
                "old_shares": 0, "old_avg": 0,
                "suggested_add_shares": suggested_qty,
                "add_price": round(entry_price, 2),
                "add_cost": round(suggested_qty * entry_price, 0),
                "new_total_shares": suggested_qty,
                "new_avg_cost": round(entry_price, 2),
                "target_pct": target_pct,
                "sl_pct": sl_pct,
                "risk_reward": f"1:{rr_ratio}" if rr_ratio > 0 else "N/A",
                "sell_qty_at_target": suggested_qty // 2,
            }
        portfolio_section = f"""
    USER'S POSITION: Not currently held. Evaluate as a potential new entry.
    Suggested Entry: Rs.{entry_price or 'N/A'} | Target: {action_math.get('target_pct', 0)}% | SL: {action_math.get('sl_pct', 0)}%
    Risk:Reward = {action_math.get('risk_reward', 'N/A')}
"""
    
    prompt = f"""
    ROLE: Institutional Chief Investment Officer (30 years veteran, SEBI registered, manages $2B AUM)
    TASK: Make a FINAL investment decision on {ticker} by synthesizing your 8 subordinate agent reports.
    
    AGENT SCORES (weighted avg = {weighted_score}/10):
    {scores_summary}
    Weights: Fundamental 25%, Technical 20%, Quant 15%, Risk 15%, Sentiment 10%, Macro 10%, Execution 5%
    
    AGENT REPORTS:
    Fundamental: {json.dumps(agents_output.get('fundamental', dict()))}
    Technical: {json.dumps(agents_output.get('technical', dict()))}
    News/Sentiment: {json.dumps(agents_output.get('news', dict()))}
    Macro: {json.dumps(agents_output.get('macro', dict()))}
    Quant: {json.dumps(agents_output.get('quant', dict()))}
    Risk: {json.dumps(agents_output.get('risk', dict()))}
    Execution: {json.dumps(agents_output.get('execution', dict()))}
    
    IMPORTANT: All numerical data was computed mathematically from real market data. Trust these numbers.
    {portfolio_section}
    DECISION FRAMEWORK:
    STRONG BUY: Weighted score > 8 AND no agent below 5 AND Quant says UNDERVALUED
    BUY: Weighted score > 6.5 AND majority agents bullish
    HOLD: Weighted score 4.5-6.5 OR significant disagreement between agents
    SELL: Weighted score < 4.5 AND majority agents bearish
    STRONG SELL: Weighted score < 3 AND fundamental distress signals
    
    Conviction Score = weighted average x 10, clamped to 0-100, adjusted for agent agreement:
    - All agents agree: +10
    - 1-2 agents disagree: +0
    - 3+ agents disagree with majority: -10
    
    ACTION TYPES (pick exactly one):
    - "BUY MORE" = user already holds, add more shares
    - "NEW BUY" = user doesn't hold, fresh entry
    - "HOLD" = keep current position, no action
    - "SELL PARTIAL" = sell some shares (specify percentage like "Sell 50%")
    - "SELL ALL" = exit entire position
    - "AVOID" = don't buy this stock
    
    You must output EXACTLY a valid JSON object with NO surrounding text, markdown, or comments.
    
    OUTPUT EXACTLY THIS JSON FORMAT ONLY:
    {{
        "ticker": "{ticker}",
        "final_decision": "STRONG BUY / BUY / HOLD / SELL / STRONG SELL",
        "action_type": "BUY MORE / NEW BUY / HOLD / SELL PARTIAL / SELL ALL / AVOID",
        "conviction_score": "1-100 number",
        "executive_summary": "2-3 sentences referencing key data from multiple agents",
        "rationale": "2-3 sentences explaining WHY this action, citing specific numbers",
        "action_steps": ["Step 1: specific action with price", "Step 2: set stop loss at X", "Step 3: target at Y, book Z% profits"],
        "bull_case": "1 sentence: what could go right",
        "bear_case": "1 sentence: what could go wrong",
        "key_risk": "Single biggest threat",
        "investment_horizon": "Short Term (< 3M) / Medium Term (3-12M) / Long Term (> 12M)",
        "target_price": "number",
        "stop_loss": "number"
    }}
    """
    result = await async_llm_call(prompt)

    # ── Coerce conviction_score to an int clamped 0-100 ──
    # A failed/empty LLM call (result == {}) must NOT emit a spurious score → null.
    if not result:
        result = {"conviction_score": None}
    else:
        try:
            cs = int(round(float(result.get("conviction_score"))))
            result["conviction_score"] = max(0, min(100, cs))
        except (TypeError, ValueError):
            result["conviction_score"] = None

    # Attach portfolio + computed action math for frontend
    result["portfolio"] = portfolio_ctx or {"is_held": False}
    result["action_math"] = action_math
    if target_price:
        result["target_price"] = target_price
    if stop_loss:
        result["stop_loss"] = stop_loss
    return result


# ═══════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════

async def run_full_analysis_async(ticker_obj, symbol: str, history_df: pd.DataFrame, news_data: list, sector: str, nifty_data: dict = None) -> dict:
    """Orchestrates the 9-agent pipeline with full data extraction."""
    import sys
    info = {}
    _safe_print(f"[AI] Starting A-grade analysis for {symbol}")
    
    if hasattr(ticker_obj, 'fast_info'):
        try:
            fi = ticker_obj.fast_info
            for attr in ['last_price', 'open', 'previous_close', 'day_high', 'day_low',
                         'year_high', 'year_low', 'market_cap', 'shares', 'currency',
                         'fifty_day_average', 'two_hundred_day_average']:
                try:
                    val = getattr(fi, attr, None)
                    if val is not None:
                        info[attr] = val
                except Exception:
                    pass
        except Exception as e:
            _safe_print(f"[AI] fast_info error: {e}")
    
    if hasattr(ticker_obj, 'info'):
        try:
            raw_info = ticker_obj.info
            if isinstance(raw_info, dict):
                info.update(raw_info)
            else:
                for key in dir(raw_info):
                    if not key.startswith('_'):
                        try:
                            info[key] = getattr(raw_info, key)
                        except Exception:
                            pass
        except Exception as e:
            _safe_print(f"[AI] info error: {e}")
    
    available_keys = [k for k in info.keys() if info[k] is not None and info[k] != 0 and info[k] != '']
    _safe_print(f"[AI] Info: {len(available_keys)} non-empty fields available")
    
    # Agent 1: Data Collection (extracts ALL 61 data points, with ticker_obj for financials)
    data_ctx = await run_data_agent(symbol, info, history_df, news_data, sector, ticker_obj=ticker_obj)
    
    _safe_print(f"[AI] Data agent complete. Technicals: {len(data_ctx.get('technicals', {}))} fields, "
          f"Risk: {len(data_ctx.get('risk_metrics', {}))} fields, "
          f"DCF: {data_ctx.get('dcf_valuation', {}).get('dcf_intrinsic_value')}")
    
    # Concurrent execution for independent agents 2-7
    tasks = [
        run_fundamental_agent(data_ctx),
        run_technical_agent(data_ctx),
        run_news_agent(data_ctx),
        run_macro_agent(data_ctx),
        run_quant_agent(data_ctx),
        run_risk_agent(data_ctx)
    ]
    results = await asyncio.gather(*tasks)
    
    agents_output = {
        "fundamental": results[0],
        "technical": results[1],
        "news": results[2],
        "macro": results[3],
        "quant": results[4],
        "risk": results[5]
    }
    
    # Agent 8: Trade Execution
    execution = await run_trade_structuring_agent(data_ctx)
    agents_output["execution"] = execution
    
    # Agent 9: Master CIO
    cio_report = await run_master_cio_agent(symbol, agents_output)
    
    _safe_print(f"[AI] Analysis complete for {symbol}. Decision: {cio_report.get('final_decision')}")
    
    return {
        "symbol": symbol,
        "agents": agents_output,
        "cio_report": cio_report
    }


# ═══════════════════════════════════════════════════════════════════
#  FALLBACK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def generate_signals(history_df, news_data):
    return {"signal": "HOLD", "reason": "Basic fallback signal", "metrics": {}}

def project_future_prices(history_df, days_ahead=30):
    if history_df.empty: return []
    last_price = history_df['Close'].iloc[-1]
    return [{"date": f"Day {i}", "close": round(last_price * (1 + (np.random.randn() * 0.01)), 2)} for i in range(1, days_ahead + 1)]
