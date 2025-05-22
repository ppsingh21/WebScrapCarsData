import requests, pandas as pd, time, json, os, shutil
from datetime import datetime, timedelta

SNAPSHOT_FILE = "spinny_snapshot.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = f"Changes_{TODAY}.xlsx"
ARCHIVE_DIR = "archive"
BASE_URL = "https://api.spinny.com/v3/api/listing/v3/"

params = {
    "city": "bangalore",
    "product_type": "cars",
    "category": "used",
    "ratio_status": "available",
    "size": 40,
    "page": 1
}

def archive_old_excels(days_old=7):
    cutoff = datetime.now() - timedelta(days=days_old)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    for file in os.listdir():
        if file.startswith("Spinny_") and file.endswith(".xlsx"):
            try:
                file_date = datetime.strptime(file.replace("Spinny_", "").replace(".xlsx", ""), "%Y-%m-%d")
                if file_date < cutoff:
                    shutil.move(file, os.path.join(ARCHIVE_DIR, file))
            except Exception:
                continue
    shutil.make_archive(f"{ARCHIVE_DIR}/spinny_archive", 'zip', ARCHIVE_DIR)
    print("📦 Archived old files to archive/spinny_archive.zip")

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
                "Price (₹)": car.get("price", 0),
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
        elif car["Price (₹)"] != old_data[cid].get("Price (₹)"):
            car["Previous Price (₹)"] = old_data[cid].get("Price (₹)")
            car["Change"] = "Price Changed"
            changed.append(car)
    return new, changed

def format_car_list(cars, change_type):
    lines = [f"{change_type} ({len(cars)}):"]
    for car in cars[:10]:  # Limit to first 10 cars
        name = car.get("Name", "Unknown")
        price = f"₹{car.get('Price (₹)'):,}"
        if change_type == "Price Drops":
            prev = f"↓ from ₹{car.get('Previous Price (₹)', 'NA'):,}"
            lines.append(f"• {name} - {price} {prev}")
        else:
            lines.append(f"• {name} - {price}")
    if len(cars) > 10:
        lines.append(f"...and {len(cars) - 10} more.")
    return "\n".join(lines)

def main():
    current = fetch_data()

    if not os.path.exists(SNAPSHOT_FILE) or os.stat(SNAPSHOT_FILE).st_size == 0:
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
        df = pd.DataFrame(current.values())
        df.to_excel(f"Spinny_{TODAY}.xlsx", index=False)
        print(f"🆕 First run — exported full data to Spinny_{TODAY}.xlsx")
        return

    with open(SNAPSHOT_FILE, "r") as f:
        previous = json.load(f)

    new, changed = compare_snapshots(current, previous)

    if new or changed:
        with pd.ExcelWriter(EXPORT_FILE) as writer:
            if new:
                pd.DataFrame(new).to_excel(writer, sheet_name="New Listings", index=False)
            if changed:
                pd.DataFrame(changed).to_excel(writer, sheet_name="Price Changed", index=False)
        print(f"✅ Exported changes to {EXPORT_FILE}")
    else:
        print("✅ No new or changed listings.")
        return  # 🛑 Exit early — no file written

    # Update snapshot
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(current, f, indent=2)

    # Archive old files
    archive_old_excels()

    # Alerts
    if changed:
        msg = format_car_list(changed, "Price Drops")
        send_telegram_alert(f"📉 Spinny Price Drop Alert\n\n{msg}")
    if new:
        msg = format_car_list(new, "New Listings")
        send_telegram_alert(f"🆕 New Spinny Listings\n\n{msg}")

if __name__ == "__main__":
    main()
