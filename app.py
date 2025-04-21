from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from dotenv import load_dotenv

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
CREDENTIALS_FILE   = "creditional.json"
GOOGLE_SHEET_NAME  = os.getenv("GOOGLE_SHEET_NAME", "shopifycustomerlist")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")

# --- Flatten nested JSON ---
def flatten_json(y, parent_key='', sep='.'):
    items = []
    if isinstance(y, list):
        if y and isinstance(y[0], dict):
            y = y[0]  # Flatten first dict in list
        else:
            return {parent_key: json.dumps(y)}  # Save raw list
    for k, v in y.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v)))  # Save list as JSON string
        else:
            items.append((new_key, v))
    return dict(items)

# --- Google Sheet connection ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# --- Insert or update customer row ---
def update_google_sheet(customer_data):
    print("📝 Updating Google Sheet...")
    client = get_gsheet_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 if GOOGLE_SHEET_ID else client.open(GOOGLE_SHEET_NAME).sheet1

    all_rows = sheet.get_all_values()
    flat = flatten_json(customer_data)
    headers = all_rows[0] if all_rows else []
    updated = False

    # Add any new columns (headers)
    for key in flat:
        if key not in headers:
            headers.append(key)
    if not all_rows:
        sheet.append_row(headers)
    elif headers != all_rows[0]:
        sheet.update("A1", [headers])

    # New row values (aligned with headers)
    new_row = [str(flat.get(col, "")) for col in headers]

    # Check if customer already exists
    for idx, row in enumerate(all_rows[1:], start=2):
        if row and row[headers.index("id")] == str(customer_data["id"]):
            sheet.update(f"A{idx}", [new_row])
            print(f"✅ Updated customer ID {customer_data['id']}")
            updated = True
            break

    if not updated:
        sheet.append_row(new_row)
        print(f"✅ Inserted new customer ID {customer_data['id']}")

# --- Delete customer from sheet ---
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

    # Support webhook payloads that include { "customers": [ ... ] }
    if "customers" in data and isinstance(data["customers"], list):
        for customer in data["customers"]:
            update_google_sheet(customer)
        return "Multiple customers processed", 200

    if "id" in data:
        update_google_sheet(data)
        return "Customer processed", 200

    return "❌ Invalid customer payload", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    print("📥 Received delete webhook:", json.dumps(data, indent=2))
    if data and "id" in data:
        delete_customer_from_sheet(data["id"])
        return "Customer deleted", 200
    return "❌ Invalid delete payload", 400

# --- Main ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
