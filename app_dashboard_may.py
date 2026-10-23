import datetime
import json
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# 1. CẤU HÌNH TRANG DASHBOARD - XƯỞNG DỆT
st.set_page_config(
    page_title="Sơ Đồ Mặt Bằng XƯỞNG DỆT", page_icon="🏭", layout="wide"
)
st.title("🏭 SƠ ĐỒ MẶT BẰNG & BẢN ĐỒ VẬN HÀNH MÁY - XƯỞNG DỆT")
st.caption("Bộ phận Kế hoạch Sản xuất | Nhà máy Bao bì")

# LINK GOOGLE APPS SCRIPT WEB APP CỦA ANH
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxkcj8J_5w0H6ahoxujS6k192evPUp1ub7KcFsG_ZGxAs0fCJkj6M5GmRNrx5H_7n0/exec"

color_map = {
    "Đang vận hành": "#2ecc71",
    "Đang rảnh": "#3498db",
    "Đang bảo trì": "#f1c40f",
    "Đang hỏng": "#e74c3c",
}


def normalize_status(stt):
  stt_str = str(stt).strip()
  if stt_str in ["Đang chạy", "Đang vận hành", "Chạy", "Running"]:
    return "Đang vận hành"
  elif stt_str in [
      "Đang rảnh",
      "Rảnh",
      "Chờ đứt sợi/gá cuộn",
      "Chờ hàng",
      "Idle",
  ]:
    return "Đang rảnh"
  elif stt_str in ["Đang bảo trì", "Bảo trì", "Maintenance"]:
    return "Đang bảo trì"
  elif stt_str in ["Đang hỏng", "Dừng sự cố", "Hỏng", "Sự cố", "Breakdown"]:
    return "Đang hỏng"
  return "Đang vận hành"


# HÀM TÍNH NGÀY HOÀN THÀNH - TRỪ CHỦ NHẬT
def add_workdays_exclude_sunday(start_date, workdays_needed):
  curr = start_date
  added = 0
  if workdays_needed <= 0:
    return start_date
  while added < workdays_needed:
    curr += datetime.timedelta(days=1)
    if curr.weekday() != 6:  # 6 = Chủ Nhật (Nghỉ)
      added += 1
  return curr


# HÀM ĐẾM SỐ NGÀY LÀM VIỆC THỰC TẾ GIỮA 2 NGÀY (TRỪ CHỦ NHẬT)
def count_workdays_between(start_date, target_date):
  if target_date <= start_date:
    return 0
  workdays = 0
  curr = start_date + datetime.timedelta(days=1)
  while curr <= target_date:
    if curr.weekday() != 6:  # Không tính Chủ Nhật
      workdays += 1
    curr += datetime.timedelta(days=1)
  return workdays


# 2. ĐỌC DỮ LIỆU TỪ GOOGLE TRANG TÍNH
@st.cache_data(ttl=5)
def load_data_from_sheets():
  raw_url = "https://docs.google.com/spreadsheets/d/1vgGAnx4p_kqLyFOKJEvxW1qV1qAW5DIeu-LbPVFNvGQ/edit?usp=drivesdk"
  csv_url = (
      raw_url.split("/edit")[0] + "/export?format=csv"
      if "/edit" in raw_url
      else raw_url
  )
  try:
    df_sheet = pd.read_csv(csv_url)
    df_sheet.columns = (
        df_sheet.columns.astype(str).str.strip().str.replace("\ufeff", "")
    )
    return df_sheet
  except Exception:
    return pd.DataFrame()


