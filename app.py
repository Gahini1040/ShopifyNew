import os
import json
from flask import Flask, request
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.utils import rowcol_to_a1

# ——— Load .env vars ———
load_dotenv()

app = Flask(__name__)

# ——— Google Sheets creds ———
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not creds_json:
    raise RuntimeError("Please set GOOGLE_CREDENTIALS_JSON in your environment")

try:
    creds_dict = json.loads(creds_json)
except json.JSONDecodeError:
    raise RuntimeError("GOOGLE_CREDENTIALS_JSON is not valid JSON")

SCOPES = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
gc = gspread.authorize(credentials)

# ——— Pick your sheet ———
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "gahinitest")

sheet = (gc.open_by_key(SHEET_ID).sheet1
         if SHEET_ID else
         gc.open(SHEET_NAME).sheet1)

# ——— Helpers ———
def convert_for_sheet(data: dict) -> dict:
    """
    Return a dict of { column_name: string_value } for every top‑level key.
    Nested dicts/lists become JSON strings; primitives become str(v) or "" if None.
    """
    flat = {}
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            flat[k] = "" if v is None else str(v)
    return flat

def upsert_customer_row(customer: dict):
    flat = convert_for_sheet(customer)

    # 1) Read existing data
    all_vals = sheet.get_all_values()
    headers = all_vals[0] if all_vals else []

    # 2) Add any missing headers
    for col in flat:
        if col not in headers:
            headers.append(col)

    # 3) Write or update header row
    if not all_vals:
        sheet.append_row(headers)
        all_vals = [headers]
    elif headers != all_vals[0]:
        sheet.update("A1", [headers])
        all_vals[0] = headers

    # 4) Build the row in header order
    new_row = [flat.get(col, "") for col in headers]
    cust_id = flat.get("id", "")

    # 5) Try to find existing row by matching the first column (“id”)
    for idx, row in enumerate(all_vals[1:], start=2):
        if row and row[0] == cust_id:
            end_col = rowcol_to_a1(1, len(headers)).split("1")[0]
            sheet.update(f"A{idx}:{end_col}{idx}", [new_row])
            print(f"✅ Updated row for customer {cust_id}")
            return

    # 6) Not found → append new row
    sheet.append_row(new_row)
    print(f"✅ Inserted row for customer {cust_id}")

def delete_customer_row(customer_id):
    records = sheet.get_all_records()
    for idx, rec in enumerate(records, start=2):
        if str(rec.get("id", "")) == str(customer_id):
            sheet.delete_rows(idx)
            print(f"🗑️ Deleted row for customer {customer_id}")
            return

# ——— Flask endpoints ———

@app.route("/")
def health():
    return "🚀 Shopify‑to‑GoogleSheet running"

@app.route("/webhook/customer/create", methods=["POST"])
@app.route("/webhook/customer/update", methods=["POST"])
def handle_upsert():
    payload = request.get_json(force=True)
    print("📥 Payload:", json.dumps(payload, indent=2))

    # Bulk array?
    if isinstance(payload.get("customers"), list):
        for cust in payload["customers"]:
            upsert_customer_row(cust)
    # Single object?
    elif "id" in payload:
        upsert_customer_row(payload)
    else:
        return "❌ Invalid payload", 400

    return "✅ OK", 200

@app.route("/webhook/customer/delete", methods=["POST"])
def handle_delete():
    payload = request.get_json(force=True)
    cid = payload.get("id")
    if cid is None:
        return "❌ Invalid delete payload", 400
    delete_customer_row(cid)
    return "✅ Deleted", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
