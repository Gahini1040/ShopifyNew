from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from dotenv import load_dotenv
from gspread.utils import rowcol_to_a1
import requests

load_dotenv()
app = Flask(__name__)

# --- Write credentials JSON from env to file ---
def write_credentials_file():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        with open("creditional.json", "w") as f:
            json.dump(json.loads(creds_json), f)

write_credentials_file()

# --- Env Vars ---
CREDENTIALS_FILE = "creditional.json"
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "shopifycustomerlist")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASSWORD = os.getenv("SHOPIFY_API_PASSWORD")
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")

# --- Convert to column: raw JSON for nested, plain for top-level ---
def convert_for_sheet(data):
    flat = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat

# --- Google Sheet connection ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# --- Fetch full customer data from Shopify ---
def fetch_full_customer_data(customer_id):
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_URL}/admin/api/2025-04/customers/{customer_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("customer")
    else:
        print(f"❌ Failed to fetch full customer data: {response.status_code}")
        return None

# --- Insert or update row ---
def update_google_sheet(customer_data):
    print("📝 Updating Google Sheet...")
    client = get_gsheet_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 if GOOGLE_SHEET_ID else client.open(GOOGLE_SHEET_NAME).sheet1

    all_rows = sheet.get_all_values()
    headers = all_rows[0] if all_rows else []
    flat = convert_for_sheet(customer_data)
    updated = False

    for key in flat:
        if key not in headers:
            headers.append(key)

    if not all_rows:
        sheet.append_row(headers)
    elif headers != all_rows[0]:
        sheet.update("A1", [headers])

    new_row = [str(flat.get(col, "")) for col in headers]

    for idx, row in enumerate(all_rows[1:], start=2):
        if row and row[headers.index("id")] == str(customer_data["id"]):
            end_col_letter = rowcol_to_a1(1, len(headers)).split("1")[0]
            sheet.update(f"A{idx}:{end_col_letter}{idx}", [new_row])
            print(f"✅ Updated customer ID {customer_data['id']}")
            updated = True
            break

    if not updated:
        sheet.append_row(new_row)
        print(f"✅ Inserted new customer ID {customer_data['id']}")

# --- Delete from sheet ---
def delete_customer_from_sheet(customer_id):
    client = get_gsheet_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 if GOOGLE_SHEET_ID else client.open(GOOGLE_SHEET_NAME).sheet1
    all_data = sheet.get_all_records()

    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == str(customer_id):
            sheet.delete_rows(idx)
            print(f"🗑️ Deleted customer {customer_id}")
            return

# --- Routes ---
@app.route("/")
def index():
    return "🚀 Flask app is running!"

@app.route("/webhook/customer/create", methods=["POST"])
@app.route("/webhook/customer/update", methods=["POST"])
def customer_create_or_update():
    data = request.get_json()
    print("📥 Received customer webhook:", json.dumps(data, indent=2))

    # Handle multiple customers (bulk webhook)
    if "customers" in data and isinstance(data["customers"], list):
        for customer in data["customers"]:
            full_data = fetch_full_customer_data(customer["id"])
            if full_data:
                update_google_sheet(full_data)
        return "Multiple customers processed", 200

    # Handle single customer
    if "id" in data:
        full_data = fetch_full_customer_data(data["id"])
        if full_data:
            update_google_sheet(full_data)
            return "Customer processed (full data)", 200

    return "❌ Invalid customer payload", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    print("📥 Received delete webhook:", json.dumps(data, indent=2))
    if data and "id" in data:
        delete_customer_from_sheet(data["id"])
        return "Customer deleted", 200
    return "❌ Invalid delete payload", 400

# --- Run App ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
