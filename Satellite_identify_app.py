import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import fuzz, process

st.title("UCS × CelesTrak 衛星対応表作成ツール")

# ------------------------------
# データ取得と整形
# ------------------------------
@st.cache_data
def load_ucs_data():
    url = "https://www.ucsusa.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023%20%28text%29.txt"
    data = requests.get(url).content.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(data), sep="\t")

    # ダブルクォーテーション除去
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
            epoch_year_code = line1[18:20]
            # TLEの年コードを西暦に変換
            if epoch_year_code.isdigit():
                epoch_year = int(epoch_year_code)
                epoch_year_full = 2000 + epoch_year if epoch_year < 57 else 1900 + epoch_year
            else:
                epoch_year_full = None
            satellites.append({
                "tle_name": name,
                "norad_id": norad_id,
                "epoch_year": epoch_year_full,
                "line1": line1,
                "line2": line2
            })
    return pd.DataFrame(satellites)

# ------------------------------
# マッチングロジック
# ------------------------------
def advanced_match(ucs_df, tle_df, name_threshold=60):
    results = []
    for _, ucs_row in ucs_df.iterrows():
        ucs_name = ucs_row['Name of Satellite, Alternate Names']
        ucs_norad = str(ucs_row.get('NORAD Number', '')).strip()
        ucs_launch = str(ucs_row.get('Date of Launch', '')).strip()
        try:
            ucs_launch_year = int(ucs_launch.split("-")[0])
        except:
            ucs_launch_year = None

        # 1. NORAD一致（年の検証はしない）
        tle_match = tle_df[tle_df['norad_id'] == ucs_norad]
        if not tle_match.empty:
            matched_row = tle_match.iloc[0]
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": matched_row['tle_name'],
                "Match Type": "NORAD一致",
                "Fuzzy Score": None,
                "Epoch Year": matched_row['epoch_year'],
                "Valid Year Match": True,
                "line1": matched_row['line1'],
                "line2": matched_row['line2']
            })
            continue

        # 2. 名前のファジーマッチ + 年一致判定
        try:
            match = process.extractOne(ucs_name, tle_df['tle_name'], scorer=fuzz.token_sort_ratio)
            if match is not None:
                best_name, score, _ = match
                matched_row = tle_df[tle_df['tle_name'] == best_name].iloc[0]
                tle_epoch_year = matched_row['epoch_year']

                # 年の一致確認：TLEのエポック年 < UCSの打ち上げ年 → 無効
                if ucs_launch_year is not None and tle_epoch_year is not None:
                    valid_year = tle_epoch_year >= ucs_launch_year
                else:
                    valid_year = True  # UCS側の年が不明ならOK

                if score >= name_threshold and valid_year:
                    results.append({
                        "UCS Name": ucs_name,
                        "UCS NORAD": ucs_norad,
                        "TLE Name": matched_row['tle_name'],
                        "Match Type": "名前類似",
                        "Fuzzy Score": score,
                        "Epoch Year": tle_epoch_year,
                        "Valid Year Match": valid_year,
                        "line1": matched_row['line1'],
                        "line2": matched_row['line2']
                    })
                else:
                    results.append({
                        "UCS Name": ucs_name,
                        "UCS NORAD": ucs_norad,
                        "TLE Name": None,
                        "Match Type": "一致なし（年不一致または閾値未満）",
                        "Fuzzy Score": score,
                        "Epoch Year": tle_epoch_year,
                        "Valid Year Match": valid_year,
                        "line1": None,
                        "line2": None
                    })
            else:
                results.append({
                    "UCS Name": ucs_name,
                    "UCS NORAD": ucs_norad,
                    "TLE Name": None,
                    "Match Type": "一致なし（None）",
                    "Fuzzy Score": None,
                    "Epoch Year": None,
                    "Valid Year Match": False,
                    "line1": None,
                    "line2": None
                })
        except Exception as e:
            results.append({
                "UCS Name": ucs_name,
                "UCS NORAD": ucs_norad,
                "TLE Name": None,
                "Match Type": f"エラー: {e}",
                "Fuzzy Score": None,
                "Epoch Year": None,
                "Valid Year Match": False,
                "line1": None,
                "line2": None
            })

    return pd.DataFrame(results)

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
    result_df = advanced_match(ucs_df, tle_df, threshold)
    st.success("✅ マッチング完了！")

    st.dataframe(result_df.head(50))

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 CSVファイルとしてダウンロード",
        data=csv,
        file_name="matched_satellites.csv",
        mime="text/csv"
    )
