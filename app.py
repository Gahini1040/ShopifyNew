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
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "shopifycustomerlist")
GOOGLE_ORDER_SHEET = os.getenv("GOOGLE_ORDER_SHEET", "shopifyorderlist")
GOOGLE_PRODUCT_SHEET = os.getenv("GOOGLE_PRODUCT_SHEET", "shopifyproductlist")

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_PASSWORD = os.getenv("SHOPIFY_API_PASSWORD")
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")

# --- Flatten JSON for sheet ---
def convert_for_sheet(data):
    flat = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat

# --- Google Sheet client ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    return gspread.authorize(creds)

# --- Fetch full data from Shopify ---
def fetch_from_shopify(resource, resource_id):
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_STORE_URL}/admin/api/2025-04/{resource}/{resource_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get(resource[:-1])  # "customers" -> "customer"
    else:
        print(f"❌ Failed to fetch {resource[:-1]} {resource_id}: {response.status_code}")
        return None

# --- Insert or update row ---
def update_google_sheet(data, sheet_type="customers"):
    print("📝 Updating Google Sheet...")
    client = get_gsheet_client()

    sheet_name = {
        "customers": GOOGLE_SHEET_NAME,
        "orders": GOOGLE_ORDER_SHEET,
        "products": GOOGLE_PRODUCT_SHEET
    }.get(sheet_type, GOOGLE_SHEET_NAME)

    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID) if GOOGLE_SHEET_ID else client.open(sheet_name)

    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ Worksheet '{sheet_name}' not found. Creating...")
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")

    all_rows = sheet.get_all_values()
    headers = all_rows[0] if all_rows else []
    flat = convert_for_sheet(data)
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
        if row and "id" in flat and row[headers.index("id")] == str(flat["id"]):
            end_col_letter = rowcol_to_a1(1, len(headers)).split("1")[0]
            sheet.update(f"A{idx}:{end_col_letter}{idx}", [new_row])
            print(f"✅ Updated ID {flat['id']}")
            updated = True
            break

    if not updated:
        sheet.append_row(new_row)
        print(f"✅ Inserted new ID {flat.get('id', '[no id]')}")

# --- Delete row from sheet ---
def delete_row_by_id(item_id, sheet_type="customers"):
    client = get_gsheet_client()

    sheet_name = {
        "customers": GOOGLE_SHEET_NAME,
        "orders": GOOGLE_ORDER_SHEET,
        "products": GOOGLE_PRODUCT_SHEET
    }.get(sheet_type, GOOGLE_SHEET_NAME)

    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID) if GOOGLE_SHEET_ID else client.open(sheet_name)

    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"❌ Sheet '{sheet_name}' not found.")
        return

    all_data = sheet.get_all_records()

    for idx, row in enumerate(all_data, start=2):
        if str(row.get("id")) == str(item_id):
            sheet.delete_rows(idx)
            print(f"🗑️ Deleted ID {item_id} from {sheet_name}")
            return

# --- Routes ---
@app.route("/")
def index():
    return "🚀 Shopify + Google Sheets Flask App is Running!"

# --- Customer Webhooks ---
@app.route("/webhook/customer/create", methods=["POST"])
@app.route("/webhook/customer/update", methods=["POST"])
def customer_create_or_update():
    data = request.get_json()
    print("📥 Customer webhook received:", json.dumps(data, indent=2))

    if "id" in data:
        full_data = fetch_from_shopify("customers", data["id"])
        if full_data:
            update_google_sheet(full_data, sheet_type="customers")
            return "Customer processed", 200

    return "❌ Invalid customer payload", 400

@app.route("/webhook/customer/delete", methods=["POST"])
def customer_delete():
    data = request.get_json()
    print("📥 Customer delete webhook:", json.dumps(data, indent=2))
    if "id" in data:
        delete_row_by_id(data["id"], sheet_type="customers")
        return "Customer deleted", 200
    return "❌ Invalid delete payload", 400

# --- Product Webhooks ---
@app.route("/webhook/product/create", methods=["POST"])
@app.route("/webhook/product/update", methods=["POST"])
def product_create_or_update():
    data = request.get_json()
    print("📥 Product webhook received:", json.dumps(data, indent=2))

    if "id" in data:
        full_data = fetch_from_shopify("products", data["id"])
        if full_data:
            update_google_sheet(full_data, sheet_type="products")
            return "Product processed", 200

    return "❌ Invalid product payload", 400

@app.route("/webhook/product/delete", methods=["POST"])
def product_delete():
    data = request.get_json()
    print("📥 Product delete webhook:", json.dumps(data, indent=2))
    if "id" in data:
        delete_row_by_id(data["id"], sheet_type="products")
        return "Product deleted", 200
    return "❌ Invalid delete payload", 400

# --- Order Webhooks ---
@app.route("/webhook/order/create", methods=["POST"])
@app.route("/webhook/order/update", methods=["POST"])
def order_create_or_update():
    data = request.get_json()
    print("📥 Order webhook received:", json.dumps(data, indent=2))

    if "id" in data:
        full_data = fetch_from_shopify("orders", data["id"])
        if full_data:
            update_google_sheet(full_data, sheet_type="orders")
            return "Order processed", 200

    return "❌ Invalid order payload", 400

@app.route("/webhook/order/delete", methods=["POST"])
def order_delete():
    data = request.get_json()
    print("📥 Order delete webhook:", json.dumps(data, indent=2))
    if "id" in data:
        delete_row_by_id(data["id"], sheet_type="orders")
        return "Order deleted", 200
    return "❌ Invalid delete payload", 400

# --- Run ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
