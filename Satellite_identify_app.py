import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import process, fuzz
from datetime import datetime

st.title("🛰️ 衛星名マッチングアプリ")

@st.cache_data
def load_ucs_data():
    url = "https://www.ucsusa.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023%20%28text%29.txt"
    data = requests.get(url).content.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(data), sep="\t")
    df.columns = df.columns.str.strip('"')  # 列名の余分なダブルクォートを削除
    return df

@st.cache_data
def load_tle_data():
    url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
    data = requests.get(url).text.strip().splitlines()
    names = [data[i].strip() for i in range(0, len(data), 3)]  # 3行ごとに1つの名前
    return pd.DataFrame({'tle_name': names})

def extract_year(date_str):
    try:
        return datetime.strptime(date_str, "%m/%d/%y").year
    except Exception:
        return None

def advanced_match(ucs_df, tle_df, threshold=80):
    results = []

    for _, ucs_row in ucs_df.iterrows():
        ucs_name = str(ucs_row.get('Name of Satellite, Alternate Names', '')).strip()
        ucs_norad = ucs_row.get('NORAD Number', '')
        ucs_launch = ucs_row.get('Date of Launch', '')
        ucs_year = extract_year(ucs_launch)

        st.write(f"🔍 UCS Name: {ucs_name} / NORAD: {ucs_norad} / Launch Year: {ucs_launch}")
        st.write(f"🧾 TLE Names (先頭5件): {tle_df['tle_name'].head().tolist()}")

        try:
            match = process.extractOne(
                ucs_name,
                tle_df['tle_name'],
                scorer=fuzz.token_sort_ratio
            )

            if match and isinstance(match, tuple) and len(match) == 2:
                best_name, score = match
                if score >= threshold:
                    results.append({
                        "UCS Name": ucs_name,
                        "TLE Name": best_name,
                        "Similarity Score": score,
                        "Launch Year": ucs_year
                    })
                else:
                    st.warning(f"⚠️ 類似度がしきい値未満: {ucs_name} → {best_name} ({score})")
            else:
                st.warning(f"⚠️ マッチが見つかりませんでした: {ucs_name}")

        except Exception as e:
            st.error(f"❌ マッチングエラー: {ucs_name} / エラー内容: {e}")

    return pd.DataFrame(results)

# ------------------------------
# メイン処理
# ------------------------------

ucs_df = load_ucs_data()
tle_df = load_tle_data()

threshold = st.slider("🎚 類似度のしきい値", min_value=50, max_value=100, value=85, step=1)

if st.button("🔍 マッチング開始"):
    st.info("マッチング処理中...お待ちください。")
    result_df = advanced_match(ucs_df, tle_df, threshold)
    st.success(f"✅ マッチング完了！ {len(result_df)} 件が見つかりました。")
    st.dataframe(result_df)
