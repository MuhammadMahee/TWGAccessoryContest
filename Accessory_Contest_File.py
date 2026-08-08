import sys
import time
import random
import string
import requests
import pandas as pd
import json
import re
from datetime import datetime
import io
import chardet
import glob
import os
import cookie  # your cookie.py
from sqlalchemy import create_engine, text

# -------------------- CONFIG --------------------
DB_USER = "twg_admin"
DB_PASS = "twg_admin"
DB_HOST = "127.0.0.1"  # localhost
DB_PORT = "3306"
DB_SCHEMA = "TWG"
DB_TABLE = "Accessory_Contest"
KPI_TABLE = "KPIs"
EMP_KPI_TABLE = "emp_kpis"
TIME_PUNCH_TABLE = "TimePunches_Raw"
TIME_PUNCH_PIVOT_TABLE = "TimePunches_Pivot"
SAME_DAY_SPIFF_TABLE = "same_day_spiff_sales"

BASE_FOLDER = r"C:\Users\Administrator\OneDrive\Accessory_Contest_Dashboard\Sales_Detailed_Exclude_BP"

URL = "https://www.myrtpos.com/newbdi/SalesReportDetail.fwx"
TIME_PUNCH_URL = "https://www.myrtpos.com/newbdi/TimePunches.fwx"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": URL,
    "Content-Type": "application/x-www-form-urlencoded"
}

# -------------------- DATABASE ENGINE --------------------
ENGINE_DB = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_SCHEMA}")


# -------------------- UTILITIES --------------------
def generate_code():
    chars = string.ascii_letters + string.digits
    return f"{''.join(random.choices(chars, k=4))}-{''.join(random.choices(chars, k=4))}"


def decode_csv_response(content):
    detected = chardet.detect(content)
    encodings = [detected.get("encoding"), "utf-8", "utf-8-sig", "latin1", "windows-1252", "ISO-8859-1"]
    for enc in encodings:
        if not enc:
            continue
        try:
            return content.decode(enc)
        except Exception:
            continue
    return None


# -------------------- ENSURE ADMIN USER --------------------
def insert_admin_user(df):
    admin_df = pd.DataFrame([{"username": "Admin", "code": "A1234"}])
    df = pd.concat([admin_df, df], ignore_index=True)
    return df


def save_table_to_mysql(df, table_name):
    if df.empty:
        print(f"[SQL:{table_name}] No data to insert. Keeping previous table unchanged.")
        return False

    stage_table = f"{table_name}_stage_{generate_code().replace('-', '').lower()}"
    backup_table = f"{table_name}_backup_{generate_code().replace('-', '').lower()}"

    current_df_rows = len(df)
    print(f"[SQL:{table_name}] Preparing upload for {current_df_rows} rows")

    with ENGINE_DB.begin() as conn:
        table_exists_query = text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        )
        table_exists = conn.execute(
            table_exists_query,
            {"schema_name": DB_SCHEMA, "table_name": table_name}
        ).fetchone() is not None

        sql_rows = 0
        if table_exists:
            sql_rows = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar() or 0
            print(f"[SQL:{table_name}] Existing table found with {sql_rows} rows")
        else:
            print(f"[SQL:{table_name}] Table does not exist yet. A new table will be created")

        if table_exists and current_df_rows < sql_rows:
            print(
                f"[SQL:{table_name}] [SKIP] Current DataFrame has fewer rows than SQL table "
                f"for '{table_name}' ({current_df_rows} < {sql_rows}). Skipping export and retrying immediately."
            )
            return False

    print(f"[SQL:{table_name}] Writing staging table '{stage_table}'")
    df.to_sql(stage_table, ENGINE_DB, if_exists="replace", index=False)

    with ENGINE_DB.begin() as conn:
        if table_exists:
            print(f"[SQL:{table_name}] Swapping staging table into place and dropping backup")
            conn.execute(text(f"RENAME TABLE `{table_name}` TO `{backup_table}`, `{stage_table}` TO `{table_name}`"))
            conn.execute(text(f"DROP TABLE `{backup_table}`"))
        else:
            print(f"[SQL:{table_name}] Promoting staging table to live table")
            conn.execute(text(f"RENAME TABLE `{stage_table}` TO `{table_name}`"))

    print(f"[SQL:{table_name}] Refresh complete with {len(df)} rows")
    return True


