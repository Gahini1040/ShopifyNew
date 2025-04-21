from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os,json

from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)

# Write credentials JSON from env to file (at runtime)
def write_credentials_file():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        with open("credentials.json", "w") as f:
            json.dump(json.loads(creds_json), f)

write_credentials_file()

# Read secrets from environment
CREDENTIALS_FILE   = "credentials.json"
GOOGLE_SHEET_NAME  = os.getenv("GOOGLE_SHEET_NAME", "Cust_Information")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")
SHOP_URL           = os.getenv("SHOP_URL")
API_VERSION        = os.getenv("API_VERSION")
ACCESS_TOKEN       = os.getenv("ACCESS_TOKEN")

def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

def update_google_sheet(customer_data):
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    all_data = sheet.get_all_records()
    headers = sheet.row_values(1)
    new_row = [customer_data.get(col, "") for col in headers]

    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == str(customer_data["id"]):
            sheet.update(f"A{idx}", [new_row])
            print(f"✅ Updated customer {customer_data['id']}")
            return
    sheet.append_row(new_row)
    print(f"✅ Inserted new customer {customer_data['id']}")

def delete_customer_from_sheet(customer_id):
    client = get_gsheet_client()
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
    if data and "id" in data:
        update_google_sheet(data)
        return "Customer processed", 200
    return "Invalid data", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    if data and "id" in data:
        delete_customer_from_sheet(data["id"])
        return "Customer deleted", 200
    return "Invalid data", 400

if __name__ == "__main__":
    # app.run(port=5000)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
