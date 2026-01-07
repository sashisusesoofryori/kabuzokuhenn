import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import time
import json
import os
from pathlib import Path
import yfinance as yf
import re

# ページ設定
st.set_page_config(
    page_title="株最強分析くん",
    page_icon="📊",
    layout="wide"
)

# データ保存用のディレクトリ作成
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "analysis_history.json"
RANKING_FILE = DATA_DIR / "monthly_ranking.json"

# スタイル設定
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .score-display {
        font-size: 4rem;
        font-weight: bold;
        text-align: center;
        margin: 1rem 0;
    }
    .metric-card {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

class StockAnalyzer:
    def __init__(self):
        self.base_url = "https://irbank.net"
        # ヘッダーをブラウザに偽装してブロックを回避
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
    def fetch_irbank_data(self, stock_code):
        """IRBANKから財務データを取得"""
        url = f"{self.base_url}/{stock_code}"
        
        try:
            time.sleep(1)  # サーバー負荷軽減
            # pandasのread_htmlを使ってテーブルを一括取得
            dfs = pd.read_html(url, encoding='utf-8', header=0)
            
            # 企業名取得用
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            company_name = self._extract_company_name(soup, stock_code)
            
            data = {
                'company_name': company_name,
                'revenue': [], 'eps': [], 'total_assets': [], 
                'operating_cf': [], 'cash': [], 'roe': [], 
                'equity_ratio': [], 'dividend': [], 'payout_ratio': [],
                'years': []
            }

            keywords = {
                'revenue': '売上高', 'eps': 'EPS', 'total_assets': '総資産',
                'operating_cf': '営業CF', 'cash': '現金等', 'roe': 'ROE',
                'equity_ratio': '自己資本比率', 'dividend': '配当', 'payout_ratio': '配当性向'
            }

            # 各テーブルからデータを検索
            for key, keyword in keywords.items():
                for df in dfs:
                    if df.apply(lambda x: x.astype(str).str.contains(keyword, na=False)).any().any():
                        found_values = self._find_values_in_df(df, keyword)
                        if found_values:
                            data[key] = found_values[-5:] # 最新5年

            # 必須データが取れていない場合はNoneを返す
            if not data['revenue']:
                return None

            # 年度の設定
            current_year = datetime.now().year
            data['years'] = list(range(current_year - 4, current_year + 1))
            return data
            
        except Exception as e:
            st.error(f"データ取得に失敗しました: {str(e)}")
            return None

    def _find_values_in_df(self, df, keyword):
        """DataFrameからキーワード行の数値を抽出"""
        try:
            mask = df.apply(lambda x: x.astype(str).str.contains(keyword, na=False)).any(axis=1)
            target_rows = df[mask]
            if target_rows.empty: return []
            
            row = target_rows.iloc[0]
            values = []
            for item in row:
                val = self._parse_number(str(item))
                if val is not None: values.append(val)
            return values
        except: return []

    def _extract_company_name(self, soup, stock_code):
        try:
            title = soup.find('h1')
            if title: return title.text.strip()
        except: pass
        return f"企業コード{stock_code}"
    
    def _parse_number(self, text):
        try:
            text = re.sub(r'[,円億万百千%]', '', text).strip()
            if text and text != '-' and text.replace('.','',1).replace('-','',1).isdigit():
                return float(text)
        except: pass
        return None
    
    def fetch_stock_price(self, stock_code, period='5y', interval='1d'):
        try:
            ticker = f"{stock_code}.T"
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            return df
        except: return None

    def calculate_score(self, data):
        """100点満点でスコアを算出"""
        score_details = {}
        # 判定ロジック
        score_details['revenue'] = 15 if self._is_increasing(data.get('revenue', [])) else 0
        score_details['eps'] = 15 if self._is_increasing(data.get('eps', [])) else 0
        score_details['total_assets'] = 10 if self._is_increasing(data.get('total_assets', [])) else 0
        
        op_cf = data.get('operating_cf', [])
        score_details['operating_cf'] = 10 if (all(x > 0 for x in op_cf) and self._is_increasing(op_cf)) else 0
        
        score_details['cash'] = 10 if self._is_increasing(data.get('cash', [])) else 0
        score_details['roe'] = 10 if all(x >= 7 for x in data.get('roe', [])) else 0
        score_details['equity_ratio'] = 10 if all(x >= 50 for x in data.get('equity_ratio', [])) else 0
        score_details['dividend'] = 10 if self._is_non_decreasing(data.get('dividend', [])) else 0
        score_details['payout_ratio'] = 10 if all(x <= 40 for x in data.get('payout_ratio', [])) else 0
        
        total_score = sum(score_details.values())
        return total_score, score_details
    
    def _is_increasing(self, values):
        if not values or len(values) < 2: return False
        return all(values[i] < values[i+1] for i in range(len(values)-1))
    
    def _is_non_decreasing(self, values):
        if not values or len(values) < 2: return True
        return all(values[i] <= values[i+1] for i in range(len(values)-1))

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(stock_code, company_name, score, score_details):
    history = load_history()
    entry = {
        'stock_code': stock_code, 'company_name': company_name,
        'score': score, 'score_details': score_details,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    history.append(entry)
    history = history[-100:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def create_score_chart(score):
    color = '#ff4444' if score < 50 else '#ffaa00' if score < 70 else '#00cc66'
    fig = go.Figure(data=[go.Pie(
        values=[score, 100-score], labels=['スコア', ''], hole=0.7,
        marker_colors=[color, '#e0e0e0'], textinfo='none'
    )])
    fig.add_annotation(text=f'{score}<br>点', x=0.5, y=0.5, font_size=40, showarrow=False)
    fig.update_layout(showlegend=False, height=400, margin=dict(t=0, b=0, l=0, r=0))
    return fig

def create_trend_chart(data, metric_name, years):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=data, mode='lines+markers', name=metric_name))
    fig.update_layout(title=f'{metric_name}の推移', height=300, template='plotly_white')
    return fig

def create_stock_price_chart(df, timeframe_label):
    if df is None or df.empty: return None
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
    fig.update_layout(title=f'株価推移 ({timeframe_label})', height=400, template='plotly_white', xaxis_rangeslider_visible=False)
    return fig

# メインエリア表示
st.markdown('<div class="main-header">📊 株最強分析くん</div>', unsafe_allow_html=True)
analyzer = StockAnalyzer()

with st.sidebar:
    st.header("⚙️ 設定")
    stock_code = st.text_input("銘柄コード", value="", placeholder="例: 7203")
    timeframe_options = {
        "日足（1年）": ("1y", "1d"), "週足（5年）": ("5y", "1wk"), "月足（MAX）": ("max", "1mo")
    }
    timeframe = st.selectbox("時間軸を選択", list(timeframe_options.keys()), index=0)
    analyze_button = st.button("🔍 分析開始", type="primary", use_container_width=True)
    history = load_history()

if analyze_button and stock_code:
    with st.spinner('データ取得中...'):
        data = analyzer.fetch_irbank_data(stock_code)
        
        if data is not None:
            score, score_details = analyzer.calculate_score(data)
            save_history(stock_code, data['company_name'], score, score_details)
            period, interval = timeframe_options[timeframe]
            stock_df = analyzer.fetch_stock_price(stock_code, period, interval)
            
            st.success(f"✅ {data['company_name']} の分析が完了しました！")
            
            if stock_df is not None:
                st.plotly_chart(create_stock_price_chart(stock_df, timeframe), use_container_width=True)
            
            st.plotly_chart(create_score_chart(score), use_container_width=True)
            
            # 詳細評価の表示
            cols = st.columns(3)
            criteria = {
                'revenue': '経常収益', 'eps': 'EPS', 'total_assets': '総資産',
                'operating_cf': '営業CF', 'cash': '現金等', 'roe': 'ROE',
                'equity_ratio': '自己資本比率', 'dividend': '1株配当', 'payout_ratio': '配当性向'
            }
            for i, (key, name) in enumerate(criteria.items()):
                with cols[i % 3]:
                    st.info(f"{name}: {score_details[key]}点")
        else:
            st.error("財務データが取得できませんでした。IRBANKからブロックされているか、銘柄コードが正しくない可能性があります。")

elif not stock_code and analyze_button:
    st.warning("⚠️ 銘柄コードを入力してください")

# フッター
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666;'>投資判断は自己責任でお願いします。</div>", unsafe_allow_html=True)
