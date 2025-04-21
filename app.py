from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Write credentials JSON from env to file (at runtime)
def write_credentials_file():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        with open("creditional.json", "w") as f:
            json.dump(json.loads(creds_json), f)

write_credentials_file()

# Read secrets from environment
CREDENTIALS_FILE   = "creditional.json"
GOOGLE_SHEET_NAME  = os.getenv("GOOGLE_SHEET_NAME", "shopifycustomerlist")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")
SHOP_URL           = os.getenv("SHOP_URL")
API_VERSION        = os.getenv("API_VERSION")
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")

# Flatten nested JSON
def flatten_json(y, parent_key='', sep='.'):
    items = []
    if isinstance(y, list):
        # Process only the first item in the list, if it's a dict
        if y and isinstance(y[0], dict):
            y = y[0]
        else:
            return {parent_key: y}
    for k, v in y.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

# Google Sheet connection
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# Update or append row in Google Sheet
def update_google_sheet(customer_data):
    print("📝 Updating Google Sheet with data:", customer_data)
    client = get_gsheet_client()
    
    # Open sheet by ID or name
    if GOOGLE_SHEET_ID:
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    else:
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    
    all_data = sheet.get_all_records()
    headers = sheet.row_values(1)
    print("📋 Sheet headers:", headers)

    # Flatten customer data
    flat_data = flatten_json(customer_data)
    print("📦 Flattened data:", flat_data)

    # Check if all columns exist in headers, if not, add them
    for key in flat_data.keys():
        if key not in headers:
            headers.append(key)
            sheet.update('A1', [headers])  # Update the header row

    # Create a new row based on the flattened data
    new_row = [flat_data.get(col, "") for col in headers]
    print("🆕 New row to insert/update:", new_row)

    # Check if this customer already exists in the sheet, if so, update it
    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == str(customer_data["id"]):
            sheet.update(f"A{idx}", [new_row])
            print(f"✅ Updated customer {customer_data['id']}")
            return

    # If the customer doesn't exist, append a new row
    sheet.append_row(new_row)
    print(f"✅ Inserted new customer {customer_data['id']}")

# Delete row in Google Sheet
def delete_customer_from_sheet(customer_id):
    client = get_gsheet_client()
    
    if GOOGLE_SHEET_ID:
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    else:
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1

    all_data = sheet.get_all_records()
    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == str(customer_id):
            sheet.delete_rows(idx)
            print(f"🗑️ Deleted customer {customer_id}")
            return

@app.route("/")
def index():
    return "🚀 Flask app is running!"

@app.route("/webhook/customer/create", methods=["POST"])
@app.route("/webhook/customer/update", methods=["POST"])
def customer_create_or_update():
    data = request.get_json()
    print("📥 Incoming customer create/update webhook:", json.dumps(data, indent=2))
    if data and "id" in data:
        update_google_sheet(data)
        return "Customer processed", 200
    print("❌ Invalid data received.")
    return "Invalid data", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    print("📥 Incoming customer delete webhook:", json.dumps(data, indent=2))
    if data and "id" in data:
        delete_customer_from_sheet(data["id"])
        return "Customer deleted", 200
    print("❌ Invalid delete webhook payload.")
    return "Invalid data", 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
