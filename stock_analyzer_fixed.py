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
    .debug-info {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
        font-family: monospace;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

class StockAnalyzer:
    def __init__(self):
        self.base_url = "https://irbank.net"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def fetch_irbank_data(self, stock_code):
        """IRBANKから財務データを取得"""
        url = f"{self.base_url}/{stock_code}"
        
        try:
            time.sleep(2)  # サーバー負荷軽減
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 企業名を取得
            company_name = self._extract_company_name(soup, stock_code)
            
            # デバッグ: データ取得状況を表示
            st.info(f"🔍 {company_name} のデータを取得中...")
            
            # 各財務指標を取得
            data = {
                'company_name': company_name,
                'revenue': self._extract_metric(soup, '売上高', '経常収益'),
                'eps': self._extract_metric(soup, 'EPS'),
                'total_assets': self._extract_metric(soup, '総資産'),
                'operating_cf': self._extract_metric(soup, '営業CF', '営業活動によるCF'),
                'cash': self._extract_metric(soup, '現金等', '現金及び現金同等物'),
                'roe': self._extract_metric(soup, 'ROE', '自己資本利益率'),
                'equity_ratio': self._extract_metric(soup, '自己資本比率'),
                'dividend': self._extract_metric(soup, '配当', '1株配当'),
                'payout_ratio': self._extract_metric(soup, '配当性向'),
                'years': []
            }
            
            # 年度を推定
            current_year = datetime.now().year
            data_length = len(data['revenue'])
            data['years'] = list(range(current_year - data_length + 1, current_year + 1))
            
            # データ取得状況を確認
            missing_data = [k for k, v in data.items() if k != 'years' and k != 'company_name' and (not v or len(v) == 0)]
            if missing_data:
                st.warning(f"⚠️ 以下のデータが取得できませんでした: {', '.join(missing_data)}")
                st.info("💡 Yahoo Financeから株価データのみ表示します")
            
            return data
            
        except Exception as e:
            st.error(f"❌ データ取得エラー: {str(e)}")
            st.info("💡 銘柄コードが正しいか確認してください。例: 7203（トヨタ）")
            return None
    
    def _extract_company_name(self, soup, stock_code):
        """企業名を抽出"""
        try:
            # h1タグから企業名を取得
            title = soup.find('h1')
            if title:
                name = title.text.strip()
                # 銘柄コードを除去
                name = re.sub(r'\d{4}', '', name).strip()
                return name
        except:
            pass
        return f"銘柄{stock_code}"
    
    def _extract_metric(self, soup, *metric_names):
        """特定の財務指標を抽出（複数の名称に対応）"""
        try:
            tables = soup.find_all('table', class_='table_style')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if not cells:
                        continue
                    
                    first_cell_text = cells[0].text.strip()
                    
                    # いずれかの指標名にマッチするかチェック
                    if any(metric_name in first_cell_text for metric_name in metric_names):
                        # 数値データを抽出（最新5年分）
                        values = []
                        for cell in cells[1:]:  # 最初のセルはラベル
                            text = cell.text.strip()
                            num = self._parse_number(text)
                            if num is not None:
                                values.append(num)
                        
                        if values:
                            # 最新5年分を取得
                            return values[-5:] if len(values) >= 5 else values
        except Exception as e:
            st.warning(f"データ抽出エラー ({metric_names[0]}): {str(e)}")
        
        return []  # 空のリストを返す
    
    def _parse_number(self, text):
        """テキストから数値を抽出"""
        try:
            # カンマや単位を除去
            text = re.sub(r'[,円億万百千%]', '', text)
            text = text.strip()
            
            # ハイフンや空文字は None
            if text in ['-', '−', '', '―', '—']:
                return None
            
            # 数値に変換
            return float(text)
        except:
            return None
    
    def fetch_stock_price(self, stock_code, period='5y', interval='1d'):
        """yfinanceで株価データを取得"""
        try:
            # 日本株の場合は.Tを付ける
            ticker = f"{stock_code}.T"
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval=interval)
            
            if df.empty:
                st.warning(f"⚠️ 株価データが取得できませんでした（銘柄コード: {stock_code}）")
                return None
            
            return df
        except Exception as e:
            st.warning(f"株価データ取得エラー: {str(e)}")
            return None
    
    def calculate_score(self, data):
        """100点満点でスコアを算出"""
        if not data:
            return 0, {}
        
        score_details = {}
        debug_info = {}
        
        # 1. 経常収益 (15点)
        if len(data['revenue']) >= 2:
            score_details['revenue'] = 15 if self._is_increasing(data['revenue']) else 0
            debug_info['revenue'] = f"データ: {data['revenue']}, 右肩上がり: {self._is_increasing(data['revenue'])}"
        else:
            score_details['revenue'] = 0
            debug_info['revenue'] = "データ不足"
        
        # 2. EPS (15点)
        if len(data['eps']) >= 2:
            score_details['eps'] = 15 if self._is_increasing(data['eps']) else 0
            debug_info['eps'] = f"データ: {data['eps']}, 右肩上がり: {self._is_increasing(data['eps'])}"
        else:
            score_details['eps'] = 0
            debug_info['eps'] = "データ不足"
        
        # 3. 総資産 (10点)
        if len(data['total_assets']) >= 2:
            score_details['total_assets'] = 10 if self._is_increasing(data['total_assets']) else 0
            debug_info['total_assets'] = f"データ: {data['total_assets']}"
        else:
            score_details['total_assets'] = 0
            debug_info['total_assets'] = "データ不足"
        
        # 4. 営業CF (10点)
        if len(data['operating_cf']) >= 2:
            all_positive = all(x > 0 for x in data['operating_cf'] if x is not None)
            is_increasing = self._is_increasing(data['operating_cf'])
            score_details['operating_cf'] = 10 if (all_positive and is_increasing) else 0
            debug_info['operating_cf'] = f"データ: {data['operating_cf']}, 全てプラス: {all_positive}, 増加: {is_increasing}"
        else:
            score_details['operating_cf'] = 0
            debug_info['operating_cf'] = "データ不足"
        
        # 5. 現金等 (10点)
        if len(data['cash']) >= 2:
            score_details['cash'] = 10 if self._is_increasing(data['cash']) else 0
            debug_info['cash'] = f"データ: {data['cash']}"
        else:
            score_details['cash'] = 0
            debug_info['cash'] = "データ不足"
        
        # 6. ROE (10点)
        if len(data['roe']) >= 1:
            all_above_7 = all(x >= 7 for x in data['roe'] if x is not None)
            score_details['roe'] = 10 if all_above_7 else 0
            debug_info['roe'] = f"データ: {data['roe']}, 全て7%以上: {all_above_7}"
        else:
            score_details['roe'] = 0
            debug_info['roe'] = "データ不足"
        
        # 7. 自己資本比率 (10点)
        if len(data['equity_ratio']) >= 1:
            all_above_50 = all(x >= 50 for x in data['equity_ratio'] if x is not None)
            score_details['equity_ratio'] = 10 if all_above_50 else 0
            debug_info['equity_ratio'] = f"データ: {data['equity_ratio']}, 全て50%以上: {all_above_50}"
        else:
            score_details['equity_ratio'] = 0
            debug_info['equity_ratio'] = "データ不足"
        
        # 8. 1株配当 (10点)
        if len(data['dividend']) >= 2:
            score_details['dividend'] = 10 if self._is_non_decreasing(data['dividend']) else 0
            debug_info['dividend'] = f"データ: {data['dividend']}, 非減配: {self._is_non_decreasing(data['dividend'])}"
        else:
            score_details['dividend'] = 0
            debug_info['dividend'] = "データ不足"
        
        # 9. 配当性向 (10点)
        if len(data['payout_ratio']) >= 1:
            all_below_40 = all(x <= 40 for x in data['payout_ratio'] if x is not None)
            score_details['payout_ratio'] = 10 if all_below_40 else 0
            debug_info['payout_ratio'] = f"データ: {data['payout_ratio']}, 全て40%以下: {all_below_40}"
        else:
            score_details['payout_ratio'] = 0
            debug_info['payout_ratio'] = "データ不足"
        
        total_score = sum(score_details.values())
        return total_score, score_details, debug_info
    
    def _is_increasing(self, values):
        """右肩上がりかチェック（Noneを除外）"""
        if len(values) < 2:
            return False
        
        # Noneを除外
        valid_values = [v for v in values if v is not None]
        if len(valid_values) < 2:
            return False
        
        # 連続する値が全て増加しているかチェック
        return all(valid_values[i] < valid_values[i+1] for i in range(len(valid_values)-1))
    
    def _is_non_decreasing(self, values):
        """非減少（維持または増加）かチェック"""
        if len(values) < 2:
            return True
        
        # Noneを除外
        valid_values = [v for v in values if v is not None]
        if len(valid_values) < 2:
            return True
        
        return all(valid_values[i] <= valid_values[i+1] for i in range(len(valid_values)-1))

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
    if not data or len(data) == 0:
        return None
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years[-len(data):],
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
        "日足(1週間)": ("7d", "1d"),
        "日足(1ヶ月)": ("1mo", "1d"),
        "日足(1年)": ("1y", "1d"),
        "週足(5年)": ("5y", "1wk"),
        "月足(MAX)": ("max", "1mo")
    }
    
    timeframe = st.selectbox(
        "時間軸を選択",
        list(timeframe_options.keys()),
        index=6
    )
    
    show_debug = st.checkbox("🔍 デバッグ情報を表示", value=False)
    
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
        
        if data is None:
            st.error("❌ 財務データの取得に失敗しました")
            st.stop()
        
        score, score_details, debug_info = analyzer.calculate_score(data)
        save_history(stock_code, data['company_name'], score, score_details)
        
        # 株価データ取得
        period, interval = timeframe_options[timeframe]
        stock_df = analyzer.fetch_stock_price(stock_code, period, interval)
    
    st.success(f"✅ {data['company_name']} の分析が完了しました!")
    
    # デバッグ情報表示
    if show_debug:
        st.markdown("### 🔍 デバッグ情報")
        with st.expander("取得データの詳細", expanded=True):
            st.json(debug_info)
    
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
        st.success("🌟 優良企業!非常に高い投資価値が期待できます。")
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
        'operating_cf': ('営業CF', 'プラス&増加', 10),
        'cash': ('現金等', '積み上がり', 10),
        'roe': ('ROE', '7%以上', 10),
        'equity_ratio': ('自己資本比率', '50%以上', 10),
        'dividend': ('1株配当', '非減配', 10),
        'payout_ratio': ('配当性向', '40%以下', 10)
    }
    
    cols = st.columns(3)
    for idx, (key, (name, criteria_text, max_score)) in enumerate(criteria.items()):
        with cols[idx % 3]:
            achieved = score_details.get(key, 0)
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
            chart = create_trend_chart(data['revenue'], '経常収益', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
        with col2:
            chart = create_trend_chart(data['eps'], 'EPS', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
    
    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            chart = create_trend_chart(data['total_assets'], '総資産', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
        with col2:
            chart = create_trend_chart(data['operating_cf'], '営業CF', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
    
    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            chart = create_trend_chart(data['roe'], 'ROE (%)', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
        with col2:
            chart = create_trend_chart(data['equity_ratio'], '自己資本比率 (%)', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
    
    with tab4:
        col1, col2 = st.columns(2)
        with col1:
            chart = create_trend_chart(data['dividend'], '1株配当', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")
        with col2:
            chart = create_trend_chart(data['payout_ratio'], '配当性向 (%)', data['years'])
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info("データがありません")

elif not stock_code and analyze_button:
    st.warning("⚠️ 銘柄コードを入力してください")
else:
    st.info("👈 サイドバーから銘柄コードを入力して分析を開始してください")
    
    # 使い方ガイド
    with st.expander("📖 使い方ガイド"):
        st.markdown("""
        ### 銘柄コードの入力例
        - **トヨタ自動車**: 7203
        - **ソニーグループ**: 6758
        - **任天堂**: 7974
        - **キーエンス**: 6861
        
        ### スコアリング基準
        各項目を評価し、100点満点で採点します:
        
        1. **経常収益** (15点) - 右肩上がりの成長
        2. **EPS** (15点) - 1株あたり利益の増加
        3. **総資産** (10点) - 資産の拡大
        4. **営業CF** (10点) - キャッシュフロー健全性
        5. **現金等** (10点) - 手元資金の充実
        6. **ROE** (10点) - 自己資本利益率7%以上
        7. **自己資本比率** (10点) - 財務安定性50%以上
        8. **1株配当** (10点) - 配当の維持・増配
        9. **配当性向** (10点) - 無理のない配当水準40%以下
        
        ### 評価基準
        - **80点以上**: 優良企業
        - **60-79点**: 良好な財務状態
        - **40-59点**: 改善の余地あり
        - **39点以下**: 慎重な判断が必要
        """)

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
    <p>⚠️ データ取得状況により、一部の銘柄で正確な分析ができない場合があります。</p>
</div>
""", unsafe_allow_html=True)