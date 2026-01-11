import streamlit as st
import pandas as pd
from datetime import date
import os
from datetime import datetime

# -------------------- DEFAULT MONTH LOGIC --------------------
today = datetime.today()
THIS_MONTH_START = date(today.year, today.month, 1)

# first day of next month minus 1 day
NEXT_MONTH_START = (
    date(today.year + (today.month // 12), ((today.month % 12) + 1), 1)
)
THIS_MONTH_END = NEXT_MONTH_START - pd.Timedelta(days=1)

THIS_MONTH_LABEL = today.strftime("%b-%y")


# -------------------- FILE PATHS --------------------
CODES_FILE = r"C:\Users\Administrator\OneDrive\Accessory_Contest_Dashboard\IDM By User\IDM_User_Codes.xlsx"
DATA_FILE = "Accessory_Contest.csv"
ADMIN_USERS = ["Admin"]  # Use exact case as in your codes file

# -------------------- PAGE CONFIG --------------------
st.set_page_config(page_title="Accessory Contest Dashboard", layout="wide")

# -------------------- LOAD DATA --------------------
df = pd.read_csv(DATA_FILE)
df["adddate"] = pd.to_datetime(df["adddate"], errors="coerce").dt.date
df = df[[
        "adddate", "marketid", "custno", "company", "item", "itmdesc", "qty",
        "Accessory", "minprice", "Cost", "discount", "Profit",
        "adduser", "Fullname", "invno", "state"
    ]]

codes_df = pd.read_excel(CODES_FILE)

# -------------------- SESSION STATE --------------------
if "page" not in st.session_state:
    st.session_state.page = st.query_params.get("page", ["Login_Page"])[0]

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None

# -------------------- HELPERS --------------------
def go_to_page(page_name):
    st.session_state.page = page_name
    st.query_params["page"] = page_name
    st.rerun()

def logout():
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

def get_user_df():
    # Admin gets full dataset
    if st.session_state.username in ADMIN_USERS:
        return df.copy()
    return df[df["adduser"] == st.session_state.username].copy()

# -------------------- SIDEBAR --------------------
if st.session_state.logged_in:
    with st.sidebar:
        st.markdown("### Logged in as")
        st.markdown(f"**{st.session_state.username}**")

        st.divider()

        st.markdown(
            """
            <style>
            div.stButton > button {
                width: 100%;
                text-align: left;
                padding: 12px;
                font-size: 15px;
                font-weight: 600;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        for btn in ["Home Page", "Summary", "Detailed"]:
            if st.button(btn):
                go_to_page(btn)

        st.divider()

        if st.button("Logout"):
            logout()

# ====================================================
# ==================== LOGIN PAGE ====================
# ====================================================
if st.session_state.page == "Login_Page":

    st.markdown(
        """
        <div style="text-align:center; margin-top:100px;">
            <h1>TWG | TOTALLY WIRELESS GROUP</h1>
            <h2>Accessory Bonus Dashboard Login</h2>
        </div>
        """,
        unsafe_allow_html=True
    )

    usernames = codes_df["username"].dropna().unique().tolist()
    selected_user = st.selectbox("Select Username", usernames)
    entered_code = st.text_input("Enter Code", type="password")

    if st.button("Login"):
        actual_code = codes_df.loc[
            codes_df["username"] == selected_user, "code"
        ].values[0]

        if entered_code == actual_code:
            st.session_state.logged_in = True
            st.session_state.username = selected_user
            go_to_page("Home Page")
        else:
            st.error("Invalid code. Please try again.")

# ====================================================
# ==================== HOME PAGE =====================
# ====================================================
elif st.session_state.page == "Home Page" and st.session_state.logged_in:

    st.markdown(
        f"""
        <div style="text-align:left;">
            <h1>TWG | TOTALLY WIRELESS GROUP |</h1>
            <h2>Welcome to Accessory Bonus Dashboard!</h2>
            <h3><strong>Top 5 Employees by Bonus – {THIS_MONTH_LABEL}</strong></h3>
            <h3><strong></strong></h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    home_df = get_user_df()

    home_df = home_df[
    (home_df["adddate"] >= THIS_MONTH_START) &
    (home_df["adddate"] <= THIS_MONTH_END)
]

    if home_df.empty:
        st.info("No data available to calculate bonuses.")
    else:
        summary = (
            home_df
            .groupby(["adduser", "Fullname"], as_index=False)
            .agg(
                Total_Accessory=("Accessory", "sum"),
                Total_Profit=("Profit", "sum")
            )
        )

        def calculate_bonus(row):
            acc = row["Total_Accessory"]
            profit = row["Total_Profit"]

            if acc <= 2999:
                pct = 0.08
            elif acc <= 5999:
                pct = 0.10
            elif acc <= 9999:
                pct = 0.15
            else:
                pct = 0.17

            return round(profit * pct, 2)

        summary["Bonus"] = summary.apply(calculate_bonus, axis=1)

        top5 = summary.sort_values("Bonus", ascending=False).head(5).reset_index(drop=True)

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        for idx, row in top5.iterrows():
            if idx == 0:
                # 1st place – BIG & BOLD
                st.markdown(
                    f"""
                    <div style="text-align:left; font-size:35px; font-weight:800; margin-bottom:12px;">
                        {medals[idx]} {row['adduser']} — {row['Fullname']} — ${row['Bonus']:,.2f}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                # Others – normal size
                st.markdown(
                    f"""
                    <div style="text-align:left; font-size:25px; margin-bottom:8px;">
                        {medals[idx]} {row['adduser']} — {row['Fullname']} — ${row['Bonus']:,.2f}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# ====================================================
# ==================== SUMMARY =======================
# ====================================================
elif st.session_state.page == "Summary" and st.session_state.logged_in:

    st.title("Summary")

    summary_df = get_user_df()

    if summary_df.empty:
        st.info("No data available for the selected user.")
    else:
        fullnames = summary_df["Fullname"].dropna().unique().tolist()
        selected_name = st.selectbox("Select Fullname", ["All"] + fullnames)

        if selected_name != "All":
            summary_df = summary_df[summary_df["Fullname"] == selected_name]

        ntid = summary_df["adduser"].dropna().unique().tolist()
        selected_ntid = st.selectbox("Select NTID", ["All"] + ntid)

        if selected_ntid != "All":
            summary_df = summary_df[summary_df["adduser"] == selected_ntid]

        companies = summary_df["company"].dropna().unique().tolist()
        selected_company = st.selectbox("Select Company", ["All"] + companies)

        if selected_company != "All":
            summary_df = summary_df[summary_df["company"] == selected_company]

        min_date = summary_df["adddate"].min()
        max_date = summary_df["adddate"].max()

        if pd.notna(min_date) and pd.notna(max_date):
            default_start = max(min_date, THIS_MONTH_START)
            default_end = min(max_date, THIS_MONTH_END)

            start_date, end_date = st.date_input(
                "Select Date Range",
                value=(default_start, default_end),
                min_value=min_date,
                max_value=max_date
            )

            summary_df = summary_df[
                (summary_df["adddate"] >= start_date) &
                (summary_df["adddate"] <= end_date)
            ]

        total_qty = summary_df["qty"].sum()
        total_accessory = summary_df["Accessory"].sum()
        total_profit = summary_df["Profit"].sum()

        if total_accessory <= 2999:
            tier, bonus_pct = "Tier 1", 0.08
        elif total_accessory <= 5999:
            tier, bonus_pct = "Tier 2", 0.10
        elif total_accessory <= 9999:
            tier, bonus_pct = "Tier 3", 0.15
        else:
            tier, bonus_pct = "Tier 4", 0.17

        bonus = total_profit * bonus_pct

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Qty", total_qty)
        c2.metric("Total Accessory", f"${total_accessory:,.2f}")
        c3.metric("Total Profit", f"${total_profit:,.2f}")

        c4, c5, c6 = st.columns(3)
        c4.metric("Tier", tier)
        c5.metric("Bonus %", f"{bonus_pct*100:.0f}%")
        c6.metric("Bonus", f"${bonus:,.2f}")

# ====================================================
# ==================== DETAILED ======================
# ====================================================
elif st.session_state.page == "Detailed" and st.session_state.logged_in:

    st.title("Detailed Data")

    filtered_df = get_user_df()

    # Keep only selected columns
    columns_to_display = df.columns
    filtered_df = filtered_df.loc[:, filtered_df.columns.intersection(columns_to_display)]

    if filtered_df.empty:
        st.info("No data available for the selected user.")
    else:
        fullnames = filtered_df["Fullname"].dropna().unique().tolist()
        selected_name = st.selectbox("Select Fullname", ["All"] + fullnames)

        if selected_name != "All":
            filtered_df = filtered_df[filtered_df["Fullname"] == selected_name]

        ntid = filtered_df["adduser"].dropna().unique().tolist()
        selected_ntid = st.selectbox("Select NTID", ["All"] + ntid)

        if selected_ntid != "All":
            filtered_df = filtered_df[filtered_df["adduser"] == selected_ntid]

        stores = filtered_df["company"].dropna().unique().tolist()
        selected_store = st.selectbox("Select Store", ["All"] + stores)

        if selected_store != "All":
            filtered_df = filtered_df[filtered_df["company"] == selected_store]

        min_date = filtered_df["adddate"].min()
        max_date = filtered_df["adddate"].max()

        if pd.notna(min_date) and pd.notna(max_date):
            default_start = max(min_date, THIS_MONTH_START)
            default_end = min(max_date, THIS_MONTH_END)

            start_date, end_date = st.date_input(
                "Select Date Range",
                value=(default_start, default_end),
                min_value=min_date,
                max_value=max_date
            )

            filtered_df = filtered_df[
                (filtered_df["adddate"] >= start_date) &
                (filtered_df["adddate"] <= end_date)
            ]

        st.dataframe(filtered_df, use_container_width=True)