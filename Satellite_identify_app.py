import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import fuzz, process

st.title("UCS × CelesTrak 衛星対応表作成ツール（NORAD ID + 名前 + 打上日で精度向上）")

# ------------------------------
# データ取得と整形
# ------------------------------
@st.cache_data
def load_ucs_data():
    url = "https://www.ucsusa.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023%20%28text%29.txt"
    data = requests.get(url).content.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(data), sep="\t")
    return df

@st.cache_data
def load_tle_data():
    url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"
    tle_text = requests.get(url).text
    lines = tle_text.strip().split("\n")
    satellites = []
    for i in range(0, len(lines), 3):
        if i+2 < len(lines):
            name = lines[i].strip()
            line1 = lines[i+1].strip()
            line2 = lines[i+2].strip()
            norad_id = line1[2:7].strip()  # NORAD番号はTLE行1の3～7桁目
            launch_year = "20" + line1[18:20] if int(line1[18:20]) < 50 else "19" + line1[18:20]
            satellites.append({
                "tle_name": name,
                "norad_id": norad_id,
                "launch_year": launch_year,
                "line1": line1,
                "line2": line2
            })
    return pd.DataFrame(satellites)

# ------------------------------
# マッチングロジック
# ------------------------------
def advanced_match(ucs_df, tle_df, name_threshold=85):
    results = []
    for _, ucs_row in ucs_df.iterrows():
        ucs_name = ucs_row['Name of Satellite, Alternate Names'].strip('"')
        ucs_norad = str(ucs_row.get('NORAD Number', ''))
        ucs_launch = str(ucs_row.get('Date of Launch', '')).split("-")[0]

        # 1. NORADで完全一致
        tle_match = tle_df[tle_df['norad_id'] == ucs_norad]
        if not tle_match.empty:
            matched_row = tle_match.iloc[0]
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": matched_row['tle_name'],
                "Match Type": "NORAD一致",
                "Fuzzy Score": None,
                "Launch Year Match": ucs_launch == matched_row['launch_year'],
                "line1": matched_row['line1'],
                "line2": matched_row['line2']
            })
            continue

        # 2. 名前のファジーマッチ（しきい値以上）
        best_name, score = process.extractOne(ucs_name, tle_df['tle_name'], scorer=fuzz.token_sort_ratio)
        if score >= name_threshold:
            matched_row = tle_df[tle_df['tle_name'] == best_name].iloc[0]
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": matched_row['tle_name'],
                "Match Type": "名前類似",
                "Fuzzy Score": score,
                "Launch Year Match": ucs_launch == matched_row['launch_year'],
                "line1": matched_row['line1'],
                "line2": matched_row['line2']
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
    return pd.DataFrame(results)

# ------------------------------
# 実行部分
# ------------------------------
st.write("データを読み込み中...")
ucs_df = load_ucs_data()
tle_df = load_tle_data()

st.write(f"UCS 衛星数: {len(ucs_df)}、CelesTrak 衛星数: {len(tle_df)}")

name_threshold = st.slider("名前のマッチング閾値（fuzzy match）", 70, 100, 85)

if st.button("マッチングを実行"):
    st.write("マッチングを実行中...")
    result_df = advanced_match(ucs_df, tle_df, name_threshold)
    st.success("マッチング完了！")
    
    st.dataframe(result_df.head(20))

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="CSVファイルとしてダウンロード",
        data=csv,
        file_name="matched_satellites.csv",
        mime="text/csv"
    )