# 3. ĐỒNG BỘ TỌA ĐỘ VÀ KÍCH THƯỚC MÁY
def generate_layout_coordinates(df_input):
  machines = []
  sheet_dict = {}

  if not df_input.empty and "Mã máy" in df_input.columns:
    for _, r in df_input.iterrows():
      m_code = str(r["Mã máy"]).strip()
      if m_code and m_code.lower() != "nan":
        raw_stt = r.get("Trạng thái", "Đang vận hành")

        ns_ca_val = 5000
        for col_name in r.index:
          if "NĂNG SUẤT" in str(col_name).upper():
            try:
              ns_ca_val = int(float(r[col_name]))
            except Exception:
              ns_ca_val = 5000
            break

        sheet_dict[m_code] = {
            "Loại thiết bị": r.get("Loại thiết bị", "Dệt tròn"),
            "Trạng thái": normalize_status(raw_stt),
            "Khách hàng": r.get("Khách hàng", "Chưa phân bổ"),
            "PO": r.get("PO", "PO-2026"),
            "Số Lượng": r.get("Số Lượng", 0),
            "khổ": r.get("khổ", "50 cm"),
            "Denier": r.get("Denier", "650D"),
            "Mật độ dệt": r.get("Mật độ dệt", "10x10"),
            "NĂNG SUẤT M/CA": int(ns_ca_val),
        }

  np.random.seed(100)
  kh_data = [
      ("CP ĐỒNG NAI", "PO-2026-089", 36000, "50 cm", "650D", "10x10"),
      ("ALIC", "PO-2026-102", 45000, "60 cm", "700D", "11x11"),
      ("FOIL LAM", "PO-2026-054", 28000, "45 cm", "750D", "12x12"),
      ("KIM ĐỨC", "PO-2026-118", 32000, "55 cm", "680D", "10x10"),
      ("MALAYSIA", "PO-2026-201", 50000, "90 cm", "800D", "8x8"),
      ("PHILIPPINES", "PO-2026-305", 25000, "90 cm", "850D", "8x8"),
      ("SEGAMAT", "PO-2026-412", 40000, "60 cm", "720D", "11x11"),
  ]
  statuses = ["Đang vận hành", "Đang rảnh", "Đang bảo trì", "Đang hỏng"]
  weights = [0.75, 0.12, 0.08, 0.05]

  def add_m(
      code, display_num, model, x, y, dx=0.85, dy=0.85, custom_kh=None
  ):
    if code in sheet_dict:
      loai = sheet_dict[code]["Loại thiết bị"]
      stt = sheet_dict[code]["Trạng thái"]
      kh = sheet_dict[code]["Khách hàng"]
      po = sheet_dict[code]["PO"]
      sl = sheet_dict[code]["Số Lượng"]
      kho = sheet_dict[code]["khổ"]
      denier = sheet_dict[code]["Denier"]
      mat_do = sheet_dict[code]["Mật độ dệt"]
      ns_ca = sheet_dict[code]["NĂNG SUẤT M/CA"]
    else:
      loai = model
      stt = np.random.choice(statuses, p=weights)
      ns_ca = 5000
      if stt != "Đang rảnh":
        if custom_kh:
          kh, po, sl, kho, denier, mat_do = custom_kh
        else:
          kh, po, sl, kho, denier, mat_do = kh_data[
              np.random.choice(len(kh_data))
          ]
      else:
        kh, po, sl, kho, denier, mat_do = (
            "Chưa phân bổ",
            "-",
            0,
            "-",
            "-",
            "-",
        )

    machines.append({
        "Mã máy": code,
        "Số hiển thị": str(display_num),
        "Loại thiết bị": loai,
        "Trạng thái": normalize_status(stt),
        "Khách hàng": kh,
        "PO": po,
        "Số Lượng": int(sl) if str(sl).replace(".", "").isdigit() else 30000,
        "khổ": kho,
        "Denier": denier,
        "Mật độ dệt": mat_do,
        "NĂNG SUẤT M/CA": int(ns_ca),
        "X": x,
        "Y": y,
        "DX": dx,
        "DY": dy,
    })

  # CỤM MÁY TRÁNG
  add_m(
      "LAM-01",
      "MÁY TRÁNG 1",
      "Tráng màng Lamination",
      6.0,
      18.2,
      dx=6.5,
      dy=1.4,
      custom_kh=("Tráng màng PP", "PO-LAM-01", 1995000, "60 cm", "N/A", "N/A"),
  )
  add_m(
      "LAM-02",
      "MÁY TRÁNG 2",
      "Tráng màng Lamination",
      6.0,
      16.2,
      dx=6.5,
      dy=1.4,
      custom_kh=("Tráng màng PP", "PO-LAM-02", 65000, "90 cm", "N/A", "N/A"),
  )

  # CỤM TẠO SỢI
  add_m(
      "EX-01",
      "TIRATEX 1",
      "Máy tạo sợi TIRATEX 1600",
      35.0,
      18.8,
      dx=7.5,
      dy=1.2,
      custom_kh=(
          "Tạo Sợi PP",
          "PO-EXT-01",
          125000,
          "Thành phẩm sợi",
          "650D-800D",
          "N/A",
      ),
  )
  add_m(
      "EX-02",
      "TIRATEX 2",
      "Máy tạo sợi TIRATEX 1600",
      35.0,
      17.3,
      dx=7.5,
      dy=1.2,
      custom_kh=(
          "Tạo Sợi PP",
          "PO-EXT-02",
          128000,
          "Thành phẩm sợi",
          "700D",
          "N/A",
      ),
  )
  add_m(
      "EX-03",
      "STAREX 1",
      "Máy tạo sợi STAREX 1400",
      35.0,
      15.8,
      dx=7.5,
      dy=1.2,
      custom_kh=(
          "Tạo Sợi PP",
          "PO-EXT-03",
          119000,
          "Thành phẩm sợi",
          "900D",
          "N/A",
      ),
  )

  # HÀNG 1
  for i, num in enumerate([33, 34, 35, 36, 37, 38]):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        1.0 + i * 1.0,
        12.5,
        dx=0.88,
        dy=0.95,
    )
  for i, num in enumerate([23, 1, 2]):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        8.0 + i * 1.0,
        12.5,
        dx=0.88,
        dy=0.95,
    )
  for i, num in enumerate(range(39, 55)):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        13.5 + i * 1.05,
        12.5,
        dx=0.92,
        dy=0.95,
    )
  for i, num in enumerate(range(55, 61)):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        33.0 + i * 1.0,
        12.5,
        dx=0.88,
        dy=0.95,
    )

  # HÀNG 2
  for i, num in enumerate(range(32, 23, -1)):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        1.0 + i * 1.0,
        10.0,
        dx=0.88,
        dy=0.95,
    )
  add_m(
      "RX81-01",
      "8.1",
      "Starlinger RX 8.1 (Jumbo)",
      10.2,
      10.0,
      dx=1.1,
      dy=0.95,
  )
  for i, num in enumerate(range(22, 6, -1)):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.1",
        13.5 + i * 1.05,
        10.0,
        dx=0.92,
        dy=0.95,
    )
  for i, num in enumerate(range(6, 2, -1)):
    add_m(
        f"RX61-{num:02d}",
        num,
        "Starlinger RX 6.0",
        33.0 + i * 1.0,
        10.0,
        dx=0.88,
        dy=0.95,
    )
  for i, num in enumerate([27, 28]):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        37.5 + i * 1.0,
        10.0,
        dx=0.88,
        dy=0.95,
    )

  # HÀNG 3
  for i, num in enumerate(range(12, 0, -1)):
    add_m(
        f"BSW-{num:02d}",
        num,
        "Máy dệt BSW",
        0.5 + i * 0.9,
        6.0,
        dx=0.82,
        dy=1.35,
    )
  for i, num in enumerate(range(1, 20)):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        13.0 + i * 0.92,
        6.0,
        dx=0.85,
        dy=1.35,
    )
  for i, num in enumerate(range(21, 27)):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        33.0 + i * 1.0,
        6.0,
        dx=0.88,
        dy=1.35,
    )

  # HÀNG 4
  for i, num in enumerate([20, 35, 36]):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        17.0,
        3.8 - i * 1.15,
        dx=2.0,
        dy=0.9,
    )
  for i, num in enumerate([32, 33, 34]):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        24.0,
        3.8 - i * 1.15,
        dx=2.0,
        dy=0.9,
    )
  for i, num in enumerate([29, 30, 31]):
    add_m(
        f"RX60-{num:02d}",
        num,
        "Starlinger RX 6.0",
        35.0,
        3.8 - i * 1.15,
        dx=2.0,
        dy=0.9,
    )

  return pd.DataFrame(machines)


