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
    class StockAnalyzer:
    def __init__(self):
        self.base_url = "https://irbank.net"
        # ヘッダーをブラウザに偽装（ブロック回避のため強化）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
    def fetch_irbank_data(self, stock_code):
        """IRBANKから財務データを取得"""
        url = f"{self.base_url}/{stock_code}"
        
        try:
            time.sleep(1)  # サーバー負荷軽減
            # pandasのread_htmlを使ってテーブルを一括取得（より強力）
            dfs = pd.read_html(url, encoding='utf-8', header=0)
            
            # 企業名取得用（ここはrequestsを使う）
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            company_name = self._extract_company_name(soup, stock_code)
            
            # データ格納用辞書
            data = {
                'company_name': company_name,
                'revenue': [], 'eps': [], 'total_assets': [], 
                'operating_cf': [], 'cash': [], 'roe': [], 
                'equity_ratio': [], 'dividend': [], 'payout_ratio': [],
                'years': []
            }

            # 取得した全テーブルから必要なデータを探す
            # IRBANKの構造に合わせてキーワード検索
            keywords = {
                'revenue': '売上高',
                'eps': 'EPS',
                'total_assets': '総資産',
                'operating_cf': '営業CF',
                'cash': '現金等',
                'roe': 'ROE',
                'equity_ratio': '自己資本比率',
                'dividend': '配当',
                'payout_ratio': '配当性向'
            }

            for key, keyword in keywords.items():
                for df in dfs:
                    # データフレームの中にキーワードが含まれているか
                    # 文字列型にして検索
                    if df.apply(lambda x: x.astype(str).str.contains(keyword, na=False)).any().any():
                        # キーワードがある行を特定
                        # 注: IRBANKのテーブル構造に依存しますが、多くのケースでこれで拾えます
                        found_values = self._find_values_in_df(df, keyword)
                        if found_values:
                            data[key] = found_values[-5:] # 最新5年

            # データが空の場合はエラー扱い
            if not data['revenue']:
                raise ValueError("財務データが見つかりませんでした")

            # 年度の設定（簡易的に現在から過去5年）
            current_year = datetime.now().year
            data['years'] = list(range(current_year - 4, current_year + 1))
            
            return data
            
        except Exception as e:
            st.error(f"データ取得エラー: {str(e)}")
            st.warning("⚠️ Streamlit CloudのIPがIRBANKにブロックされているか、データが存在しません。")
            return None # ダミーデータではなくNoneを返す

    def _find_values_in_df(self, df, keyword):
        """DataFrameから特定のキーワードの行の数値を抽出"""
        try:
            # キーワードを含む行を探す
            mask = df.apply(lambda x: x.astype(str).str.contains(keyword, na=False)).any(axis=1)
            target_rows = df[mask]
            
            if target_rows.empty:
                return []
            
            # 最初のヒット行を使用
            row = target_rows.iloc[0]
            values = []
            
            # 行の各セルを数値変換してリスト化
            for item in row:
                val = self._parse_number(str(item))
                if val is not None:
                    values.append(val)
            
            return values
        except:
            return []

    def _extract_company_name(self, soup, stock_code):
        """企業名を抽出"""
        try:
            title = soup.find('h1')
            if title:
                return title.text.strip()
        except:
            pass
        return f"企業コード{stock_code}"
    
    def _parse_number(self, text):
        """テキストから数値を抽出"""
        try:
            # カンマや単位、%を除去
            text = re.sub(r'[,円億万百千%]', '', text)
            text = text.strip()
            # 年号やテキストを除外して数値のみ抽出
            if text and text != '-' and text.replace('.','',1).isdigit():
                return float(text)
        except:
            pass
        return None
    def calculate_score(self, data):
        """100点満点でスコアを算出"""
        score_details = {}
        
        # 1. 経常収益 (15点)
        score_details['revenue'] = 15 if self._is_increasing(data['revenue']) else 0
        
        # 2. EPS (15点)
        score_details['eps'] = 15 if self._is_increasing(data['eps']) else 0
        
        # 3. 総資産 (10点)
        score_details['total_assets'] = 10 if self._is_increasing(data['total_assets']) else 0
        
        # 4. 営業CF (10点)
        score_details['operating_cf'] = 10 if (all(x > 0 for x in data['operating_cf']) and 
                                                 self._is_increasing(data['operating_cf'])) else 0
        
        # 5. 現金等 (10点)
        score_details['cash'] = 10 if self._is_increasing(data['cash']) else 0
        
        # 6. ROE (10点)
        score_details['roe'] = 10 if all(x >= 7 for x in data['roe']) else 0
        
        # 7. 自己資本比率 (10点)
        score_details['equity_ratio'] = 10 if all(x >= 50 for x in data['equity_ratio']) else 0
        
        # 8. 1株配当 (10点)
        score_details['dividend'] = 10 if self._is_non_decreasing(data['dividend']) else 0
        
        # 9. 配当性向 (10点)
        score_details['payout_ratio'] = 10 if all(x <= 40 for x in data['payout_ratio']) else 0
        
        total_score = sum(score_details.values())
        return total_score, score_details
    
    def _is_increasing(self, values):
        """右肩上がりかチェック"""
        if len(values) < 2:
            return False
        return all(values[i] < values[i+1] for i in range(len(values)-1))
    
    def _is_non_decreasing(self, values):
        """非減少（維持または増加）かチェック"""
        if len(values) < 2:
            return True
        return all(values[i] <= values[i+1] for i in range(len(values)-1))