# -------------------- FETCH DATA --------------------
def fetch_accessory_data():
    today = datetime.today()
    fixed_start = datetime(2026, 2, 1)
    this_month_start = datetime(today.year, today.month, 1)
    months_to_fetch = []

    cursor = fixed_start
    while cursor <= this_month_start:
        months_to_fetch.append((cursor.year, cursor.month))
        cursor = (cursor.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)

    all_dataframes = []
    print(
        f"[FETCH] Starting sales detail pull for {len(months_to_fetch)} month(s) "
        f"from {fixed_start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}"
    )

    for year, month in months_to_fetch:
        start_date = datetime(year, month, 1)
        next_month = (start_date.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)
        end_date = next_month - pd.Timedelta(days=1)
        print(f"[FETCH] Requesting {start_date.strftime('%Y-%m-%d')} through {end_date.strftime('%Y-%m-%d')}")

        payload = {
            "frmMarketID": "",
            "frmRegionID": "",
            "frmStateID": "",
            "frmStoreType": "",
            "frmStore": "",
            "chkNoPayment": "chkNoPayment",
            "frmStart": start_date.strftime("%m/%d/%Y"),
            "frmEnd": end_date.strftime("%m/%d/%Y"),
            "btnExcel": "click"
        }

        try:
            response = requests.post(URL, data=payload, headers=HEADERS, cookies=cookie.cookie)
            if response.status_code != 200:
                print(f"[FETCH] Request failed for {month:02d}/{year} with status {response.status_code}")
                continue

            csv_text = decode_csv_response(response.content)
            if csv_text is None:
                print(f"[FETCH] Unable to decode CSV for {month:02d}/{year}")
                continue

            if "<html" in csv_text.lower():
                print(f"[FETCH] HTML response received instead of CSV for {month:02d}/{year}")
                continue

            df_month = pd.read_csv(io.StringIO(csv_text))
            all_dataframes.append(df_month)
            print(f"[FETCH] Retrieved {len(df_month)} rows for {month:02d}/{year}")

        except Exception as e:
            print(f"[FETCH] Error fetching {month:02d}/{year}: {e}")

    if all_dataframes:
        df = pd.concat(all_dataframes, ignore_index=True)
        print(f"[FETCH] Combined fetch complete with {len(df)} rows")
        return df

    print("[FETCH] No data fetched")
    return pd.DataFrame()