df_sheet = load_data_from_sheets()

if "df_data" not in st.session_state or st.sidebar.button(
    "🔄 Tải lại từ Google Sheets"
):
  st.session_state.df_data = generate_layout_coordinates(df_sheet)

df_all = st.session_state.df_data

# QUẢN LÝ THIẾT BỊ EXPANDER
st.sidebar.markdown("### ⚙️ QUẢN LÝ THIẾT BỊ")
with st.sidebar.expander("📝 CẬP NHẬT TRỰC TIẾP MÁY", expanded=False):
  target_machine = st.selectbox(
      "Chọn máy cần đổi:", df_all["Mã máy"], key="exp_select_m"
  )
  curr_row = df_all[df_all["Mã máy"] == target_machine].iloc[0]

  st.markdown("---")
  val_loai = st.text_input("Loại thiết bị:", value=str(curr_row["Loại thiết bị"]))
  val_status = st.selectbox(
      "Trạng thái:",
      list(color_map.keys()),
      index=list(color_map.keys()).index(
          normalize_status(curr_row["Trạng thái"])
      ),
  )
  val_kh = st.text_input("Tên Khách hàng:", value=str(curr_row["Khách hàng"]))
  val_po = st.text_input("Mã PO:", value=str(curr_row["PO"]))
  val_sl = st.number_input(
      "Sản lượng / Số Lượng (m):", value=int(curr_row["Số Lượng"]), step=500
  )
  val_kho = st.text_input("Khổ:", value=str(curr_row["khổ"]))
  val_denier = st.text_input("Denier:", value=str(curr_row["Denier"]))
  val_matdo = st.text_input("Mật độ dệt:", value=str(curr_row["Mật độ dệt"]))
  val_nsc = st.number_input(
      "⚡ NĂNG SUẤT M/CA:", value=int(curr_row["NĂNG SUẤT M/CA"]), step=500
  )

  btn_save = st.button("💾 ĐỒNG BỘ NGHUYÊN TRANG LÊN GOOGLE SHEETS")
  if btn_save:
    mask = st.session_state.df_data["Mã máy"] == target_machine
    st.session_state.df_data.loc[mask, "Loại thiết bị"] = val_loai
    st.session_state.df_data.loc[mask, "Trạng thái"] = val_status
    st.session_state.df_data.loc[mask, "Khách hàng"] = val_kh
    st.session_state.df_data.loc[mask, "PO"] = val_po
    st.session_state.df_data.loc[mask, "Số Lượng"] = val_sl
    st.session_state.df_data.loc[mask, "khổ"] = val_kho
    st.session_state.df_data.loc[mask, "Denier"] = val_denier
    st.session_state.df_data.loc[mask, "Mật độ dệt"] = val_matdo
    st.session_state.df_data.loc[mask, "NĂNG SUẤT M/CA"] = val_nsc

    payload = {
        "Mã máy": target_machine,
        "Loại thiết bị": val_loai,
        "Trạng thái": val_status,
        "Khách hàng": val_kh,
        "PO": val_po,
        "Số Lượng": val_sl,
        "khổ": val_kho,
        "Denier": val_denier,
        "Mật độ dệt": val_matdo,
        "NĂNG SUẤT M/CA": val_nsc,
    }

    if "script.google.com" in WEB_APP_URL:
      try:
        res = requests.post(WEB_APP_URL, json=payload, timeout=5)
        st.success(f"✅ Đã ghi nhận máy {target_machine} lên Google Sheets!")
      except Exception as e:
        st.warning(f"Đã cập nhật giao diện! (Lỗi gửi Sheets: {e})")
    else:
      st.success(f"✅ Đã cập nhật máy {target_machine} trên Sơ đồ!")

    st.rerun()

