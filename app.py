from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# from config import CREDENTIALS_FILE,GOOGLE_SHEET_NAME
import os
CREDENTIALS_FILE   = os.getenv("CREDENTIALS_FILE", "creditional.json")
GOOGLE_SHEET_NAME  = os.getenv("GOOGLE_SHEET_NAME", "Cust_Information")


app = Flask(__name__)
# GOOGLE_SHEET_NAME = "Cust_Information"  # Your Google Sheet name

def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

def update_google_sheet(customer_data):
    client = get_gsheet_client()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    all_data = sheet.get_all_records()
    headers = sheet.row_values(1)

    # Prepare new row with existing headers
    new_row = [customer_data.get(col, "") for col in headers]

    # Check if customer already exists
    for idx, row in enumerate(all_data, start=2):  # start=2 because headers are in row 1
        if str(row.get("id")) == str(customer_data["id"]):
            sheet.update(f"A{idx}", [new_row])
            print(f"✅ Updated customer {customer_data['id']}")
            return

    # If customer not found, insert new
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
    app.run(port=5000)
