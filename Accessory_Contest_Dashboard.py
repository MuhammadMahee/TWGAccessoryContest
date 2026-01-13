import streamlit as st
import pandas as pd
from datetime import date, datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Accessory Contest Dashboard", layout="wide")

# ---------------- QUERY PARAMS ----------------
qp = st.query_params
username = qp.get("user", "Admin")
page = qp.get("page", "Home Page")

# ---------------- DATE LOGIC ----------------
today = datetime.today()
THIS_MONTH_START = date(today.year, today.month, 1)
NEXT_MONTH_START = date(today.year + (today.month // 12), ((today.month % 12) + 1), 1)
THIS_MONTH_END = NEXT_MONTH_START - pd.Timedelta(days=1)
THIS_MONTH_LABEL = today.strftime("%b-%y")

# ---------------- FILE ----------------
DATA_FILE = "Accessory_Contest.csv"

# ---------------- LOAD DATA ----------------
df = pd.read_csv(DATA_FILE)
df["adddate"] = pd.to_datetime(df["adddate"], errors="coerce").dt.date

df = df[
    [
        "adddate", "marketid", "custno", "company", "item", "itmdesc",
        "qty", "Accessory", "minprice", "Cost", "discount",
        "Profit", "adduser", "Fullname", "invno", "state"
    ]
]

# ---------------- FILTER BY USER ----------------
def get_user_df():
    if username == "Admin":
        return df.copy()
    return df[df["adduser"] == username].copy()

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("### Logged in as")
    st.markdown(f"**{username}**")
    st.divider()

    if st.button("Home Page"):
        st.query_params.clear()
        st.query_params["user"] = username
        st.query_params["page"] = "Home Page"

    if st.button("Summary"):
        st.query_params.clear()
        st.query_params["user"] = username
        st.query_params["page"] = "Summary"

    if st.button("Detailed"):
        st.query_params.clear()
        st.query_params["user"] = username
        st.query_params["page"] = "Detailed"

# ====================================================
# ==================== HOME PAGE =====================
# ====================================================
if page == "Home Page":

    st.markdown(
        f"""
        <h1>TWG | Totally Wireless Group</h1>
        <h2>Accessory Bonus Dashboard</h2>
        <h3>Top 5 Employees — {THIS_MONTH_LABEL}</h3>
        """,
        unsafe_allow_html=True
    )

    home_df = get_user_df()
    home_df = home_df[
        (home_df["adddate"] >= THIS_MONTH_START)
        & (home_df["adddate"] <= THIS_MONTH_END)
    ]

    if home_df.empty:
        st.info("No data available.")
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
        top5 = summary.sort_values("Bonus", ascending=False).head(5)

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        for i, row in top5.reset_index(drop=True).iterrows():
            st.markdown(
                f"<h3>{medals[i]} {row['adduser']} — {row['Fullname']} — ${row['Bonus']:,.2f}</h3>",
                unsafe_allow_html=True
            )

# ====================================================
# ==================== SUMMARY =======================
# ====================================================
elif page == "Summary":

    st.title("Summary")
    summary_df = get_user_df()

    if summary_df.empty:
        st.info("No data available.")
    else:
        start_date, end_date = st.date_input(
            "Date Range",
            value=(THIS_MONTH_START, THIS_MONTH_END)
        )

        summary_df = summary_df[
            (summary_df["adddate"] >= start_date)
            & (summary_df["adddate"] <= end_date)
        ]

        st.metric("Total Qty", summary_df["qty"].sum())
        st.metric("Total Accessory", f"${summary_df['Accessory'].sum():,.2f}")
        st.metric("Total Profit", f"${summary_df['Profit'].sum():,.2f}")

# ====================================================
# ==================== DETAILED ======================
# ====================================================
elif page == "Detailed":

    st.title("Detailed Data")
    detailed_df = get_user_df()

    if detailed_df.empty:
        st.info("No data available.")
    else:
        st.dataframe(detailed_df, use_container_width=True)
