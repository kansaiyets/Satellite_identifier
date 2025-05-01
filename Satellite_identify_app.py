import streamlit as st
import pandas as pd
import requests
from io import StringIO
from rapidfuzz import fuzz, process

st.title("UCS × CelesTrak 衛星対応表作成ツール（NORAD ID + 名前 + 打上年で精度向上）")

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
        if i + 2 < len(lines):
            name = lines[i].strip()
            line1 = lines[i + 1].strip()
            line2 = lines[i + 2].strip()
            norad_id = line1[2:7].strip()
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
        try:
            ucs_name = str(ucs_row
