import requests
from concurrent.futures import ThreadPoolExecutor

url = "https://www.myrtpos.com/newbdi/TimePunches.fwx"

payload = {
    "frmMarketID": "",
    "frmStateID": "",
    "frmRegionID": "",
    "frmStoreType": "",
    "frmStore": "",
    "frmStart": "04/05/2026",
    "frmEnd": "04/05/2026",
    "btnExcel": "click"
}

cookies = {
    "FW_SessionID": "642723VGD02",
    "sec85952EAF_id": "twg.dev",
    "sec85952EAF_pd": "BEC61796"
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded"
}

def hit(i):
    try:
        response = requests.post(url, data=payload, cookies=cookies, headers=headers)
        print(f"Hit {i}: {response.status_code}")
    except Exception as e:
        print(f"Hit {i}: Error {e}")

# Run 5 hits in parallel
with ThreadPoolExecutor(max_workers=10000) as executor:
    executor.map(hit, range(1, 10001))