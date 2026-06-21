"""
Google Sheets からデータを読み込む。
サービスアカウント認証 または パブリックシート（CSV エクスポート）に対応。
"""
import os
import io
import requests
import pandas as pd
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _sheet_id_from_url(url: str) -> str:
    """Google Sheets URL からスプレッドシート ID を抽出。"""
    import re
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""


def _gid_from_url(url: str) -> str:
    """URL から gid（シートID）を抽出。"""
    import re
    m = re.search(r"gid=(\d+)", url)
    return m.group(1) if m else "0"


@st.cache_data(ttl=300)
def load_sheet_as_csv(sheet_url: str, gid: str = "0") -> pd.DataFrame:
    """
    Google Sheets を CSV としてパブリック取得する（認証不要の場合）。
    シートが非公開の場合はサービスアカウント認証にフォールバック。
    """
    sid = _sheet_id_from_url(sheet_url)
    csv_url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"

    try:
        resp = requests.get(csv_url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        # 文字化け防止：UTF-8 を明示してデコード
        resp.encoding = "utf-8"
        df = pd.read_csv(io.StringIO(resp.text), encoding="utf-8")
        return df
    except Exception as e:
        st.warning(f"CSV取得失敗（{e}）。サービスアカウント認証を試みます。")
        return _load_via_service_account(sheet_url, gid)


def _load_via_service_account(sheet_url: str, gid: str) -> pd.DataFrame:
    """サービスアカウント認証で読み込む。"""
    if not HAS_GSPREAD:
        return pd.DataFrame()
    try:
        creds_dict = dict(st.secrets.get("gcp_service_account", {}))
        if creds_dict:
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
            creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_url(sheet_url)
        worksheets = spreadsheet.worksheets()
        ws = next((w for w in worksheets if str(w.id) == gid), worksheets[0])
        return pd.DataFrame(ws.get_all_records())
    except Exception as e:
        st.error(f"認証読み込みエラー：{e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_sakai_operation_data(sheet_url: str) -> pd.DataFrame:
    """
    境町拠点の運行データを読み込む。
    Google Sheets: 1TS-XQsP3k_GZFslv2tkAQ4kl1iVTAjIJ4OjCJcudsFI / gid=1870078201
    """
    gid = _gid_from_url(sheet_url)
    df = load_sheet_as_csv(sheet_url, gid)
    return df
