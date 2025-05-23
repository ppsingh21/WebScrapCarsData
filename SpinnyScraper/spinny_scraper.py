import requests, pandas as pd, time, json, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Telegram credentials
os.environ["TELEGRAM_TOKEN"] = "7698578725:AAFbPdl3eWNvotkNKt2vu6aTN3KTpsXRpQk"
os.environ["TELEGRAM_CHAT_ID"] = "6975035469"

TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = os.path.join(SCRIPT_DIR, f"Spinny_{TODAY}.xlsx")
SNAPSHOT_FILE = os.path.join(SCRIPT_DIR, "spinny_snapshot.json")
BASE_URL = "https://api.spinny.com/v3/api/listing/v3/"

params = {
    "city": "bangalore",
    "product_type": "cars",
    "category": "used",
    "ratio_status": "available",
    "size": 40,
    "page": 1
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
    all_data = {}
    while True:
        print(f"Fetching page {params['page']}...")
        res = requests.get(BASE_URL, params=params)
        if res.status_code != 200:
            print(f"❌ Error: {res.status_code}")
            break

        results = res.json().get("results", [])
        if not results:
            break

        for car in results:
            cid = str(car.get("id"))
            all_data[cid] = {
                "id": cid,
                "Name": f"{car.get('make')} {car.get('model')}",
                "Variant": car.get("variant", ""),
                "Fuel": car.get("fuel_type", ""),
                "Year": car.get("make_year", ""),
                "Color": car.get("color", ""),
                "Ownership": f"{car.get('no_of_owners')}st owner",
                "KMs Driven": f"{car.get('round_off_mileage_new')} km",
                "Price (₹)": int(car.get("price", 0)),
                "Registration": car.get("rto", ""),
                "Image": f"https:{car.get('images', [{}])[0].get('file', {}).get('absurl', '')}",
                "Fetched On": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        if not res.json().get("next"):
            break

        params["page"] += 1
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
            curr_price = int(car["Price (₹)"])
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

    if not os.path.exists(SNAPSHOT_FILE) or os.stat(SNAPSHOT_FILE).st_size == 0:
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
        df = pd.DataFrame(current.values())
        df.to_excel(EXPORT_FILE, index=False)  # ✅ Uses correct folder path
        print(f"🆕 First run — exported full data to Spinny_{TODAY}.xlsx")
        return

    with open(SNAPSHOT_FILE, "r") as f:
        previous = json.load(f)

    new, changed = compare_snapshots(current, previous)

    if new or changed:
        with pd.ExcelWriter(EXPORT_FILE) as writer:
            df_all = pd.DataFrame(new + changed)
            df_all.to_excel(writer, sheet_name="New & Changed Listings", index=False)
        print(f"✅ Exported changes to {EXPORT_FILE}")
    else:
        print("✅ No new or changed listings.")
        return

    # Save new snapshot
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(current, f, indent=2)

    # Telegram Alerts
    if changed:
        msg = format_car_list(changed, "Price Drops")
        send_telegram_alert(f"📉 Spinny Price Drop Alert\n\n{msg}")
    if new:
        msg = format_car_list(new, "New Listings")
        send_telegram_alert(f"🆕 New Spinny Listings\n\n{msg}")

if __name__ == "__main__":
    main()
