import requests, json, os, time
import pandas as pd
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Use environment variables (set in GitHub Actions secrets)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = os.path.join(SCRIPT_DIR, f"Cars24_{TODAY}.xlsx")
SNAPSHOT_FILE = os.path.join(SCRIPT_DIR, "cars24_snapshot.json")

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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing")
        return
    for chat_id in TELEGRAM_CHAT_ID.split(","):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id.strip(),
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"❌ Telegram send failed: {e}")

def fetch_data_for_city(slug, city_id, fetch_time):
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
        try:
            res = requests.post(api_url, headers=HEADERS, json=payload, timeout=30)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"❌ Error fetching page: {e}")
            break

        cars = data.get("content", [])
        if not cars:
            break

        for car in cars:
            cid = str(car["appointmentId"])
            all_data[cid] = {
                "ID": cid,
                "City": slug,
                "Name": car.get("carName", "Unknown"),
                "Make": car.get("make"),
                "Model": car.get("model"),
                "Variant": car.get("variant"),
                "Year": car.get("year"),
                "KMs Driven": car.get("odometer", {}).get("display", ""),
                "Ownership": f"{car.get('ownership', '')}st owner" if car.get('ownership') else "",
                "Transmission": car.get("transmissionType", {}).get("value", ""),
                "Fuel": car.get("fuelType", ""),
                "BodyType": car.get("bodyType", ""),
                "Price (₹)": int(car.get("listingPrice", 0)),
                "Registration": car.get("maskedRegNum", ""),
                "Image": car.get("listingImage", {}).get("uri", ""),
                "Fetched On": fetch_time
            }

        # Pagination handling
        last_car = cars[-1]
        last_score = last_car.get("score")
        last_id = str(last_car.get("appointmentId"))

        if not last_score or not last_id:
            break

        payload = {
            "searchFilter": [],
            "cityId": city_id,
            "sort": "bestmatch",
            "size": 20,
            "searchAfter": [last_score, last_id],
            "filterVersion": 2
        }

        page += 1
        time.sleep(0.5)  # Be polite to the API

    return all_data

def compare_snapshots(new_data, old_data):
    new_listings = []
    price_drops = []
    
    for cid, new_car in new_data.items():
        if cid not in old_data:
            new_listings.append(new_car)
        else:
            old_price = old_data[cid].get("Price (₹)", 0)
            new_price = new_car.get("Price (₹)", 0)
            if new_price != old_price:  # Only alert on price drops
                price_drops.append({
                    **new_car,
                    "Previous Price (₹)": old_price
                })
    return new_listings, price_drops

def format_car_list(cars, list_type):
    if not cars:
        return ""
        
    message = f"<b>{list_type} ({len(cars)}):</b>\n\n"
    for car in cars:
        name = car.get("Name", "Unknown")
        price = f"₹{car.get('Price (₹)', 0):,}"
        city = car.get("City", "Unknown")
        
        if list_type == "Price Drops":
            old_price = f"₹{car.get('Previous Price (₹)', 0):,}"
            message += f"• {city.upper()}: {name}\n"
            message += f"  🔻 {old_price} → {price} ({round((car['Previous Price (₹)'] - car['Price (₹)'])/car['Previous Price (₹)']*100)}%)\n\n"
        else:
            message += f"• {city.upper()}: {name}\n"
            message += f"  💰 {price}\n\n"
            
    return message

def load_existing_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
        
    try:
        with open(SNAPSHOT_FILE, "r") as f:
            data = json.load(f)
            # Convert to dict if loaded as list (legacy format)
            return {item['ID']: item for item in data} if isinstance(data, list) else data
    except Exception as e:
        print(f"Error loading snapshot: {e}")
        return {}

def main():
    fetch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_snapshot = {}
    
    # Fetch data for all cities
    for city in CITIES:
        try:
            city_data = fetch_data_for_city(city["slug"], city["cityId"], fetch_time)
            current_snapshot.update(city_data)
            print(f"✅ {city['slug']}: {len(city_data)} cars")
        except Exception as e:
            print(f"❌ Failed {city['slug']}: {e}")
            send_telegram_alert(f"🚨 CARS24 SCRAPER FAILURE\n\n{city['slug'].upper()} failed: {e}")

    # Load previous snapshot
    old_snapshot = load_existing_snapshot()
    
    # Export current data to Excel
    df = pd.DataFrame(list(current_snapshot.values()))
    df.to_excel(EXPORT_FILE, index=False)
    print(f"📊 Exported {len(df)} records to {EXPORT_FILE}")

    # Find changes
    new_listings, price_drops = compare_snapshots(current_snapshot, old_snapshot)
    
    # Save new snapshot
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(current_snapshot, f, indent=2)

    # Send alerts if changes found
    if not new_listings and not price_drops:
        print("✅ No changes detected")
        return

    alerts = []
    if new_listings:
        alerts.append(format_car_list(new_listings, "New Listings"))
    if price_drops:
        alerts.append(format_car_list(price_drops, "Price Drops"))
    
    full_message = "\n".join(alerts)
    send_telegram_alert(f"🚗 <b>CARS24 UPDATE - {TODAY}</b>\n\n{full_message}")

if __name__ == "__main__":
    main()