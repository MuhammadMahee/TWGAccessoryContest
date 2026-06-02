import time
import random
import string
import hashlib
import requests
import pandas as pd
import json
import re
from datetime import datetime

import cookie  # your cookie.py
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.types import String

# -------------------- CONFIG --------------------
DB_USER = "twg_admin"
DB_PASS = "twg_admin"
DB_HOST = "127.0.0.1"  # localhost
DB_PORT = "3306"
DB_SCHEMA = "TWG"
DB_TABLE = "Logins"
RAW_DB_TABLE = "idm_by_user"

URL = "https://www.myrtpos.com/newbdi/IDMUserStores.fwx"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.myrtpos.com/newbdi/IDMUserStores.fwx",
    "Content-Type": "application/x-www-form-urlencoded",
}

PAYLOAD = {
    "frmMarketID": "",
    "frmRegionID": "",
    "frmStateID": "",
    "frmPrinciple": "",
    "frmStore": "",
    "btnExcel": "click",
}


# -------------------- UTILITIES --------------------
def generate_code():
    chars = string.ascii_letters + string.digits
    return f"{''.join(random.choices(chars, k=4))}-{''.join(random.choices(chars, k=4))}"


def sanitize_column_name(column_name):
    sanitized = re.sub(r"[^0-9a-zA-Z_]+", "_", str(column_name).strip().lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")

    if not sanitized:
        sanitized = "column"
    if sanitized[0].isdigit():
        sanitized = f"col_{sanitized}"

    return sanitized


def normalize_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value).strip()


def prepare_raw_df(raw_df):
    prepared_df = raw_df.copy()
    prepared_df.columns = [sanitize_column_name(col) for col in prepared_df.columns]
    prepared_df = prepared_df.loc[:, ~prepared_df.columns.duplicated()]
    prepared_df = prepared_df.fillna("")

    row_strings = prepared_df.apply(
        lambda row: "|".join(normalize_value(value) for value in row.values),
        axis=1,
    )
    prepared_df["row_hash"] = row_strings.apply(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    )

    return prepared_df


# -------------------- DATABASE ENGINE --------------------
ENGINE_ROOT = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/")
ENGINE_DB = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_SCHEMA}")


# -------------------- INIT DATABASE --------------------
def init_database():
    with ENGINE_ROOT.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_SCHEMA}"))
        print(f"Schema checked/created: {DB_SCHEMA}")

    with ENGINE_DB.connect() as conn:
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {DB_TABLE} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE,
            code VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """))
        print(f"Table checked/created: {DB_TABLE}")


def init_raw_table(raw_df):
    inspector = inspect(ENGINE_DB)

    if not inspector.has_table(RAW_DB_TABLE):
        raw_df.head(0).to_sql(
            RAW_DB_TABLE,
            ENGINE_DB,
            if_exists="replace",
            index=False,
            dtype={"row_hash": String(64)},
        )
        print(f"Table created: {RAW_DB_TABLE}")

    inspector = inspect(ENGINE_DB)
    existing_columns = {col["name"] for col in inspector.get_columns(RAW_DB_TABLE)}
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(RAW_DB_TABLE)}
    row_hash_index_name = f"idx_{RAW_DB_TABLE}_row_hash"

    with ENGINE_DB.begin() as conn:
        if "row_hash" not in existing_columns:
            conn.execute(text(f"ALTER TABLE {RAW_DB_TABLE} ADD COLUMN row_hash VARCHAR(64)"))
        else:
            conn.execute(text(f"ALTER TABLE {RAW_DB_TABLE} MODIFY COLUMN row_hash VARCHAR(64)"))

        if row_hash_index_name not in existing_indexes:
            conn.execute(text(f"""
            CREATE UNIQUE INDEX {row_hash_index_name}
            ON {RAW_DB_TABLE} (row_hash)
            """))

    print(f"Raw table checked/updated: {RAW_DB_TABLE}")


# -------------------- LOAD EXISTING USERS --------------------
def load_existing_users():
    try:
        df = pd.read_sql(f"SELECT username, code FROM {DB_TABLE}", ENGINE_DB)
        return dict(zip(df["username"], df["code"]))
    except Exception as e:
        print(f"No existing users in DB: {e}")
        return {}


def load_existing_row_hashes():
    try:
        df = pd.read_sql(f"SELECT row_hash FROM {RAW_DB_TABLE}", ENGINE_DB)
        return set(df["row_hash"].dropna().tolist())
    except Exception as e:
        print(f"No existing IDM raw rows in DB: {e}")
        return set()


# -------------------- SAVE NEW DATA --------------------
def save_new_users(df):
    if not df.empty:
        df.to_sql(DB_TABLE, ENGINE_DB, if_exists="append", index=False)
        print(f"Inserted {len(df)} new users into DB")
    else:
        print("No new users to insert")


def save_new_raw_rows(df):
    if not df.empty:
        df.to_sql(RAW_DB_TABLE, ENGINE_DB, if_exists="append", index=False)
        print(f"Inserted {len(df)} new raw IDM rows into DB")
    else:
        print("No new raw IDM rows to insert")


# -------------------- MAIN LOGIC --------------------
def run_idm_user_report():
    print(f"\n[{datetime.now()}] Fetching IDM User Data\n")

    try:
        response = requests.post(URL, data=PAYLOAD, headers=HEADERS, cookies=cookie.cookie)
        if response.status_code != 200:
            raise RuntimeError(f"Request failed: {response.status_code}")

        html = response.text
        match = re.search(r"let\s+data\s*=\s*(\[\{.*?\}\]);", html, re.DOTALL)
        if not match:
            raise RuntimeError("Data section not found")

        data = json.loads(match.group(1))
        df = pd.DataFrame(data)
        if df.empty or "username" not in df.columns:
            raise RuntimeError("No valid username data found")

    except Exception as e:
        print(f"[ERROR] Error fetching data: {e}")
        return

    raw_df = prepare_raw_df(df)

    # -------------------- DATABASE INIT --------------------
    init_database()
    init_raw_table(raw_df)

    user_code_map = load_existing_users()
    print(f"Loaded existing users from DB: {len(user_code_map)}")

    # Assign persistent codes
    users_df = df[["username"]].dropna().drop_duplicates().reset_index(drop=True)
    new_users = 0
    for user in users_df["username"]:
        if user not in user_code_map:
            user_code_map[user] = generate_code()
            new_users += 1

    final_df = (
        pd.DataFrame(user_code_map.items(), columns=["username", "code"])
        .sort_values("username")
        .reset_index(drop=True)
    )

    # Insert only truly new users
    existing_df = pd.DataFrame(list(user_code_map.items()), columns=["username", "code"])
    db_existing_users = load_existing_users()
    db_existing_set = set(db_existing_users.keys())
    insert_df = existing_df[~existing_df["username"].isin(db_existing_set)]
    save_new_users(insert_df)

    # Insert only brand-new raw IDM rows
    existing_row_hashes = load_existing_row_hashes()
    new_raw_rows_df = raw_df[~raw_df["row_hash"].isin(existing_row_hashes)].copy()
    save_new_raw_rows(new_raw_rows_df)

    print(
        f"[{datetime.now()}] Total Users: {len(final_df)} | "
        f"New Users Added: {new_users} | New Raw Rows Added: {len(new_raw_rows_df)}"
    )


# -------------------- RUN INFINITE LOOP --------------------
if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting IDM User Report Auto-Loop...")
    while True:
        try:
            run_idm_user_report()
        except Exception as e:
            print(f"[ERROR] Unexpected exception: {e}")
        time.sleep(60)  # 60 seconds between runs
