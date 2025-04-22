import os
import json
from flask import Flask, request
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.utils import rowcol_to_a1

# ——— Load environment variables from .env ———
load_dotenv()

# ——— Flask setup ———
app = Flask(__name__)

# ——— Google Sheets credential setup ———
# Expect your service‑account JSON in this env var
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not creds_json:
    raise RuntimeError("Missing GOOGLE_CREDENTIALS_JSON environment variable")

try:
    creds_dict = json.loads(creds_json)
except json.JSONDecodeError:
    raise RuntimeError("GOOGLE_CREDENTIALS_JSON is not valid JSON")

# Scopes for reading/writing Sheets & Drive
SCOPES = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]

# Create credentials and authorize
credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
gc = gspread.authorize(credentials)

# ——— Which sheet to use? ———
SHEET_ID   = os.getenv("GOOGLE_SHEET_ID")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "gahinitest")

if SHEET_ID:
    sheet = gc.open_by_key(SHEET_ID).sheet1
else:
    sheet = gc.open(SHEET_NAME).sheet1

# ——— Helpers ———
def convert_for_sheet(data: dict) -> dict:
    """
    Turn nested dicts/lists into JSON strings; leave primitives as-is.
    """
    flat = {}
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, ensure_ascii=False)
        else:
            # Convert None -> "" and everything else to str
            flat[k] = "" if v is None else v
    return flat

def update_google_sheet(customer: dict):
    """
    Upsert a single customer row based on `id`.
    """
    flat = convert_for_sheet(customer)
    all_values = sheet.get_all_values()
    headers = all_values[0] if all_values else []

    # 1) Add any missing headers
    for key in flat:
        if key not in headers:
            headers.append(key)

    # 2) (Re)write header row if needed
    if not all_values:
        sheet.append_row(headers)
        all_values = [headers]
    elif headers != all_values[0]:
        sheet.update("A1", [headers])
        all_values[0] = headers

    # 3) Build the row in header order
    row = [flat.get(col, "") for col in headers]
    cust_id = str(flat.get("id", ""))

    # 4) Try to find existing row with same ID and update
    for idx, existing in enumerate(all_values[1:], start=2):
        if existing and existing[0] == cust_id:
            # Determine last column letter
            end_col = rowcol_to_a1(1, len(headers)).split("1")[0]
            sheet.update(f"A{idx}:{end_col}{idx}", [row])
            print(f"✅ Updated customer {cust_id}")
            return

    # 5) Otherwise append new row
    sheet.append_row(row)
    print(f"✅ Inserted customer {cust_id}")

def delete_customer_from_sheet(customer_id):
    """
    Delete the row matching customer_id.
    """
    records = sheet.get_all_records()
    for idx, rec in enumerate(records, start=2):
        if str(rec.get("id")) == str(customer_id):
            sheet.delete_rows(idx)
            print(f"🗑️ Deleted customer {customer_id}")
            return

# ——— Flask routes ———

@app.route("/")
def index():
    return "🚀 Shopify‑to‑GoogleSheet Webhook Receiver"

@app.route("/webhook/customer/create", methods=["POST"])
@app.route("/webhook/customer/update", methods=["POST"])
def upsert_customer():
    payload = request.get_json(force=True)
    print("📥 Payload:", json.dumps(payload, indent=2))

    # Bulk payload?
    if isinstance(payload.get("customers"), list):
        for cust in payload["customers"]:
            update_google_sheet(cust)
    # Single customer?
    elif payload.get("id"):
        update_google_sheet(payload)
    else:
        return "❌ Invalid payload", 400

    return "✅ Success", 200

@app.route("/webhook/customer/delete", methods=["POST"])
def remove_customer():
    payload = request.get_json(force=True)
    cid = payload.get("id")
    if cid:
        delete_customer_from_sheet(cid)
        return "✅ Deleted", 200
    return "❌ Invalid delete payload", 400

# ——— Run the app ———
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    # debug=True will reload on changes; remove for production
    app.run(host="0.0.0.0", port=port, debug=True)