# BỘ LỌC TRA CỨU SIDEBAR
st.sidebar.markdown("---")
st.sidebar.header("🔍 BỘ LỌC TRA CỨU")

all_customers = sorted(
    [c for c in df_all["Khách hàng"].unique() if c != "Chưa phân bổ"]
)
selected_kh = st.sidebar.multiselect(
    "🏢 Lọc theo Khách hàng:",
    options=all_customers,
    default=[],
    placeholder="Tất cả Khách hàng",
)
search_machine = st.sidebar.text_input("🔎 Tìm Số máy / Mã máy:", "")
selected_status = st.sidebar.multiselect(
    "🟢 Lọc theo Trạng thái:",
    options=list(color_map.keys()),
    default=[],
    placeholder="Tất cả Trạng thái",
)

df_filtered = df_all.copy()
if selected_kh:
  df_filtered = df_filtered[df_filtered["Khách hàng"].isin(selected_kh)]
if selected_status:
  df_filtered = df_filtered[
      df_filtered["Trạng thái"].apply(normalize_status).isin(selected_status)
  ]
if search_machine.strip() != "":
  q = search_machine.strip().lower()
  df_filtered = df_filtered[
      df_filtered["Mã máy"].str.lower().str.contains(q)
      | df_filtered["Số hiển thị"].str.lower().str.contains(q)
  ]

highlight_ids = set(df_filtered["Mã máy"])

# KPI TỔNG QUAN
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tổng thiết bị", len(df_all))
c2.metric(
    "🟢 Đang vận hành",
    len(
        df_all[
            df_all["Trạng thái"].apply(normalize_status) == "Đang vận hành"
        ]
    ),
)
c3.metric(
    "🔵 Đang rảnh",
    len(df_all[df_all["Trạng thái"].apply(normalize_status) == "Đang rảnh"]),
)
c4.metric(
    "🟡 Đang bảo trì",
    len(
        df_all[df_all["Trạng thái"].apply(normalize_status) == "Đang bảo trì"]
    ),
)
c5.metric(
    "🔴 Đang hỏng",
    len(
        df_all[df_all["Trạng thái"].apply(normalize_status) == "Đang hỏng"]
    ),
)

st.markdown("---")

# DỰNG SƠ ĐỒ MẶT BẰNG XƯỞNG DỆT
fig = go.Figure()