def fetch_time_punch_data():
    today = datetime.today()
    fixed_start = datetime(2026, 2, 1)
    this_month_start = datetime(today.year, today.month, 1)
    months_to_fetch = []

    cursor = fixed_start
    while cursor <= this_month_start:
        months_to_fetch.append((cursor.year, cursor.month))
        cursor = (cursor.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)

    headers = {**HEADERS, "Referer": TIME_PUNCH_URL}
    all_dataframes = []
    print(
        f"[TIMEPUNCH] Starting TimePunches pull for {len(months_to_fetch)} month(s) "
        f"from {fixed_start.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}"
    )

    for year, month in months_to_fetch:
        start_date = datetime(year, month, 1)
        next_month = (start_date.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)
        end_date = next_month - pd.Timedelta(days=1)
        print(f"[TIMEPUNCH] Requesting {start_date.strftime('%Y-%m-%d')} through {end_date.strftime('%Y-%m-%d')}")

        payload = {
            "frmMarketID": "",
            "frmStateID": "",
            "frmRegionID": "",
            "frmStoreType": "",
            "frmStore": "",
            "frmStart": start_date.strftime("%m/%d/%Y"),
            "frmEnd": end_date.strftime("%m/%d/%Y"),
            "btnExcel": "click"
        }

        try:
            response = requests.post(TIME_PUNCH_URL, data=payload, headers=headers, cookies=cookie.cookie)
            if response.status_code != 200:
                print(f"[TIMEPUNCH] Request failed for {month:02d}/{year} with status {response.status_code}")
                continue

            csv_text = decode_csv_response(response.content)
            if csv_text is None:
                print(f"[TIMEPUNCH] Unable to decode CSV for {month:02d}/{year}")
                continue

            if "<html" in csv_text.lower():
                print(f"[TIMEPUNCH] HTML response received instead of CSV for {month:02d}/{year}")
                continue

            df_month = pd.read_csv(io.StringIO(csv_text))
            all_dataframes.append(df_month)
            print(f"[TIMEPUNCH] Retrieved {len(df_month)} rows for {month:02d}/{year}")
        except Exception as e:
            print(f"[TIMEPUNCH] Error fetching {month:02d}/{year}: {e}")

    if all_dataframes:
        df = pd.concat(all_dataframes, ignore_index=True)
        print(f"[TIMEPUNCH] Combined fetch complete with {len(df)} rows")
        return df

    print("[TIMEPUNCH] No data fetched")
    return pd.DataFrame()


# -------------------- PROCESS DATA --------------------
def process_data(df):
    if df.empty:
        print("[PROCESS] Source DataFrame is empty. Skipping accessory detail processing")
        return df

    print(f"[PROCESS] Building accessory detail from {len(df)} source rows")
    acc_detail = df[(df["tangible"].str.upper() == "T") & (df["serialized"].str.upper() == "F")].copy()
    acc_detail["qty"] = acc_detail["qty"].astype(int)
    acc_detail["price"] = acc_detail["price"].astype(float).round(2)
    acc_detail["cost1"] = acc_detail["cost"].astype(float).round(2)

    acc_detail = acc_detail.drop(columns=["cost"])
    acc_detail = acc_detail.drop(columns=["profit"])

    acc_detail["Accessory"] = (acc_detail["qty"] * acc_detail["price"]).round(2)
    acc_detail["Cost"] = (acc_detail["qty"] * acc_detail["cost1"]).round(2)
    acc_detail["Profit"] = (acc_detail["Accessory"] - acc_detail["Cost"]).round(2)

    acc_detail["Fullname"] = (acc_detail["name"] + " " + acc_detail["lastname"]).str.upper()

    acc_detail = insert_admin_user(acc_detail)
    print(f"[PROCESS] Accessory detail ready with {len(acc_detail)} rows")

    return acc_detail


def build_same_day_spiff_table(df):
    columns = ["report_date", "marketid", "company", "mim_count", "hint_count"]
    if df.empty:
        print("[SDS] Source DataFrame is empty. Skipping Same Day Spiff build")
        return pd.DataFrame(columns=columns)

    required = {"adddate", "marketid", "company", "item", "category", "qty"}
    missing = sorted(required - set(df.columns))
    if missing:
        print(f"[SDS] Missing required Sales Detailed columns: {', '.join(missing)}")
        return pd.DataFrame(columns=columns)

    working = df.copy()
    working["report_date"] = pd.to_datetime(working["adddate"], errors="coerce").dt.date
    working["marketid"] = working["marketid"].fillna("").astype(str).str.strip()
    working["company"] = working["company"].fillna("").astype(str).str.strip()
    working["qty"] = pd.to_numeric(working["qty"], errors="coerce").fillna(0)

    item_upper = working["item"].fillna("").astype(str).str.strip().str.upper()
    category_upper = working["category"].fillna("").astype(str).str.strip().str.upper()
    working["mim_count"] = working["qty"].where(item_upper == "MIM", 0)
    working["hint_count"] = working["qty"].where(category_upper == "HINT", 0)
    working = working[
        working["report_date"].notna()
        & (working["marketid"] != "")
        & (working["company"] != "")
        & ((working["mim_count"] != 0) | (working["hint_count"] != 0))
    ].copy()

    if working.empty:
        print("[SDS] No MIM item or HINT category rows found")
        return pd.DataFrame(columns=columns)

    result = (
        working.groupby(["report_date", "marketid", "company"], dropna=False)[["mim_count", "hint_count"]]
        .sum()
        .reset_index()
        .sort_values(["report_date", "marketid", "company"])
        .reset_index(drop=True)
    )
    result["mim_count"] = result["mim_count"].round().astype(int)
    result["hint_count"] = result["hint_count"].round().astype(int)
    print(f"[SDS] Same Day Spiff history ready with {len(result)} Date/store rows")
    return result[columns]


