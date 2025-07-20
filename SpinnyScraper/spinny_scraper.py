import requests, pandas as pd, time, json, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Use environment variables (set in GitHub Actions secrets)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TODAY = datetime.now().strftime("%Y-%m-%d")
EXPORT_FILE = os.path.join(SCRIPT_DIR, f"Spinny_{TODAY}.xlsx")
SNAPSHOT_FILE = os.path.join(SCRIPT_DIR, "spinny_snapshot.json")
BASE_URL = "https://api.spinny.com/v3/api/listing/v3/"

# list all the city slugs you want to scrape
CITIES = ["bangalore", "mumbai", "delhi-ncr", "kolkata", "hyderabad", "chennai"]

# base params that are common for every request
BASE_PARAMS = {
    "product_type": "cars",
    "category": "used",
    "ratio_status": "available",
    "size": 40,
    "page": 1
}

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

def fetch_data_for_city(city, fetch_time):
    """Fetch all pages for a single city and return dict[id] -> record."""
    params = BASE_PARAMS.copy()
    params["city"] = city
    all_data = {}
    while True:
        print(f"Fetching {city} page {params['page']}…")
        try:
            res = requests.get(BASE_URL, params=params, timeout=30)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"❌ Error fetching {city} page {params['page']}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for car in results:
            cid = str(car.get("id"))
            all_data[cid] = {
                "ID": cid,
                "City": city,
                "Name": f"{car.get('make', '')} {car.get('model', '')}",
                "Make": car.get("make"),
                "Model": car.get("model"),
                "Variant": car.get("variant", ""),
                "Year": car.get("make_year", ""),
                "KM Driven": car.get("round_off_mileage_new", 0),
                "Ownership": f"{car.get('no_of_owners', 0)}st owner",
                "Transmission": car.get("transmission", "").title(),
                "Fuel": car.get("fuel_type", "").title(),
                "BodyType": car.get("body_type", "").title(),
                "Price (₹)": int(car.get("price", 0)),
                "Registration": car.get("rto", ""),
                "Fetched On": fetch_time
            }

        if not data.get("next"):
            break

        params["page"] += 1
        time.sleep(0.5)
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
            if new_price < old_price:  # Only alert on price drops
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
            city_data = fetch_data_for_city(city, fetch_time)
            current_snapshot.update(city_data)
            print(f"✅ {city}: {len(city_data)} cars")
        except Exception as e:
            print(f"❌ Failed {city}: {e}")
            send_telegram_alert(f"🚨 SPINNY SCRAPER FAILURE\n\n{city.upper()} failed: {e}")

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
    send_telegram_alert(f"🚗 <b>SPINNY UPDATE - {TODAY}</b>\n\n{full_message}")

if __name__ == "__main__":
    main()