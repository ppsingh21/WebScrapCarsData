import requests, json, os, time
import pandas as pd
from datetime import datetime
import shutil

SNAPSHOT_FILE = "cars24_snapshot.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = f"Changes_{TODAY}.xlsx"

API_URL = "https://car-catalog-gateway-in.c24.tech/listing/v1/buy-used-cars-bangalore"
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/json'
}

def archive_old_excels(days_old=7):
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days_old)
    archive_dir = "archive"
    os.makedirs(archive_dir, exist_ok=True)

    for file in os.listdir():
        if file.startswith("Changes_") and file.endswith(".xlsx"):
            date_part = file.replace("Changes_", "").replace(".xlsx", "")
            try:
                file_date = datetime.strptime(date_part, "%Y-%m-%d")
                if file_date < cutoff:
                    shutil.move(file, os.path.join(archive_dir, file))
            except ValueError:
                continue

    # Zip archived files
    shutil.make_archive("archive/cars24_archive", 'zip', archive_dir)
    print("📦 Archived old files to archive/cars24_archive.zip")

def send_telegram_alert(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, json=payload)

def fetch_data():
    payload = {
        "searchFilter": [],
        "cityId": "4709",
        "sort": "bestmatch",
        "size": 1000,
        "filterVersion": 1
    }
    all_data = {}
    while True:
        res = requests.post(API_URL, headers=HEADERS, json=payload)
        cars = res.json().get("content", [])
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
                "Price (₹)": car.get("listingPrice"),
                "Registration": car.get("maskedRegNum"),
                "Image": car.get("listingImage", {}).get("uri", ""),
                "Fetched On": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        if not res.json().get("searchAfter"):
            break
        payload["searchAfter"] = res.json()["searchAfter"]
        time.sleep(0.5)
    return all_data

def compare_snapshots(new_data, old_data):
    new, changed = [], []
    for cid, car in new_data.items():
        if cid not in old_data:
            car["Change"] = "New"
            new.append(car)
        elif car["Price (₹)"] != old_data[cid]["Price (₹)"]:
            car["Previous Price (₹)"] = old_data[cid]["Price (₹)"]
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
    if not os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(current, f, indent=2)
        df = pd.DataFrame(current.values())
        df.to_excel(f"Cars24_{TODAY}.xlsx", index=False)
        return

    with open(SNAPSHOT_FILE, "r") as f:
        if os.stat(SNAPSHOT_FILE).st_size == 0:
            previous = {}
        else:
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

    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(current, f, indent=2)
    archive_old_excels()
    
    # Alerts
    if changed:
        msg = format_car_list(changed, "Price Drops")
        send_telegram_alert(f"📉 Cars24 Price Drop Alert\n\n{msg}")
    if new:
        msg = format_car_list(new, "New Listings")
        send_telegram_alert(f"🆕 New Cars24 Listings\n\n{msg}")
        
if __name__ == "__main__":
    main()
