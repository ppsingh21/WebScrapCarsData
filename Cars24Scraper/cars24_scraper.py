import requests, json, os, time
import pandas as pd
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Telegram credentials
os.environ["TELEGRAM_TOKEN"] = "7698578725:AAFbPdl3eWNvotkNKt2vu6aTN3KTpsXRpQk"
os.environ["TELEGRAM_CHAT_ID"] = "6975035469"

TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = os.path.join(SCRIPT_DIR, f"Cars24_{TODAY}.xlsx")
SNAPSHOT_FILE = os.path.join(SCRIPT_DIR, "cars24_snapshot.json")

API_URL = "https://car-catalog-gateway-in.c24.tech/listing/v1/buy-used-cars-bangalore"

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/json'
}

# define your cities & their IDs here:
CITIES = [
    {"slug": "bangalore", "cityId": "4709"},
    {"slug": "mumbai", "cityId": "2378"},
    {"slug": "delhi-ncr", "cityId": "132"},
    {"slug": "kolkata", "cityId": "777"},
    {"slug": "hyderabad", "cityId": "3686"},
    {"slug": "chennai", "cityId": "5732"},
]

def send_telegram_alert(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_ids = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_ids:
        return
    for chat_id in chat_ids.split(","):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id.strip(),
            "text": message
        }
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"❌ Failed to send Telegram message to {chat_id}: {e}")

def fetch_data_for_city(slug, city_id):
    """
    Fetch all pages for a single city slug/cityId combination.
    Returns a dict of {appointmentId: record_dict}
    """
    api_url = f"https://car-catalog-gateway-in.c24.tech/listing/v1/buy-used-cars-{slug}"
    payload = {
        "searchFilter": [],
        "cityId": city_id,
        "sort": "bestmatch",
        "size": 20,
        "filterVersion": 2
    }

    all_data = {}
    page = 1

    while True:
        print(f"Fetching {slug} page {page}...")
        res = requests.post(api_url, headers=HEADERS, json=payload)
        if res.status_code != 200:
            print(f"❌ Error: {res.status_code}")
            break

        cars = res.json().get("content", [])
        if not cars:
            break

        for car in cars:
            cid = str(car["appointmentId"])
            all_data[cid] = {
                "ID": cid,
                "City": city_id,
                "Make": car.get("make"),
                "Model": car.get("model"),
                "Variant": car.get("variant"),
                "Year": car.get("year"),
                "KM Driven": car.get("odometer", {}).get("value"),
                "Ownership": car.get("ownership"),
                "Transmission": car.get("transmissionType", {}).get("value"),
                "Fuel": car.get("fuelType"),
                "BodyType": car.get("bodyType"),
                "Price (₹)": int(car.get("listingPrice", 0)),
                "Registration": car.get("maskedRegNum"),
                "Fetched On": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        # Extract cursor info from the last car
        last_car = cars[-1]
        last_score = last_car.get("score")
        last_id = str(last_car.get("appointmentId"))

        if not last_score or not last_id:
            break

        # For next request
        payload = {
            "searchFilter": [],
            "cityId": "4709",
            "sort": "bestmatch",
            "size": 20,
            "searchAfter": [last_score, last_id],
            "filterVersion": 2
        }

        page += 1
        time.sleep(0.5)

    return all_data

def compare_snapshots(new_data, old_data):
    new, changed = [], []
    for cid, car in new_data.items():
        if cid not in old_data:
            car["Change"] = "New"
            new.append(car)
        else:
            prev_price = int(old_data[cid].get("Price (₹)", 0))
            curr_price = int(car.get("Price (₹)", 0))
            if curr_price != prev_price:
                car["Previous Price (₹)"] = prev_price
                car["Change"] = "Price Changed"
                changed.append(car)
    return new, changed

def format_car_list(cars, change_type):
    lines = [f"{change_type} ({len(cars)}):"]
    for car in cars:
        name = car.get("Name", "Unknown")
        price = f"₹{car.get('Price (₹)', 0):,}"
        if change_type == "Price Drops" or car.get("Change") == "Price Changed":
            prev = f"↓ from ₹{car.get('Previous Price (₹)', 'NA'):,}"
            lines.append(f"• {name} - {price} {prev}")
        else:
            lines.append(f"• {name} - {price}")
    return "\n".join(lines)

def main():
    combined = []
    # loop over each city
    for c in CITIES:
        data = fetch_data_for_city(c["slug"], c["cityId"])
        for rec in data.values():
            rec["City"] = c["slug"]
            combined.append(rec)

    if not os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(combined, f, indent=2)
        df = pd.DataFrame(combined)
        df.to_excel(EXPORT_FILE, index=False)
        print(f"🆕 First run — exported full data to {EXPORT_FILE}")
        return

    with open(SNAPSHOT_FILE, "r") as f:
        previous = json.load(f)

    new, changed = compare_snapshots(combined, previous)

    if new or changed:
        df_all = pd.DataFrame(new + changed)
        df_all.to_excel(EXPORT_FILE, index=False)
        print(f"✅ Exported {len(df_all)} new/changed records to {EXPORT_FILE}")
    else:
        print("✅ No new or changed listings.")
        return

    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    if changed:
        msg = format_car_list(changed, "Price Drops")
        send_telegram_alert(f"📉 Cars24 Price Drop Alert\n\n{msg}")
    if new:
        msg = format_car_list(new, "New Listings")
        send_telegram_alert(f"🆕 New Cars24 Listings\n\n{msg}")

if __name__ == "__main__":
    main()