def build_kpi_table(df, acc_detail):
    key_columns = ["Date", "marketid", "custno", "company"]

    if df.empty:
        print("[KPI] Source DataFrame is empty. Skipping KPI build")
        return pd.DataFrame(columns=key_columns + ["PPD", "Accessory"])

    working_df = df.copy()
    working_df["qty"] = pd.to_numeric(working_df["qty"], errors="coerce").fillna(0)
    working_df["Date"] = pd.to_datetime(working_df["adddate"], errors="coerce").dt.date
    print(f"[KPI] Starting KPI build from {len(working_df)} source rows")

    prodline_upper = working_df["prodline"].fillna("").astype(str).str.strip().str.upper()
    item_upper = working_df["item"].fillna("").astype(str).str.strip().str.upper()

    metropcs = working_df[prodline_upper == "METROPCS"].copy()
    blank_prodline = working_df[prodline_upper == ""].copy()
    line_only_act = blank_prodline[item_upper.loc[blank_prodline.index] == "LINEONLYACT"].copy()
    print(f"[KPI] METROPCS rows found: {len(metropcs)}")
    print(f"[KPI] Blank prodline rows found: {len(blank_prodline)}")
    print(f"[KPI] LINEONLYACT rows added from blank prodline: {len(line_only_act)}")

    metropcs_combined = pd.concat([metropcs, line_only_act], ignore_index=True)
    combined_rows = len(metropcs_combined)
    metropcs_combined = metropcs_combined[
        metropcs_combined["category"].fillna("").astype(str).str.strip().str.upper() != "SIM CARDS"
    ].copy()
    print(f"[KPI] Removed {combined_rows - len(metropcs_combined)} SIM CARDS rows")
    print(f"[KPI] Final METROPCS dataset has {len(metropcs_combined)} rows")

    ppd_summary = (
        metropcs_combined.groupby(key_columns, dropna=False)["qty"]
        .sum()
        .reset_index()
        .rename(columns={"qty": "PPD"})
    )
    ppd_summary["PPD"] = ppd_summary["PPD"].round(2)

    accessory_working = acc_detail.copy()
    accessory_working["Date"] = pd.to_datetime(accessory_working["adddate"], errors="coerce").dt.date
    accessory_summary = (
        accessory_working.groupby(key_columns, dropna=False)["Accessory"]
        .sum()
        .reset_index()
    )
    accessory_summary["Accessory"] = accessory_summary["Accessory"].round(2)

    KPI = working_df[key_columns].drop_duplicates().copy()
    KPI = KPI.merge(ppd_summary, on=key_columns, how="left")
    KPI = KPI.merge(accessory_summary, on=key_columns, how="left")
    KPI["PPD"] = KPI["PPD"].fillna(0)
    KPI["Accessory"] = KPI["Accessory"].fillna(0).round(2)
    print(f"[KPI] KPI table ready with {len(KPI)} unique Date/store rows")

    return KPI