# Vách tường & Khu vực phụ
fig.add_shape(
    type="rect",
    x0=-0.5,
    y0=14.2,
    x1=40,
    y1=14.8,
    fillcolor="#27ae60",
    line=dict(color="#1e8449", width=2),
    layer="below",
)
fig.add_annotation(
    x=19.5,
    y=14.5,
    text="<b>TƯỜNG VÁCH NGĂN XƯỞNG</b>",
    showarrow=False,
    font=dict(color="white", size=13),
)

fig.add_shape(
    type="rect",
    x0=0.5,
    y0=0.5,
    x1=11.5,
    y1=4.5,
    fillcolor="#34495e",
    line=dict(color="#7f8c8d", width=2),
    layer="below",
)
fig.add_annotation(
    x=6.0,
    y=2.5,
    text="<b>KHU VỰC ĐỰNG SỢI</b>",
    showarrow=False,
    font=dict(color="#ecf0f1", size=13),
)

fig.add_shape(
    type="line",
    x0=-0.5,
    y0=8.0,
    x1=40,
    y1=8.0,
    line=dict(color="#f39c12", width=3, dash="dot"),
    layer="below",
)
fig.add_annotation(
    x=-0.2,
    y=8.5,
    text="<b>⬅️ LỐI VÀO CHÍNH</b>",
    showarrow=False,
    font=dict(color="#f39c12", size=12),
)

for x_aisle in [12.0, 31.5]:
  fig.add_shape(
      type="line",
      x0=x_aisle,
      y0=0,
      x1=x_aisle,
      y1=14,
      line=dict(color="#bdc3c7", width=2, dash="dash"),
      layer="below",
  )

# HỘP THỐNG KÊ KHÁCH HÀNG
if selected_kh:
  df_kh_matched = df_all[df_all["Khách hàng"].isin(selected_kh)]
  total_m_kh = len(df_kh_matched)

  model_counts = df_kh_matched.groupby("Loại thiết bị").size().to_dict()
  model_details = "<br>".join(
      [f"  • <b>{model}:</b> {count} máy" for model, count in model_counts.items()]
  )
  kh_str = ", ".join(selected_kh)

  info_html = (
      f"<b>🏢 KHÁCH HÀNG: {kh_str}</b><br>⚙️ <b>Tổng số máy đang chạy:</b>"
      f" <span style='color:#2ecc71;'><b>{total_m_kh} máy</b></span><br><b>📋"
      f" Chi tiết loại máy:</b><br>{model_details}"
  )
else:
  info_html = (
      "<b>🏢 THỐNG KÊ KHÁCH HÀNG</b><br><i>(Hãy chọn Khách hàng ở Bộ Lọc để"
      " xem chi tiết số máy & loại máy)</i>"
  )

fig.add_shape(
    type="rect",
    x0=0.5,
    y0=-3.8,
    x1=11.5,
    y1=-0.5,
    fillcolor="#2c3e50" if selected_kh else "#1e272e",
    line=dict(color="#2ecc71" if selected_kh else "#576574", width=2),
    layer="below",
)

fig.add_annotation(
    x=0.8,
    y=-2.15,
    text=info_html,
    showarrow=False,
    font=dict(color="#ffffff", size=11),
    align="left",
    xanchor="left",
)

hover_texts = []
for _, row in df_all.iterrows():
  is_selected = row["Mã máy"] in highlight_ids
  stt_norm = normalize_status(row["Trạng thái"])
  color = color_map.get(stt_norm, "#2ecc71") if is_selected else "#3a3a3a"
  opacity = 1.0 if is_selected else 0.3

  x0 = row["X"] - row["DX"] / 2
  x1 = row["X"] + row["DX"] / 2
  y0 = row["Y"] - row["DY"] / 2
  y1 = row["Y"] + row["DY"] / 2

  fig.add_shape(
      type="rect",
      x0=x0,
      y0=y0,
      x1=x1,
      y1=y1,
      fillcolor=color,
      line=dict(
          color="#ffffff" if is_selected else "#555555",
          width=2 if is_selected else 1,
      ),
      opacity=opacity,
      layer="below",
  )

  val_str = str(row["Số hiển thị"])
  f_size = 11 if len(val_str) <= 3 else (9 if len(val_str) <= 8 else 8)

  fig.add_annotation(
      x=row["X"],
      y=row["Y"],
      text=f"<b>{val_str}</b>",
      showarrow=False,
      font=dict(size=f_size, color="#ffffff"),
      align="center",
  )

  ns_ca_txt = f"{int(row['NĂNG SUẤT M/CA']):,}"
  hover_txt = (
      f"<b>MÁY: {row['Mã máy']} (Số: {row['Số hiển thị']})</b><br>"
      f"<b>Loại thiết bị:</b> {row['Loại thiết bị']}<br>"
      f"<b>Trạng thái:</b> {stt_norm}<br>"
      f"-----------------------------<br>"
      f"<b>Khách hàng:</b> {row['Khách hàng']}<br>"
      f"<b>PO:</b> {row['PO']}<br>"
      f"<b>Sản lượng/Số lượng:</b> {int(row['Số Lượng']):,} m<br>"
      f"<b>⚡ Năng suất:</b> {ns_ca_txt} m/ca (3 ca ="
      f" {int(row['NĂNG SUẤT M/CA']*3):,} m/ngày)<br>"
      f"<b>Khổ:</b> {row['khổ']} | <b>Denier:</b> {row['Denier']} | <b>Mật"
      f" độ:</b> {row['Mật độ dệt']}"
  )
  hover_texts.append(hover_txt)

