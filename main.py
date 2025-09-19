import argparse
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

def load_city_codes(filename="cities.csv"):
    codes = {}
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            codes[row["City_alias"]] = row
    return codes

def build_url(from_city, to_city, date, codes):
    from_row = codes[from_city]
    to_row = codes[to_city]

    return (
        "https://pass.rw.by/ru/route/"
        f"?from={from_row['City']}"
        f"&from_exp={from_row['exp_code']}"
        f"&from_esr={from_row['esr_code']}"
        f"&to={to_row['City']}"
        f"&to_exp={to_row['exp_code']}"
        f"&to_esr={to_row['esr_code']}"
        f"&front_date={date.strftime('%d+%b+%Y')}"
        f"&date={date.strftime('%Y-%m-%d')}"
    )

def parse_trains(html, filter_type=None, filter_selling=None):
    soup = BeautifulSoup(html, "html.parser")
    trains = []
    for row in soup.select(".sch-table__row"):
        train_type = row.get("data-train-type")
        selling = row.get("data-ticket_selling_allowed")

        if filter_type and train_type != filter_type:
            continue
        if filter_selling is not None and selling != filter_selling:
            continue

        number = row.get("data-train-number")
        dep_time = row.select_one(".train-from-time").text.strip()
        arr_time = row.select_one(".train-to-time").text.strip()
        dep_station = row.select_one(".train-from-name").text.strip()
        arr_station = row.select_one(".train-to-name").text.strip()

        tickets = []
        for t in row.select(".sch-table__t-item.has-quant"):
            t_name = t.select_one(".sch-table__t-name").text.strip()
            t_name = t_name if t_name else "Неизвестный тип"
            qty = t.select_one("a span").text.strip()

            # Collect all costs in this ticket type
            costs = [c.text.strip() for c in t.select(".ticket-cost")]
            currencies = [c.text.strip() for c in t.select(".ticket-currency")]

            # Join multiple prices with "/"
            if costs:
                price_str = "/".join(costs)
                if currencies:
                    # take unique currencies and join
                    uniq_cur = "/".join(sorted(set(currencies)))
                    price_str = f"{price_str} {uniq_cur}"
            else:
                price_str = "—"

            tickets.append({
                "type": t_name,
                "seats": qty,
                "price": price_str
            })


        trains.append({
            "number": number,
            "train_type": train_type,
            "selling": selling,
            "dep_time": dep_time,
            "arr_time": arr_time,
            "departure": f"{dep_time} {dep_station}",
            "arrival": f"{arr_time} {arr_station}",
            "tickets": tickets
        })
    return trains

def list_train_types(html):
    soup = BeautifulSoup(html, "html.parser")
    types = {row.get("data-train-type") for row in soup.select(".sch-table__row")}
    types = {t for t in types if t}  # drop None
    return sorted(types)


def train_icon(train_type: str) -> str:
    icons = {
        "international": "🌍",
        "regional_business": "💼",
        "interregional_economy": "🚆",
        "interregional_business": "🚄",
        "regional_economy": "🚌",
    }
    return icons.get(train_type, "❓")

def time_to_category(dep_time: str) -> str:
    """Return Ночь, Утро, День, Вечер by departure time"""
    dt = datetime.strptime(dep_time, "%H:%M")
    h = dt.hour
    if 0 <= h < 6:
        return "Ночь"
    elif 6 <= h < 12:
        return "Утро"
    elif 12 <= h < 18:
        return "День"
    else:
        return "Вечер"

def print_trains_grouped(trains):
    grouped = {"Ночь": [], "Утро": [], "День": [], "Вечер": []}
    for t in trains:
        cat = time_to_category(t["dep_time"])
        grouped[cat].append(t)

    for section, items in grouped.items():
        if not items:
            continue
        print(f"\n=== {section} ===")
        for t in items:
            # Header color
            if t["train_type"] in ("international", "regional_business"):
                header_color = Fore.BLUE + Style.BRIGHT
            else:
                header_color = Style.RESET_ALL

            icon = train_icon(t["train_type"])
            header = (
                f"{icon} Поезд {t['number']} "
                f"{t['departure']} → {t['arrival']}"
            )
            if t["selling"] == "false":
                header += " ❌"
            print(f"{header_color}{header}{Style.RESET_ALL}")

            for ticket in t["tickets"]:
                if ticket["type"] == "Сидячий":
                    ticket_color = Fore.GREEN + Style.BRIGHT
                else:
                    ticket_color = Style.RESET_ALL

                print(
                    f"  {ticket_color}{ticket['type']}: "
                    f"{ticket['seats']} мест, {ticket['price']}{Style.RESET_ALL}"
                )

def main():
    parser = argparse.ArgumentParser(description="RW.BY train seat checker")
    parser.add_argument("--from", dest="from_city", required=True, help="From city alias (see cities.csv)")
    parser.add_argument("--to", dest="to_city", required=True, help="To city alias (see cities.csv)")
    parser.add_argument("--date", required=True, help="Travel date in YYYY-MM-DD")
    parser.add_argument("--type", dest="train_type", help="Filter by train type (e.g. international, interregional_economy)")
    parser.add_argument("--selling", choices=["true", "false"], help="Filter by ticket selling allowed")
    parser.add_argument("--list-types", action="store_true", help="List available train types in response and exit")
    args = parser.parse_args()

    codes = load_city_codes()
    date = datetime.strptime(args.date, "%Y-%m-%d")
    url = build_url(args.from_city, args.to_city, date, codes)

    resp = requests.get(url)
    resp.raise_for_status()

    if args.list_types:
        types = list_train_types(resp.text)
        print("Train types found in response:")
        for t in types:
            print("  -", t)
        return

    trains = parse_trains(resp.text, filter_type=args.train_type, filter_selling=args.selling)
    if not trains:
        print("Нет поездов с указанным фильтром.")
        return

    print_trains_grouped(trains)

if __name__ == "__main__":
    main()
