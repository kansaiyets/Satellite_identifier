import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import fuzz, process

st.title("UCS × CelesTrak 衛星マッチングツール")

# ------------------------------
# データ読み込み
# ------------------------------
@st.cache_data
def load_ucs_data():
    url = "https://www.ucsusa.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023%20%28text%29.txt"
    data = requests.get(url).content.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(data), sep="\t")
    df.columns = [col.strip().strip('"') for col in df.columns]  # ヘッダー整形
    return df

@st.cache_data
def load_tle_data():
    url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
    tle_text = requests.get(url).text
    lines = tle_text.strip().split("\n")
    satellites = []
    for i in range(0, len(lines), 3):
        if i + 2 < len(lines):
            name = lines[i].strip()
            line1 = lines[i + 1].strip()
            line2 = lines[i + 2].strip()
            norad_id = line1[2:7].strip()
            year_code = int(line1[18:20])
            launch_year = f"20{year_code:02}" if year_code < 50 else f"19{year_code:02}"
            satellites.append({
                "tle_name": name,
                "line1": line1,
                "line2": line2,
                "norad_id": norad_id,
                "launch_year": launch_year
            })
    return pd.DataFrame(satellites)

# ------------------------------
# マッチング処理（確認出力付き）
# ------------------------------
def advanced_match(ucs_df, tle_df, name_threshold=85):
    results = []
    for idx, ucs_row in ucs_df.iterrows():
        try:
            ucs_name = ucs_row['Name of Satellite, Alternate Names']
        except KeyError as e:
            st.error(f"❌ UCSデータに 'Name of Satellite, Alternate Names' 列が存在しません。利用可能な列: {list(ucs_row.index)}")
            raise e

        ucs_norad = str(ucs_row.get('NORAD Number', '')).strip()
        ucs_launch = str(ucs_row.get('Date of Launch', '')).split("-")[0]

        # 🟡 確認用出力
        st.write(f"🔍 UCS Name: {ucs_name} / NORAD: {ucs_norad} / Launch Year: {ucs_launch}")
        st.write(f"🧾 TLE Names (先頭5件): {tle_df['tle_name'].head().tolist()}")

        # 1. NORAD一致
        match_norad = tle_df[tle_df['norad_id'] == ucs_norad]
        if not match_norad.empty:
            row = match_norad.iloc[0]
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": row['tle_name'],
                "Match Type": "NORAD一致",
                "Fuzzy Score": None,
                "Launch Year Match": ucs_launch == row['launch_year'],
                "line1": row['line1'],
                "line2": row['line2']
            })
            continue

        # 2. ファジーマッチ
        try:
            best_name, score = process.extractOne(ucs_name, tle_df['tle_name'], scorer=fuzz.token_sort_ratio)
        except Exception as e:
            st.error(f"❌ extractOne でエラーが発生しました: {e}")
            raise e

        if score >= name_threshold:
            row = tle_df[tle_df['tle_name'] == best_name].iloc[0]
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": best_name,
                "Match Type": "名前類似",
                "Fuzzy Score": score,
                "Launch Year Match": ucs_launch == row['launch_year'],
                "line1": row['line1'],
                "line2": row['line2']
            })
        else:
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": None,
                "Match Type": "一致なし",
                "Fuzzy Score": score,
                "Launch Year Match": False,
                "line1": None,
                "line2": None
            })

        # デモ目的で最初の3件だけに制限（コメントアウトすれば全件処理）
        if idx >= 2:
            break

    return pd.DataFrame(results)

# ------------------------------
# UI
# ------------------------------
st.write("🔄 衛星データを読み込み中...")
ucs_df = load_ucs_data()
tle_df = load_tle_data()
st.success(f"✅ UCS衛星数: {len(ucs_df)}、TLE衛星数: {len(tle_df)}")

threshold = st.slider("名前のマッチング閾値 (Fuzzy)", 70, 100, 85)

if st.button("マッチングを実行"):
    st.write("🚀 マッチング処理中...")
    result_df = advanced_match(ucs_df, tle_df, threshold)
    st.success("✅ マッチング完了！")

    st.dataframe(result_df)

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button("CSVをダウンロード", data=csv, file_name="matched_satellites.csv", mime="text/csv")
