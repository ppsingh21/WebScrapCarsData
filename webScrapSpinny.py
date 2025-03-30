import requests
import pandas as pd
import time
import json
import os
from datetime import datetime

# Constants
BASE_URL = "https://api.spinny.com/v3/api/listing/v3/"
today_str = datetime.now().strftime("%Y-%m-%d")
EXCEL_FILE = f"Spinny_{today_str}.xlsx"
JSON_FILE = "spinny_snapshot.json"

params = {
    "city": "bangalore",
    "product_type": "cars",
    "category": "used",
    "ratio_status": "available",
    "size": 40,
    "page": 1
}

# Load previous snapshot
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        previous_data = json.load(f)
    is_first_run = False
else:
    previous_data = {}
    is_first_run = True

new_or_updated = []
price_drops = []

while True:
    print(f"Fetching page {params['page']}...")
    response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        print(f"Error fetching page {params['page']}: {response.status_code}")
        break

    data = response.json()
    results = data.get("results", [])
    if not results:
        break

    for car in results:
        car_id = str(car.get("id"))
        current_price = car.get("price", 0)
        fetched_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        current = {
            "Name": f"{car.get('make', '')} {car.get('model', '')}",
            "Variant": car.get("variant", ""),
            "Colour": car.get("color", ""),
            "Price (₹)": current_price,
            "KMs Driven": f"{car.get('round_off_mileage_new', '')} km",
            "Fuel": car.get("fuel_type", ""),
            "Transmission": car.get("transmission", ""),
            "Ownership": f"{car.get('no_of_owners', '')}st owner",
            "Year": car.get("make_year", ""),
            "Registration Number": car.get("rto", ""),
            "Image URL": f"https:{car.get('images', [{}])[0].get('file', {}).get('absurl', '')}",
            "Date Fetched": fetched_on
        }

        prev = previous_data.get(car_id)

        if not prev:
            new_or_updated.append(current)
            previous_data[car_id] = current
        else:
            if prev["Price (₹)"] > current_price:
                price_drops.append(current)
            if prev != current:
                new_or_updated.append(current)
                previous_data[car_id] = current

    if not data.get("next"):
        break

    params["page"] += 1
    time.sleep(0.5)

# Export logic
if is_first_run or new_or_updated:
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        pd.DataFrame(new_or_updated).to_excel(writer, sheet_name="NewOrModified", index=False)
        if price_drops:
            pd.DataFrame(price_drops).to_excel(writer, sheet_name="PriceDrops", index=False)
    print(f"\n✅ Exported {len(new_or_updated)} records to '{EXCEL_FILE}'")
else:
    print("\n✅ No new or updated listings. Excel not modified.")

# Save updated snapshot
with open(JSON_FILE, "w") as f:
    json.dump(previous_data, f, indent=2)

print("📦 JSON snapshot updated.")