def build_emp_kpi_table(df, acc_detail):
    key_columns = ["Date", "marketid", "custno", "company", "adduser", "Fullname"]

    if df.empty:
        print("[EMP_KPI] Source DataFrame is empty. Skipping employee KPI build")
        return pd.DataFrame(columns=key_columns + ["PPD", "Accessory"])

    working_df = df.copy()
    working_df["qty"] = pd.to_numeric(working_df["qty"], errors="coerce").fillna(0)
    working_df["Date"] = pd.to_datetime(working_df["adddate"], errors="coerce").dt.date
    working_df["adduser"] = working_df["adduser"].fillna("").astype(str).str.strip()
    working_df["Fullname"] = (
        working_df["name"].fillna("").astype(str).str.strip() + " " +
        working_df["lastname"].fillna("").astype(str).str.strip()
    ).str.strip().str.upper()
    print(f"[EMP_KPI] Starting employee KPI build from {len(working_df)} source rows")

    prodline_upper = working_df["prodline"].fillna("").astype(str).str.strip().str.upper()
    item_upper = working_df["item"].fillna("").astype(str).str.strip().str.upper()

    metropcs = working_df[prodline_upper == "METROPCS"].copy()
    blank_prodline = working_df[prodline_upper == ""].copy()
    line_only_act = blank_prodline[item_upper.loc[blank_prodline.index] == "LINEONLYACT"].copy()
    print(f"[EMP_KPI] METROPCS rows found: {len(metropcs)}")
    print(f"[EMP_KPI] Blank prodline rows found: {len(blank_prodline)}")
    print(f"[EMP_KPI] LINEONLYACT rows added from blank prodline: {len(line_only_act)}")

    metropcs_combined = pd.concat([metropcs, line_only_act], ignore_index=True)
    combined_rows = len(metropcs_combined)
    metropcs_combined = metropcs_combined[
        metropcs_combined["category"].fillna("").astype(str).str.strip().str.upper() != "SIM CARDS"
    ].copy()
    print(f"[EMP_KPI] Removed {combined_rows - len(metropcs_combined)} SIM CARDS rows")
    print(f"[EMP_KPI] Final employee METROPCS dataset has {len(metropcs_combined)} rows")

    ppd_summary = (
        metropcs_combined.groupby(key_columns, dropna=False)["qty"]
        .sum()
        .reset_index()
        .rename(columns={"qty": "PPD"})
    )
    ppd_summary["PPD"] = ppd_summary["PPD"].round(2)

    accessory_working = acc_detail.copy()
    accessory_working["Date"] = pd.to_datetime(accessory_working["adddate"], errors="coerce").dt.date
    accessory_working["adduser"] = accessory_working["adduser"].fillna("").astype(str).str.strip()
    accessory_working["Fullname"] = (
        accessory_working["name"].fillna("").astype(str).str.strip() + " " +
        accessory_working["lastname"].fillna("").astype(str).str.strip()
    ).str.strip().str.upper()
    accessory_summary = (
        accessory_working.groupby(key_columns, dropna=False)["Accessory"]
        .sum()
        .reset_index()
    )
    accessory_summary["Accessory"] = accessory_summary["Accessory"].round(2)

    emp_kpi = working_df[key_columns].drop_duplicates().copy()
    emp_kpi = emp_kpi.merge(ppd_summary, on=key_columns, how="left")
    emp_kpi = emp_kpi.merge(accessory_summary, on=key_columns, how="left")
    emp_kpi["PPD"] = emp_kpi["PPD"].fillna(0)
    emp_kpi["Accessory"] = emp_kpi["Accessory"].fillna(0).round(2)
    print(f"[EMP_KPI] Employee KPI table ready with {len(emp_kpi)} unique Date/store/customer/employee rows")

    return emp_kpi


