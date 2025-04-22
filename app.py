from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

app = Flask(__name__)

# Google Sheets setup
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")  # This should be the JSON string of your credentials
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "gahinitest")  # Sheet name from env or default

# Load credentials from environment variable
creds_dict = json.loads(CREDS_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

def flatten_customer(customer):
    """Convert nested dicts/lists to JSON strings for storage"""
    flat = {}
    for key, value in customer.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat

def update_google_sheet(customer_data):
    flat = flatten_customer(customer_data)
    headers = sheet.row_values(1)
    all_rows = sheet.get_all_values()

    # If sheet is empty, write headers
    if not headers:
        headers = list(flat.keys())
        sheet.append_row(headers)
    else:
        # Add any missing headers
        for key in flat:
            if key not in headers:
                headers.append(key)
        if headers != sheet.row_values(1):
            sheet.update("A1", [headers])

    id_index = headers.index("id") if "id" in headers else None
    customer_id = str(flat["id"])

    # Check if customer already exists
    found = False
    for i, row in enumerate(all_rows[1:], start=2):  # Skip header
        if id_index is not None and len(row) > id_index and row[id_index] == customer_id:
            # Update row
            updated_row = [flat.get(h, "") for h in headers]
            sheet.update(f"A{i}", [updated_row])
            found = True
            break

    if not found:
        # Append new row
        new_row = [flat.get(h, "") for h in headers]
        sheet.append_row(new_row)

@app.route('/webhook/customer/create', methods=['POST'])
@app.route('/webhook/customer/update', methods=['POST'])
def customer_webhook():
    data = request.get_json()
    if not data:
        return "Invalid JSON", 400

    try:
        if "customers" in data and isinstance(data["customers"], list):
            for customer in data["customers"]:
                update_google_sheet(customer)
        elif "id" in data:
            update_google_sheet(data)
        else:
            return "Invalid customer data", 400
    except Exception as e:
        return f"Error processing customer data: {str(e)}", 500

    return "Customer data updated", 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
