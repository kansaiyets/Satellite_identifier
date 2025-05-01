import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import fuzz, process
import re

st.title("UCS × CelesTrak 衛星対応表作成ツール")

# ------------------------------
# データ取得と整形
# ------------------------------
@st.cache_data
def load_ucs_data():
    url = "https://www.ucsusa.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023%20%28text%29.txt"
    data = requests.get(url).content.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(data), sep="\t")
    df.columns = [col.strip().strip('"') for col in df.columns]
    df = df.applymap(lambda x: x.strip('"') if isinstance(x, str) else x)
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
            norad_id = line1[2:7].strip()
            year_code = line1[18:20]
            try:
                epoch_year = int(year_code)
                launch_year = 2000 + epoch_year if epoch_year < 50 else 1900 + epoch_year
            except:
                launch_year = None
            satellites.append({
                "tle_name": name,
                "norad_id": norad_id,
                "launch_year": launch_year,
                "line1": line1,
                "line2": line2
            })
    return pd.DataFrame(satellites)

# ------------------------------
# 衛星名の候補を抽出
# ------------------------------
def extract_name_candidates(name_str):
    if not isinstance(name_str, str):
        return []
    no_parens = re.sub(r"[()]", ",", name_str)
    parts = re.split(r"[,\s]+", no_parens)
    return [part.strip() for part in parts if part.strip()]

# ------------------------------
# マッチングロジック
# ------------------------------
def advanced_match(ucs_df, tle_df, name_threshold=60):
    results = []
    match_count = 0

    for _, ucs_row in ucs_df.iterrows():
        ucs_name = ucs_row['Name of Satellite, Alternate Names']
        ucs_norad = str(ucs_row.get('NORAD Number', ''))
        ucs_launch = str(ucs_row.get('Date of Launch', '')).split("-")[0]
        try:
            ucs_launch_year = int(ucs_launch)
        except:
            ucs_launch_year = None

        # 1. NORAD一致
        tle_match = tle_df[tle_df['norad_id'] == ucs_norad]
        if not tle_match.empty:
            matched_row = tle_match.iloc[0]
            match_count += 1
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": matched_row['tle_name'],
                "Match Type": "NORAD一致",
                "Fuzzy Score": None,
                "Launch Year Match": True,
                "line1": matched_row['line1'],
                "line2": matched_row['line2']
            })
            continue

        # 2. 名前のファジーマッチ（複数候補）
        name_candidates = extract_name_candidates(ucs_name)
        best_match = None
        best_score = -1

        for candidate in name_candidates:
            match = process.extractOne(candidate, tle_df['tle_name'], scorer=fuzz.token_sort_ratio)
            if match and match[1] > best_score:
                best_match = match
                best_score = match[1]

        if best_match and best_score >= name_threshold:
            best_name, score, _ = best_match
            matched_row = tle_df[tle_df['tle_name'] == best_name].iloc[0]

            tle_launch_year = matched_row['launch_year']
            if tle_launch_year is not None and ucs_launch_year is not None:
                launch_match = tle_launch_year >= ucs_launch_year
            else:
                launch_match = True  # UCS側が不明な場合はOK

            if launch_match:
                match_count += 1
                results.append({
                    "UCS Name": ucs_name,
                    "UCS NORAD": ucs_norad,
                    "TLE Name": matched_row['tle_name'],
                    "Match Type": "名前類似",
                    "Fuzzy Score": score,
                    "Launch Year Match": True,
                    "line1": matched_row['line1'],
                    "line2": matched_row['line2']
                })
            else:
                results.append({
                    "UCS Name": ucs_name,
                    "UCS NORAD": ucs_norad,
                    "TLE Name": matched_row['tle_name'],
                    "Match Type": "打ち上げ年不一致",
                    "Fuzzy Score": score,
                    "Launch Year Match": False,
                    "line1": None,
                    "line2": None
                })
        else:
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": None,
                "Match Type": "一致なし",
                "Fuzzy Score": best_score if best_match else None,
                "Launch Year Match": False,
                "line1": None,
                "line2": None
            })

    return pd.DataFrame(results), match_count

# ------------------------------
# 実行
# ------------------------------
st.write("データを読み込み中...")
ucs_df = load_ucs_data()
tle_df = load_tle_data()

st.write(f"✅ UCS 衛星数: {len(ucs_df)}、CelesTrak 衛星数: {len(tle_df)}")

threshold = st.slider("名前のマッチング閾値（fuzzy match）", 20, 100, 60)

if st.button("マッチングを実行"):
    st.write("🔄 マッチングを実行中...")
    result_df, match_count = advanced_match(ucs_df, tle_df, threshold)
    st.success(f"✅ マッチング完了！一致した衛星数: {match_count} / {len(result_df)}")

    st.dataframe(result_df.head(30))

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 CSVファイルとしてダウンロード",
        data=csv,
        file_name="matched_satellites.csv",
        mime="text/csv"
    )