fig.add_trace(
    go.Scatter(
        x=df_all["X"],
        y=df_all["Y"],
        mode="markers",
        marker=dict(size=20, opacity=0),
        hoverinfo="text",
        hovertext=hover_texts,
        showlegend=False,
    )
)

for status_name, status_color in color_map.items():
  fig.add_trace(
      go.Scatter(
          x=[None],
          y=[None],
          mode="markers",
          marker=dict(size=14, symbol="square", color=status_color),
          name=status_name,
      )
  )

fig.update_layout(
    title=(
        "<b>LAYOUT BẢN ĐỒ VẬN HÀNH XƯỞNG DỆT (TỐI ƯU KÍCH THƯỚC HÌNH KHỐI"
        " MÁY)</b>"
    ),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        range=[-1, 40],
        autorange=False,
        fixedrange=False,
    ),
    yaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        range=[-4.2, 20.5],
        autorange=False,
        fixedrange=False,
    ),
    height=820,
    plot_bgcolor="#181818",
    paper_bgcolor="#181818",
    font=dict(color="white"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1
    ),
    dragmode=False,
    uirevision="constant",
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={"displayModeBar": True, "scrollZoom": False, "responsive": True},
)

# =========================================================================
# 8. CÔNG CỤ TÍNH NĂNG SUẤT, ĐỐI CHIẾU GAP & ĐỀ XUẤT PHƯƠNG ÁN MÁY
# =========================================================================
st.markdown("---")
st.subheader("⏱️ CÔNG CỤ TÍNH NĂNG SUẤT & ĐỀ XUẤT MÁY THEO NGÀY GIAO HÀNG")
st.caption(
    "Tính toán chính xác theo sản lượng mục tiêu PO (sau khi trừ tồn kho), năng"
    " suất ca (3 ca/ngày) và đối chiếu GAP chênh lệch."
)

p_col1, p_col2 = st.columns([1.1, 1.1])

