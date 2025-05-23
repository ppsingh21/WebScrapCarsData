import requests, json, os, time
import pandas as pd
from datetime import datetime

# Telegram credentials
os.environ["TELEGRAM_TOKEN"] = "7698578725:AAFbPdl3eWNvotkNKt2vu6aTN3KTpsXRpQk"
os.environ["TELEGRAM_CHAT_ID"] = "6975035469"

SNAPSHOT_FILE = "cars24_snapshot.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = f"Cars24_{TODAY}.xlsx"

API_URL = "https://car-catalog-gateway-in.c24.tech/listing/v1/buy-used-cars-bangalore"
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/json'
}

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

def fetch_data():
    payload = {
        "searchFilter": [],
        "cityId": "4709",
        "sort": "bestmatch",
        "size": 20,
        "filterVersion": 2
    }

    all_data = {}
    page = 1

    while True:
        print(f"Fetching Cars24 page {page}...")
        res = requests.post(API_URL, headers=HEADERS, json=payload)
        if res.status_code != 200:
            print(f"❌ Error: {res.status_code}")
            break

        cars = res.json().get("content", [])
        if not cars:
            break

        for car in cars:
            cid = str(car["appointmentId"])
            all_data[cid] = {
                "id": cid,
                "Name": car.get("carName"),
                "Variant": car.get("variant"),
                "Fuel": car.get("fuelType"),
                "Year": car.get("year"),
                "Color": car.get("color"),
                "Ownership": f"{car.get('ownership')}st owner",
                "KMs Driven": car.get("odometer", {}).get("display", ""),
                "Price (₹)": int(car.get("listingPrice", 0)),
                "Registration": car.get("maskedRegNum"),
                "Image": car.get("listingImage", {}).get("uri", ""),
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
    current = fetch_data()

    if not os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
        df = pd.DataFrame(current.values())
        df.to_excel(EXPORT_FILE, index=False)
        print(f"🆕 First run — exported full data to {EXPORT_FILE}")
        return

    with open(SNAPSHOT_FILE, "r") as f:
        previous = json.load(f)

    new, changed = compare_snapshots(current, previous)

    if new or changed:
        df_all = pd.DataFrame(new + changed)
        df_all.to_excel(EXPORT_FILE, index=False)
        print(f"✅ Exported {len(df_all)} new/changed records to {EXPORT_FILE}")
    else:
        print("✅ No new or changed listings.")
        return

    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(current, f, indent=2)

    if changed:
        msg = format_car_list(changed, "Price Drops")
        send_telegram_alert(f"📉 Cars24 Price Drop Alert\n\n{msg}")
    if new:
        msg = format_car_list(new, "New Listings")
        send_telegram_alert(f"🆕 New Cars24 Listings\n\n{msg}")

if __name__ == "__main__":
    main()