def load_history():
    """分析履歴を読み込み"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(stock_code, company_name, score, score_details):
    """分析履歴を保存"""
    history = load_history()
    entry = {
        'stock_code': stock_code,
        'company_name': company_name,
        'score': score,
        'score_details': score_details,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    history.append(entry)
    
    # 最新100件のみ保持
    history = history[-100:]
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def save_to_github():
    """GitHub連携用の保存処理"""
    # Git操作はStreamlit Cloudの環境で自動的に処理される
    # ローカル環境では手動でコミット・プッシュが必要
    pass

def create_score_chart(score):
    """スコア表示用円グラフ"""
    color = '#ff4444' if score < 50 else '#ffaa00' if score < 70 else '#00cc66'
    
    fig = go.Figure(data=[go.Pie(
        values=[score, 100-score],
        labels=['スコア', ''],
        hole=0.7,
        marker_colors=[color, '#e0e0e0'],
        textinfo='none',
        hoverinfo='label+value'
    )])
    
    fig.add_annotation(
        text=f'{score}<br>点',
        x=0.5, y=0.5,
        font_size=40,
        showarrow=False
    )
    
    fig.update_layout(
        showlegend=False,
        height=400,
        margin=dict(t=0, b=0, l=0, r=0)
    )
    return fig

def create_trend_chart(data, metric_name, years):
    """推移グラフ作成"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years,
        y=data,
        mode='lines+markers',
        name=metric_name,
        line=dict(width=3),
        marker=dict(size=10),
        fill='tonexty',
        fillcolor='rgba(31, 119, 180, 0.2)'
    ))
    
    fig.update_layout(
        title=f'{metric_name}の推移',
        xaxis_title='年度',
        yaxis_title='値',
        height=300,
        hovermode='x unified',
        template='plotly_white'
    )
    return fig

def create_stock_price_chart(df, timeframe_label):
    """株価チャート作成"""
    if df is None or df.empty:
        return None
    
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='株価'
    )])
    
    fig.update_layout(
        title=f'株価推移 ({timeframe_label})',
        yaxis_title='株価 (円)',
        xaxis_title='日付',
        height=400,
        template='plotly_white',
        xaxis_rangeslider_visible=False
    )
    return fig

# メインアプリケーション
st.markdown('<div class="main-header">📊 株最強分析くん</div>', unsafe_allow_html=True)

