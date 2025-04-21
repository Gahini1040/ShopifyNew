from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Write credentials JSON from env to file
def write_credentials_file():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        with open("creditional.json", "w") as f:
            json.dump(json.loads(creds_json), f)

write_credentials_file()

CREDENTIALS_FILE   = "creditional.json"
GOOGLE_SHEET_NAME  = os.getenv("GOOGLE_SHEET_NAME", "shopifycustomerlist")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")

# Google Sheet connection
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# Update or insert a single row with JSON string
def update_google_sheet(customer_data):
    print("📝 Updating Google Sheet with customer data:", customer_data)
    client = get_gsheet_client()

    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 if GOOGLE_SHEET_ID else client.open(GOOGLE_SHEET_NAME).sheet1

    all_data = sheet.get_all_records()
    headers = sheet.row_values(1)
    
    # Ensure headers are set
    if "id" not in headers or "customer_json" not in headers:
        headers = ["id", "customer_json"]
        sheet.update("A1", [headers])

    customer_id = str(customer_data["id"])
    customer_json = json.dumps(customer_data)

    # Check if customer already exists
    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == customer_id:
            sheet.update(f"A{idx}", [[customer_id, customer_json]])
            print(f"✅ Updated existing customer {customer_id}")
            return

    # If not found, append
    sheet.append_row([customer_id, customer_json])
    print(f"✅ Inserted new customer {customer_id}")

# Delete row in Google Sheet
def delete_customer_from_sheet(customer_id):
    client = get_gsheet_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 if GOOGLE_SHEET_ID else client.open(GOOGLE_SHEET_NAME).sheet1
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
    print("📥 Received customer create/update:", json.dumps(data, indent=2))

    # Handle Shopify format where data is under "customers" array
    if data and "customers" in data and isinstance(data["customers"], list):
        customer = data["customers"][0]
    else:
        customer = data

    if customer and "id" in customer:
        update_google_sheet(customer)
        return "Customer processed", 200

    print("❌ Invalid data received.")
    return "Invalid data", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    print("📥 Received customer delete:", json.dumps(data, indent=2))

    customer_id = None
    if "id" in data:
        customer_id = data["id"]
    elif "customers" in data and data["customers"]:
        customer_id = data["customers"][0].get("id")

    if customer_id:
        delete_customer_from_sheet(customer_id)
        return "Customer deleted", 200

    print("❌ Invalid delete webhook payload.")
    return "Invalid data", 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