def build_time_punch_pivot(df):
    if df.empty:
        print("[TIMEPUNCH] Source DataFrame is empty. Skipping pivot build")
        return pd.DataFrame(columns=["Date", "company", "hoursworked", "unique_username_count"])

    working_df = df.copy()
    working_df.columns = [str(col).strip() for col in working_df.columns]
    column_lookup = {str(col).strip().lower(): col for col in working_df.columns}
    required_columns = ["clockintime", "company", "hoursworked", "username"]
    missing_columns = [col for col in required_columns if col not in column_lookup]

    if missing_columns:
        print(f"[TIMEPUNCH] Missing required columns for pivot: {missing_columns}")
        return pd.DataFrame(columns=["Date", "company", "hoursworked", "unique_username_count"])

    clockin_col = column_lookup["clockintime"]
    company_col = column_lookup["company"]
    hoursworked_col = column_lookup["hoursworked"]
    username_col = column_lookup["username"]

    working_df["Date"] = pd.to_datetime(working_df[clockin_col], errors="coerce").dt.date
    working_df[hoursworked_col] = pd.to_numeric(working_df[hoursworked_col], errors="coerce").fillna(0)
    working_df[company_col] = working_df[company_col].fillna("").astype(str).str.strip()
    working_df[username_col] = working_df[username_col].fillna("").astype(str).str.strip()

    working_df = working_df[working_df["Date"].notna()].copy()

    pivot_df = (
        working_df.groupby(["Date", company_col], dropna=False)
        .agg(
            hoursworked=(hoursworked_col, "sum"),
            unique_username_count=(username_col, pd.Series.nunique)
        )
        .reset_index()
        .rename(columns={company_col: "company"})
        .sort_values(["Date", "company"], ascending=[True, True])
        .reset_index(drop=True)
    )
    pivot_df["hoursworked"] = pivot_df["hoursworked"].round(2)
    print(f"[TIMEPUNCH] Pivot ready with {len(pivot_df)} Date/company rows")

    return pivot_df


# -------------------- SAVE TO MYSQL --------------------
def save_to_mysql(df):
    return save_table_to_mysql(df, DB_TABLE)


# -------------------- MAIN LOOP --------------------
if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting Accessory_Contest refresh loop")
    while True:
        try:
            print(f"[{datetime.now()}] New refresh cycle started")
            df = fetch_accessory_data()
            time_punch_df = fetch_time_punch_data()
            acc_detail = process_data(df)
            same_day_spiff = build_same_day_spiff_table(df)
            KPI = build_kpi_table(df, acc_detail)
            emp_kpi = build_emp_kpi_table(df, acc_detail)
            time_punch_pivot = build_time_punch_pivot(time_punch_df)

            accessory_exported = save_to_mysql(acc_detail)
            same_day_spiff_exported = save_table_to_mysql(same_day_spiff, SAME_DAY_SPIFF_TABLE)
            kpi_exported = save_table_to_mysql(KPI, KPI_TABLE)
            emp_kpi_exported = save_table_to_mysql(emp_kpi, EMP_KPI_TABLE)
            time_punch_exported = save_table_to_mysql(time_punch_df, TIME_PUNCH_TABLE)
            time_punch_pivot_exported = save_table_to_mysql(time_punch_pivot, TIME_PUNCH_PIVOT_TABLE)

            if (
                not accessory_exported
                or not same_day_spiff_exported
                or not kpi_exported
                or not emp_kpi_exported
                or not time_punch_exported
                or not time_punch_pivot_exported
            ):
                print(f"[{datetime.now()}] Refresh cycle did not complete successfully. Retrying immediately")
                continue

            print(
                f"[{datetime.now()}] Refresh cycle completed successfully: "
                f"{DB_TABLE}={len(acc_detail)} rows, {KPI_TABLE}={len(KPI)} rows, "
                f"{SAME_DAY_SPIFF_TABLE}={len(same_day_spiff)} rows, "
                f"{EMP_KPI_TABLE}={len(emp_kpi)} rows, "
                f"{TIME_PUNCH_TABLE}={len(time_punch_df)} rows, {TIME_PUNCH_PIVOT_TABLE}={len(time_punch_pivot)} rows"
            )
        except Exception as e:
            print(f"[ERROR] Unexpected exception: {e}")

        print(f"[{datetime.now()}] Sleeping for 1200 seconds before next refresh")
        time.sleep(1200)  # 20 minutes before next fetch
