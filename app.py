from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import requests
import math
import statistics

app = FastAPI(title="CandleVision AI Pro", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

BINANCE_BASE = "https://api.binance.com"

class AnalyzeRequest(BaseModel):
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    limit: int = 250

VALID_INTERVALS = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w"}
VALID_SYMBOL = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

def get_klines(symbol: str, interval: str, limit: int = 250):
    symbol = symbol.upper().strip()
    if not symbol or any(ch not in VALID_SYMBOL for ch in symbol):
        raise HTTPException(400, "نماد نامعتبر است.")
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, "تایم‌فریم پشتیبانی نمی‌شود.")
    limit = max(60, min(int(limit), 1000))
    try:
        r = requests.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=12,
            headers={"User-Agent": "CandleVisionAIPro/0.1"}
        )
        r.raise_for_status()
        raw = r.json()
    except requests.RequestException:
        raise HTTPException(502, "دریافت داده از منبع بازار ناموفق بود. اتصال یا دسترسی به API را بررسی کن.")
    except ValueError:
        raise HTTPException(502, "پاسخ منبع داده قابل‌خواندن نیست.")
    if not isinstance(raw, list) or len(raw) < 60:
        raise HTTPException(502, "داده کافی از منبع بازار دریافت نشد.")
    return [{
        "time": int(k[0] // 1000),
        "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
        "close": float(k[4]), "volume": float(k[5]),
        "close_time": int(k[6] // 1000)
    } for k in raw]

def ichimoku(candles):
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]
    def midrange(end, period):
        start = max(0, end-period+1)
        return (max(highs[start:end+1]) + min(lows[start:end+1])) / 2
    out = []
    for i in range(len(candles)):
        tenkan = midrange(i, 9) if i >= 8 else None
        kijun = midrange(i, 26) if i >= 25 else None
        span_b = midrange(i, 52) if i >= 51 else None
        span_a = (tenkan + kijun)/2 if tenkan is not None and kijun is not None else None
        out.append({"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b})
    return out

def find_pivots(candles, left=3, right=3):
    highs, lows = [], []
    for i in range(left, len(candles)-right):
        h, l = candles[i]["high"], candles[i]["low"]
        if all(h > candles[j]["high"] for j in range(i-left, i)) and all(h >= candles[j]["high"] for j in range(i+1, i+right+1)):
            highs.append({"index": i, "price": h, "time": candles[i]["time"]})
        if all(l < candles[j]["low"] for j in range(i-left, i)) and all(l <= candles[j]["low"] for j in range(i+1, i+right+1)):
            lows.append({"index": i, "price": l, "time": candles[i]["time"]})
    return highs, lows

def candle_pattern(candles):
    a, b = candles[-2], candles[-1]
    body = abs(b["close"] - b["open"])
    rng = max(b["high"] - b["low"], 1e-12)
    upper = b["high"] - max(b["open"], b["close"])
    lower = min(b["open"], b["close"]) - b["low"]
    prev_body = abs(a["close"] - a["open"])
    pattern = "الگوی مشخص و قوی شناسایی نشد"
    if body/rng < 0.10:
        pattern = "دوجی احتمالی"
    elif lower >= body*2 and upper <= max(body*0.7, rng*0.05) and b["close"] > b["open"]:
        pattern = "چکش/پین‌بار صعودی احتمالی"
    elif upper >= body*2 and lower <= max(body*0.7, rng*0.05) and b["close"] < b["open"]:
        pattern = "ستاره/پین‌بار نزولی احتمالی"
    elif a["close"] < a["open"] and b["close"] > b["open"] and b["open"] <= a["close"] and b["close"] >= a["open"] and body > prev_body:
        pattern = "پوشای صعودی"
    elif a["close"] > a["open"] and b["close"] < b["open"] and b["open"] >= a["close"] and b["close"] <= a["open"] and body > prev_body:
        pattern = "پوشای نزولی"
    return {"name": pattern, "body_ratio": round(body/rng, 3), "upper_wick_ratio": round(upper/rng, 3), "lower_wick_ratio": round(lower/rng, 3)}

def analyze(candles):
    closes = [c["close"] for c in candles]
    last = candles[-1]
    prev = candles[-2]
    ichi = ichimoku(candles)
    ic = ichi[-1]
    highs, lows = find_pivots(candles)
    # A deliberately transparent baseline, not a trained forecasting model.
    recent = closes[-8:]
    momentum = (recent[-1] - recent[0]) / max(recent[0], 1e-12)
    recent_range = statistics.mean([x["high"] - x["low"] for x in candles[-14:]])
    pattern = candle_pattern(candles)
    score = 0.0
    reasons = []
    if momentum > 0:
        score += 0.25
        reasons.append("شتاب ۸ کندل اخیر مثبت است")
    elif momentum < 0:
        score -= 0.25
        reasons.append("شتاب ۸ کندل اخیر منفی است")
    if ic["tenkan"] and ic["kijun"]:
        if ic["tenkan"] > ic["kijun"]:
            score += 0.20
            reasons.append("تنکان‌سن بالاتر از کیجون‌سن است")
        else:
            score -= 0.20
            reasons.append("تنکان‌سن پایین‌تر از کیجون‌سن است")
    if ic["span_a"] and ic["span_b"]:
        cloud_top, cloud_bottom = max(ic["span_a"], ic["span_b"]), min(ic["span_a"], ic["span_b"])
        if last["close"] > cloud_top:
            score += 0.20
            reasons.append("قیمت بالای ابر کومو قرار دارد")
        elif last["close"] < cloud_bottom:
            score -= 0.20
            reasons.append("قیمت پایین ابر کومو قرار دارد")
        else:
            reasons.append("قیمت داخل ابر کومو است")
    if "صعودی" in pattern["name"] or pattern["name"] == "پوشای صعودی":
        score += 0.15
        reasons.append("الگوی کندلی با سوگیری صعودی شناسایی شد")
    elif "نزولی" in pattern["name"] or pattern["name"] == "پوشای نزولی":
        score -= 0.15
        reasons.append("الگوی کندلی با سوگیری نزولی شناسایی شد")
    direction = "صعودی" if score > 0.12 else ("نزولی" if score < -0.12 else "خنثی/نامشخص")
    # These are heuristic scores, intentionally not represented as calibrated probabilities.
    confidence = min(78, max(35, int(50 + abs(score)*45)))
    close_est = last["close"] * (1 + max(-0.008, min(0.008, momentum * 0.35)))
    range_est = max(recent_range, last["close"] * 0.001)
    cloud_state = "داده ناکافی" if not ic["span_a"] or not ic["span_b"] else (
        "بالای ابر" if last["close"] > max(ic["span_a"], ic["span_b"]) else
        "پایین ابر" if last["close"] < min(ic["span_a"], ic["span_b"]) else "داخل ابر"
    )
    return {
        "symbol": "", "interval": "", "last_price": last["close"],
        "direction": direction, "heuristic_score": round(score, 3),
        "confidence_label": "تخمین اولیه؛ هنوز کالیبره نشده",
        "confidence_score": confidence,
        "next_candle_estimate": {
            "open": last["close"],
            "high_zone": [round(max(last["close"], close_est) + range_est*0.2, 8), round(max(last["close"], close_est) + range_est, 8)],
            "low_zone": [round(min(last["close"], close_est) - range_est, 8), round(min(last["close"], close_est) - range_est*0.2, 8)],
            "close_estimate": round(close_est, 8)
        },
        "pattern": pattern,
        "ichimoku": {
            "tenkan": ic["tenkan"], "kijun": ic["kijun"],
            "span_a": ic["span_a"], "span_b": ic["span_b"],
            "price_vs_cloud": cloud_state
        },
        "trend_points": {"swing_highs": highs[-8:], "swing_lows": lows[-8:]},
        "reasons": reasons,
        "warnings": [
            "این نسخه نمونه اولیه است؛ مدل یادگیری ماشین آموزش‌دیده و اعتبارسنجی‌شده نیست.",
            "مقادیر سقف/کف محدوده‌های تقریبی مبتنی بر نوسان اخیرند و تضمین آماری ندارند.",
            "آخرین کندل دریافتی ممکن است هنوز بسته نشده باشد؛ برای ارزیابی از کندل‌های بسته‌شده استفاده کن."
        ]
    }

@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0", "mode": "prototype"}

@app.post("/api/analyze")
def analyze_market(req: AnalyzeRequest):
    candles = get_klines(req.symbol, req.interval, req.limit)
    result = analyze(candles)
    result["symbol"] = req.symbol.upper()
    result["interval"] = req.interval
    result["candles"] = candles
    return result

@app.post("/api/analyze-image")
async def analyze_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "لطفاً یک فایل تصویری ارسال کن.")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "حداکثر اندازه تصویر ۸ مگابایت است.")
    # Vision processing is intentionally not faked: this endpoint validates upload only.
    # Next implementation step: chart OCR/vision and alignment with exchange OHLCV data.
    return {
        "status": "received",
        "filename": file.filename,
        "bytes": len(data),
        "message": "تصویر دریافت شد؛ تحلیل تصویری در این نسخه هنوز پیاده‌سازی نشده است. برای تحلیل فعلی از نماد و تایم‌فریم استفاده کن."
    }