with p_col1:
  st.markdown("#### 1️⃣ Chọn Đơn Hàng PO, Tồn Kho & Nhập Năng Suất Máy")

  calc_kh_options = ["Tất cả Khách hàng"] + sorted(
      [c for c in df_all["Khách hàng"].unique() if c != "Chưa phân bổ"]
  )
  selected_kh_calc = st.selectbox(
      "🏢 Chọn Khách hàng (Lọc danh sách PO):", options=calc_kh_options
  )

  if selected_kh_calc != "Tất cả Khách hàng":
    df_calc_scope = df_all[df_all["Khách hàng"] == selected_kh_calc]
  else:
    df_calc_scope = df_all.copy()

  po_list = sorted([
      p
      for p in df_calc_scope["PO"].unique()
      if str(p) != "-" and str(p).lower() != "nan"
  ])
  if not po_list:
    po_list = ["Chưa có PO"]

  selected_po = st.selectbox(
      "📦 Chọn Mã PO cần tính toán tiến độ:", options=po_list
  )

  df_po_machines = df_all[df_all["PO"] == selected_po]
  po_kh = (
      df_po_machines["Khách hàng"].iloc[0]
      if not df_po_machines.empty
      else "N/A"
  )

  try:
    po_qty_default = int(df_po_machines["Số Lượng"].iloc[0])
  except Exception:
    po_qty_default = 30000

  po_qty = st.number_input(
      "📏 Tổng số lượng sản phẩm PO (mét):",
      value=po_qty_default,
      step=1000,
  )

  # SỐ LƯỢNG TỒN KHO TỰ NHẬP
  inventory_qty = st.number_input(
      "📦 Số lượng Tồn kho hiện có (mét):",
      value=0,
      min_value=0,
      step=1000,
      key=f"input_inventory_{selected_po}",
  )

  # TÍNH SẢN LƯỢNG CÒN LẠI CẦN SẢN XUẤT
  remaining_qty = max(0, po_qty - inventory_qty)

  st.info(
      f"📊 **Sản lượng còn lại cần sản xuất:** `{remaining_qty:,} m`  \n*(Tổng PO:"
      f" {po_qty:,} m - Tồn kho: {inventory_qty:,} m)*"
  )

  running_po_df = df_po_machines[
      df_po_machines["Trạng thái"].apply(normalize_status) == "Đang vận hành"
  ]
  running_m_po = len(running_po_df)

  st.markdown("---")
  st.markdown(
      f"⚙️ **TỰ NHẬP NĂNG SUẤT/CA CHO CÁC LOẠI MÁY ĐANG CHẠY PO {selected_po}:**"
  )

  model_inputs = {}
  total_daily_calculated = 0.0

  if not running_po_df.empty:
    model_groups = running_po_df.groupby("Loại thiết bị")

    for model_name, group in model_groups:
      m_count = len(group)
      default_ns_ca = int(group["NĂNG SUẤT M/CA"].iloc[0])

      ns_input_val = st.number_input(
          f"⚡ Năng suất/ca/máy [{model_name}] ({m_count} máy đang chạy):",
          value=int(default_ns_ca),
          step=100,
          key=f"input_ns_{selected_po}_{model_name}",
      )

      daily_for_model = m_count * ns_input_val * 3.0
      total_daily_calculated += daily_for_model
      model_inputs[model_name] = {
          "count": m_count,
          "ns_ca": ns_input_val,
          "daily": daily_for_model,
      }
  else:
    st.warning(
        f"⚠️ Chưa có máy nào ở trạng thái **Đang vận hành** được gán cho PO"
        f" **{selected_po}**!"
    )

  today = datetime.date.today()
  default_target_date = today + datetime.timedelta(days=10)
  target_delivery_date = st.date_input(
      "📅 Chọn Ngày Giao Hàng Mong Muốn (Target Delivery Date):",
      value=default_target_date,
      min_value=today,
  )

