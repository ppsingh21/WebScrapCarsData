import requests
import pandas as pd
import time
import json
import os
from datetime import datetime

# Constants
today_str = datetime.now().strftime("%Y-%m-%d")
EXCEL_FILE = f"Cars24_{today_str}.xlsx"
JSON_FILE = "Cars24_snapshot.json"
API_URL = "https://car-catalog-gateway-in.c24.tech/listing/v1/buy-used-cars-bangalore"

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/json'
}

def strip_nonessential_fields(data):
    """Remove fields that shouldn't affect change detection."""
    return {k: v for k, v in data.items() if k not in ["Date Fetched"]}

# Load previous snapshot
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        previous_data = json.load(f)
    is_first_run = False
else:
    previous_data = {}
    is_first_run = True

# API payload
payload = {
    "searchFilter": [],
    "cityId": "4709",
    "sort": "bestmatch",
    "size": 1000,
    "filterVersion": 1
}

new_or_updated = []
price_drops = []
all_fetched_data = {}
page = 1

while True:
    print(f"Fetching page {page}...")
    response = requests.post(API_URL, headers=headers, json=payload)
    data = response.json()

    cars = data.get("content", [])
    if not cars:
        break

    for car in cars:
        car_id = str(car.get("appointmentId"))
        current_price = car.get("listingPrice", 0)
        fetched_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        current = {
            "Name": car.get("carName", ""),
            "Variant": car.get("variant", ""),
            "Colour": car.get("color", ""),
            "Price (₹)": current_price,
            "KMs Driven": car.get("odometer", {}).get("display", ""),
            "Fuel": car.get("fuelType", ""),
            "Transmission": car.get("transmissionType", {}).get("value", ""),
            "Ownership": f"{car.get('ownership', '')}st owner",
            "Year": car.get("year", ""),
            "Registration Number": car.get("maskedRegNum", ""),
            "Image URL": car.get("listingImage", {}).get("uri", ""),
            "Date Fetched": fetched_on
        }

        all_fetched_data[car_id] = current  # Track for full export if first time

        prev = previous_data.get(car_id)

        if not prev:
            new_or_updated.append(current)
        else:
            prev_price = prev.get("Price (₹)", 0)
                    
            # ✅ Track price changes in either direction
            if prev_price != current_price:
                current["Previous Price (₹)"] = prev_price
                current["Price Changed"] = "Decreased" if prev_price > current_price else "Increased"
                price_drops.append(current)
            
            # ✅ Compare meaningful fields only
            if strip_nonessential_fields(prev) != strip_nonessential_fields(current):
                new_or_updated.append(current)

    search_after = data.get("searchAfter")
    if not search_after:
        break

    payload["searchAfter"] = search_after
    page += 1
    time.sleep(0.5)

# Export logic
if is_first_run:
    df_all = pd.DataFrame(all_fetched_data.values())
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df_all.to_excel(writer, sheet_name="AllCars", index=False)
    print(f"\n🆕 First run — exported all {len(df_all)} records to '{EXCEL_FILE}'")
elif new_or_updated:
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        pd.DataFrame(new_or_updated).to_excel(writer, sheet_name="NewOrModified", index=False)
        if price_drops:
            pd.DataFrame(price_drops).to_excel(writer, sheet_name="PriceDrops", index=False)
    print(f"\n✅ Exported {len(new_or_updated)} new/updated records to '{EXCEL_FILE}'")
else:
    print("\n✅ No new or updated listings. Excel not modified.")

# Save updated snapshot
with open(JSON_FILE, "w") as f:
    json.dump(all_fetched_data, f, indent=2)

print("📦 JSON snapshot updated.")
