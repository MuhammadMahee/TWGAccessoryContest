import streamlit as st
import pandas as pd

# ---------------- CONFIG ----------------
CODES_FILE = "IDM_User_Codes.xlsx"

REPORTS = {
    "Accessory Dashboard": "https://twgaccbonus.streamlit.app/",
    # Add more reports here later if needed
}

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="TWG Reports Portal",
    layout="centered"
)

# ---------------- SESSION STATE ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None

# ---------------- LOAD USERS ----------------
codes_df = pd.read_excel(CODES_FILE)
usernames = codes_df["username"].dropna().unique().tolist()

# ====================================================
# ==================== LOGIN PAGE ====================
# ====================================================
if not st.session_state.logged_in:

    st.markdown(
        """
        <div style="text-align:center; margin-top:120px;">
            <h1>TWG | Totally Wireless Group</h1>
            <h2>Reports Login</h2>
        </div>
        """,
        unsafe_allow_html=True
    )

    selected_user = st.selectbox("Select Username", usernames)
    entered_code = st.text_input("Enter Code", type="password")

    if st.button("Login"):
        actual_code = codes_df.loc[
            codes_df["username"] == selected_user, "code"
        ].values[0]

        if entered_code == actual_code:
            st.session_state.logged_in = True
            st.session_state.username = selected_user
            st.rerun()
        else:
            st.error("Invalid code")

# ====================================================
# ================= SELECTION PAGE ===================
# ====================================================
else:
    st.markdown(
        f"""
        <div style="text-align:center;">
            <h2>Welcome, {st.session_state.username}</h2>
            <h3>Select a Report</h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    selected_report = st.selectbox(
        "Available Reports",
        list(REPORTS.keys())
    )

    if st.button("Open Report"):
        base_url = REPORTS[selected_report]
        final_url = f"{base_url}?user={st.session_state.username}"  # FIXED: use ?user=
        st.markdown(
            f"<meta http-equiv='refresh' content='0; url={final_url}'>",
            unsafe_allow_html=True
        )

    st.divider()

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()