with p_col2:
  st.markdown("#### 2️⃣ Kết Quả Tính Toán Tiến Độ & Đối Chiếu GAP")

  if total_daily_calculated > 0:
    total_hours_needed = (
        (remaining_qty / total_daily_calculated) * 24.0
        if total_daily_calculated > 0
        else 0
    )
    workdays_needed = math.ceil(remaining_qty / total_daily_calculated)

    if total_hours_needed <= 24.0:
      estimated_finish_date = today
      time_txt = f"{total_hours_needed:.1f} giờ (~{math.ceil(total_hours_needed/8)} ca dệt)"
    else:
      estimated_finish_date = add_workdays_exclude_sunday(
          today, workdays_needed
      )
      time_txt = f"{workdays_needed} ngày làm việc"

    available_workdays = count_workdays_between(today, target_delivery_date)

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Sản lượng cần dệt",
        f"{int(remaining_qty):,} m",
        f"Thời gian: {time_txt}",
    )
    m2.metric(
        "Công suất dệt 1 ngày",
        f"{int(total_daily_calculated):,} m",
        "1 Ngày = 3 Ca",
    )
    m3.metric("Ngày xong dự kiến", estimated_finish_date.strftime("%d/%m/%Y"))

    gap_val = int(total_daily_calculated - remaining_qty)
    st.markdown("---")
    st.markdown("🎯 **ĐỐI TƯỢNG PO & ĐÁNH GIÁ GAP CÔNG SUẤT DỆT:**")

    if remaining_qty == 0:
      st.success(
          f"🎉 **ĐÃ ĐỦ TỒN KHO!** Không cần sản xuất thêm cho PO **{selected_po}**.",
          icon="✅",
      )
    elif gap_val >= 0:
      st.success(
          f"📊 **Sản lượng cần dệt:** `{int(remaining_qty):,} m`  |  ⚡ **Công suất"
          f" xưởng/ngày:** `{int(total_daily_calculated):,} m`  \n👉 **ĐÁNH GIÁ"
          f" GAP:** :green[**+{gap_val:,} m/ngày (DƯ THỪA NĂNG SUẤT)**]  \n*Đơn"
          f" hàng hoàn tất nhanh chóng trong {time_txt}.*",
          icon="✅",
      )
    else:
      st.warning(
          f"📊 **Sản lượng cần dệt:** `{int(remaining_qty):,} m`  |  ⚡ **Công suất"
          f" xưởng/ngày:** `{int(total_daily_calculated):,} m`  \n👉 **ĐÁNH GIÁ"
          f" GAP:** :red[**{gap_val:,} m/ngày (THIẾU CÔNG SUẤT)**]",
          icon="⚠️",
      )

    st.markdown("---")

    if remaining_qty == 0:
      st.success(
          f"🟢 **TỒN KHO ĐÁP ỨNG ĐỦ ĐƠN HÀNG!**  \n"
          f"Số lượng tồn kho (`{inventory_qty:,} m`) đã đủ để giao PO **{selected_po}** mà không cần khởi chạy dệt thêm."
      )
    elif estimated_finish_date <= target_delivery_date:
      st.success(
          f"🟢 **ĐÁP ỨNG TIẾN ĐỘ GIAO HÀNG!**  \n"
          f"Đơn hàng **{selected_po}** dự kiến dệt xong vào ngày"
          f" **{estimated_finish_date.strftime('%d/%m/%Y')}** ({time_txt}), kịp"
          f" trước hạn giao **{target_delivery_date.strftime('%d/%m/%Y')}**."
      )
    else:
      days_late = (estimated_finish_date - target_delivery_date).days
      st.error(
          f"🔴 **CẢNH BÁO: TRỄ TIẾN ĐỘ GIAO HÀNG ({days_late} ngày)!**  \n"
          f"Đơn hàng dệt xong vào ngày"
          f" **{estimated_finish_date.strftime('%d/%m/%Y')}**, trễ so với hạn"
          f" giao **{target_delivery_date.strftime('%d/%m/%Y')}**."
      )

    st.markdown("---")
    st.markdown("💡 **PHƯƠNG ÁN PHÂN BỔ & TĂNG/GIẢM MÁY:**")

    avg_m_daily = (
        total_daily_calculated / running_m_po if running_m_po > 0 else 15000.0
    )
    idle_machines_count = len(
        df_all[df_all["Trạng thái"].apply(normalize_status) == "Đang rảnh"]
    )

    if remaining_qty == 0:
      st.info(
          f"• **Số máy đang chạy PO hiện tại:** **{running_m_po} máy**  \n"
          f"• 👉 **ĐỀ XUẤT MÁY:** Tồn kho đã đủ đơn hàng, có thể :green[**chuyển toàn bộ {running_m_po} máy sang chạy PO khác**]."
      )
    elif available_workdays > 0:
      required_daily_output = remaining_qty / available_workdays
      required_total_machines = math.ceil(required_daily_output / avg_m_daily)
      if required_total_machines < 1:
        required_total_machines = 1
      add_machines_needed = max(0, required_total_machines - running_m_po)

      m_txt = (
          f":red[**CẦN THÊM +{add_machines_needed} MÁY**] *(Xưởng hiện có"
          f" **{idle_machines_count} máy Đang Rảnh** có thể đưa vào chạy)*"
          if add_machines_needed > 0
          else f":green[**ĐỦ MÁY CHẠY ({running_m_po} máy đang dư công suất, có"
               " thể chuyển bớt máy sang PO khác)**]"
      )

      st.info(
          f"• **Số máy đang chạy PO hiện tại:** **{running_m_po} máy**  \n"
          f"• **Số máy tối thiểu cần để kịp hạn giao ({target_delivery_date.strftime('%d/%m/%Y')}):** **{required_total_machines} máy**  \n"
          f"• 👉 **ĐỀ XUẤT MÁY:** {m_txt}"
      )
    else:
      st.info(
          f"• **Số máy đang chạy PO hiện tại:** **{running_m_po} máy**  \n"
          f"• **Số máy rảnh trên xưởng:** **{idle_machines_count} máy**  \n"
          f"• 👉 **PHƯƠNG ÁN:** Đơn hàng chỉ mất **{time_txt}**, đáp ứng dệt"
          " ngay trong ca dệt hôm nay mà không cần bổ sung máy."
      )

  else:
    st.info(
        "💡 Hãy chọn Mã PO và đảm bảo có máy đang ở trạng thái **Đang vận"
        " hành**."
    )

# 9. BẢNG DỮ LIỆU
st.markdown("---")
st.subheader("✏️ BẢNG CHI TIẾT KỸ THUẬT MÁY XƯỞNG DỆT")
st.dataframe(
    st.session_state.df_data[[
        "Mã máy",
        "Loại thiết bị",
        "Trạng thái",
        "Khách hàng",
        "PO",
        "Số Lượng",
        "khổ",
        "Denier",
        "Mật độ dệt",
        "NĂNG SUẤT M/CA",
    ]],
    use_container_width=True,
)