analyzer = StockAnalyzer()

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    stock_code = st.text_input("銘柄コード", value="", placeholder="例: 7203")
    
    st.markdown("---")
    st.subheader("📈 株価表示期間")
    
    timeframe_options = {
        "5分足": ("5d", "5m"),
        "15分足": ("5d", "15m"),
        "1時間足": ("1mo", "1h"),
        "日足（1週間）": ("7d", "1d"),
        "日足（1ヶ月）": ("1mo", "1d"),
        "日足（1年）": ("1y", "1d"),
        "週足（5年）": ("5y", "1wk"),
        "月足（MAX）": ("max", "1mo")
    }
    
    timeframe = st.selectbox(
        "時間軸を選択",
        list(timeframe_options.keys()),
        index=6
    )
    
    analyze_button = st.button("🔍 分析開始", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.subheader("📜 分析履歴")
    history = load_history()
    if history:
        for entry in reversed(history[-5:]):
            with st.expander(f"{entry['company_name']} ({entry['stock_code']})"):
                st.metric("スコア", f"{entry['score']}点")
                st.caption(entry['date'])
    else:
        st.info("履歴がありません")
    
    st.markdown("---")
    if st.button("💾 データをエクスポート"):
        st.download_button(
            label="履歴をダウンロード",
            data=json.dumps(history, ensure_ascii=False, indent=2),
            file_name=f"stock_analysis_history_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json"
        )

# メインエリア
if analyze_button and stock_code:
    with st.spinner('データ取得中...'):
        # 財務データ取得
        data = analyzer.fetch_irbank_data(stock_code)
        score, score_details = analyzer.calculate_score(data)
        save_history(stock_code, data['company_name'], score, score_details)
        
        # 株価データ取得
        period, interval = timeframe_options[timeframe]
        stock_df = analyzer.fetch_stock_price(stock_code, period, interval)
    
    st.success(f"✅ {data['company_name']} の分析が完了しました！")
    
    # 株価チャート表示
    if stock_df is not None:
        st.subheader("💹 株価チャート")
        stock_chart = create_stock_price_chart(stock_df, timeframe)
        if stock_chart:
            st.plotly_chart(stock_chart, use_container_width=True)
        
        # 簡易統計
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("現在値", f"{stock_df['Close'].iloc[-1]:.2f}円")
        with col2:
            change = stock_df['Close'].iloc[-1] - stock_df['Close'].iloc[-2]
            change_pct = (change / stock_df['Close'].iloc[-2]) * 100
            st.metric("前日比", f"{change:.2f}円", f"{change_pct:+.2f}%")
        with col3:
            st.metric("期間高値", f"{stock_df['High'].max():.2f}円")
        with col4:
            st.metric("期間安値", f"{stock_df['Low'].min():.2f}円")
    
    st.markdown("---")
    
    # スコア表示
    st.subheader("🎯 総合評価スコア")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.plotly_chart(create_score_chart(score), use_container_width=True)
    
    # 評価コメント
    if score >= 80:
        st.success("🌟 優良企業！非常に高い投資価値が期待できます。")
    elif score >= 60:
        st.info("👍 良好な財務状態です。")
    elif score >= 40:
        st.warning("⚠️ 一部改善の余地があります。")
    else:
        st.error("❌ 慎重な判断が必要です。")
    
    # 詳細スコア
    st.subheader("📋 詳細評価")
    
    criteria = {
        'revenue': ('経常収益', '右肩上がり', 15),
        'eps': ('EPS', '右肩上がり', 15),
        'total_assets': ('総資産', '増加傾向', 10),
        'operating_cf': ('営業CF', 'プラス＆増加', 10),
        'cash': ('現金等', '積み上がり', 10),
        'roe': ('ROE', '7%以上', 10),
        'equity_ratio': ('自己資本比率', '50%以上', 10),
        'dividend': ('1株配当', '非減配', 10),
        'payout_ratio': ('配当性向', '40%以下', 10)
    }
    
    cols = st.columns(3)
    for idx, (key, (name, criteria_text, max_score)) in enumerate(criteria.items()):
        with cols[idx % 3]:
            achieved = score_details[key]
            status = "✅ 合格" if achieved == max_score else "❌ 不合格"
            color = "#d4edda" if achieved == max_score else "#f8d7da"
            st.markdown(f"""
            <div style="padding: 1rem; border-radius: 0.5rem; background-color: {color}; margin: 0.5rem 0;">
                <strong>{name}</strong><br>
                {status} ({achieved}/{max_score}点)<br>
                <small>基準: {criteria_text}</small>
            </div>
            """, unsafe_allow_html=True)
    
    # 推移グラフ
    st.subheader("📊 財務指標の推移")
    
    tab1, tab2, tab3, tab4 = st.tabs(["収益性", "資産・CF", "健全性", "配当"])
    
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_trend_chart(data['revenue'], '経常収益', data['years']), use_container_width=True)
        with col2:
            st.plotly_chart(create_trend_chart(data['eps'], 'EPS', data['years']), use_container_width=True)
    
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_trend_chart(data['total_assets'], '総資産', data['years']), use_container_width=True)
        with col2:
            st.plotly_chart(create_trend_chart(data['operating_cf'], '営業CF', data['years']), use_container_width=True)
    
    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_trend_chart(data['roe'], 'ROE (%)', data['years']), use_container_width=True)
        with col2:
            st.plotly_chart(create_trend_chart(data['equity_ratio'], '自己資本比率 (%)', data['years']), use_container_width=True)
    
    with tab4:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_trend_chart(data['dividend'], '1株配当', data['years']), use_container_width=True)
        with col2:
            st.plotly_chart(create_trend_chart(data['payout_ratio'], '配当性向 (%)', data['years']), use_container_width=True)

elif not stock_code and analyze_button:
    st.warning("⚠️ 銘柄コードを入力してください")
else:
    st.info("👈 サイドバーから銘柄コードを入力して分析を開始してください")

# ランキング表示
st.markdown("---")
st.subheader("🏆 月間スコアランキング")

if history:
    df = pd.DataFrame(history)
    df['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    
    current_month = datetime.now().strftime('%Y-%m')
    monthly_data = df[df['month'] == current_month].sort_values('score', ascending=False)
    
    if not monthly_data.empty:
        # 重複する銘柄は最新のもののみ表示
        monthly_data = monthly_data.drop_duplicates(subset=['stock_code'], keep='first')
        
        display_df = monthly_data[['stock_code', 'company_name', 'score', 'date']].head(10)
        display_df = display_df.rename(columns={
            'stock_code': '銘柄コード',
            'company_name': '企業名',
            'score': 'スコア',
            'date': '分析日時'
        })
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("今月の分析データがありません")
else:
    st.info("ランキングデータがありません")

# フッター
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9rem;'>
    <p>💡 このアプリは財務データに基づく独自のスコアリングシステムです。</p>
    <p>投資判断は自己責任でお願いします。IRBANKおよびYahoo Financeからデータを取得しています。</p>
</div>
""", unsafe_allow_html=True)
