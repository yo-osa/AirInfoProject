from flask import Flask, render_template, request
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import os
import google.generativeai as genai
from scraper import scrape_skyscanner
import json
import matplotlib.pyplot as plt
from collections import Counter

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'YOUR_GEMINI_API_KEY')
genai.configure(api_key="AIzaSyDNvTFTbJqR5R0g7-Tr6RQHv0u8Bb3ZPQU")

AVIATIONSTACK_API_KEY = os.environ.get('AVIATIONSTACK_API_KEY', '')

def fetch_aviationstack_flights(origin, destination, date):
    # IATA codes
    url = (
        f"http://api.aviationstack.com/v1/flights?access_key={AVIATIONSTACK_API_KEY}"
        f"&dep_iata={origin}&arr_iata={destination}&flight_date={date}"
    )
    resp = requests.get(url)
    flights = []
    if resp.status_code == 200:
        data = resp.json()
        for f in data.get('data', [])[:10]: 
            flights.append({
                'airline': f.get('airline', {}).get('name', ''),
                'flight_number': f.get('flight', {}).get('iata', ''),
                'departure_time': f.get('departure', {}).get('scheduled', ''),
                'arrival_time': f.get('arrival', {}).get('scheduled', ''),
                'status': f.get('flight_status', ''),
            })
    return flights

def fetch_aviationstack_flights_by_airline(airline_code, api_key):
    url = (
        f"http://api.aviationstack.com/v1/flights?access_key={api_key}"
        f"&airline_iata={airline_code}"
    )
    resp = requests.get(url)
    flights = []
    if resp.status_code == 200:
        data = resp.json()
        for f in data.get('data', [])[:10]: 
            flights.append({
                'airline': f.get('airline', {}).get('name', ''),
                'flight_number': f.get('flight', {}).get('iata', ''),
                'departure_airport': f.get('departure', {}).get('airport', ''),
                'arrival_airport': f.get('arrival', {}).get('airport', ''),
                'departure_time': f.get('departure', {}).get('scheduled', ''),
                'arrival_time': f.get('arrival', {}).get('scheduled', ''),
                'status': f.get('flight_status', ''),
            })
    return flights

def plot_bar_chart(items, title, filename, xlabel):
    labels = []
    counts = []
    for item in items:
        if '(' in item and ')' in item:
            label, count = item.rsplit('(', 1)
            labels.append(label.strip())
            try:
                counts.append(int(count.strip(')')))
            except ValueError:
                continue
    if not labels or not counts:
        return None
    plt.figure(figsize=(8, 4))
    plt.barh(labels, counts, color='#2196f3')
    plt.xlabel(xlabel)
    plt.title(title)
    plt.tight_layout()
    plot_dir = 'static/plots'
    os.makedirs(plot_dir, exist_ok=True)
    plot_path = f'{plot_dir}/{filename}'
    plt.savefig(plot_path)
    plt.close()
    return plot_path

@app.route('/', methods=['GET'])
def index():
    origin = request.args.get('origin', '')
    destination = request.args.get('destination', '')
    date = request.args.get('date', '')
    insights = None
    high_demand_labels = []
    high_demand_counts = []
    if origin and date:
        #00:00 to 23:59 UTC
        dt = datetime.strptime(date, '%Y-%m-%d')
        begin = int(time.mktime(dt.timetuple()))
        end = int(time.mktime((dt + timedelta(days=1)).timetuple()))
        # Fetching departures and arrivals for the airport
        departures_url = f'https://opensky-network.org/api/flights/departure?airport={origin}&begin={begin}&end={end}'
        arrivals_url = f'https://opensky-network.org/api/flights/arrival?airport={origin}&begin={begin}&end={end}'
        try:
            dep_resp = requests.get(departures_url, timeout=20)
            arr_resp = requests.get(arrivals_url, timeout=20)
            dep_data = dep_resp.json() if dep_resp.status_code == 200 else []
            arr_data = arr_resp.json() if arr_resp.status_code == 200 else []
            # Combine and filter by destination if provided
            flights = dep_data + arr_data
            if destination:
                flights = [f for f in flights if f.get('estArrivalAirport') == destination or f.get('estDepartureAirport') == destination]
            df = pd.DataFrame(flights)
            # Insights: popular routes, high demand periods, total flights
            if not df.empty:
                df['route'] = df['estDepartureAirport'].fillna('UNK') + '-' + df['estArrivalAirport'].fillna('UNK')
                popular_routes = df['route'].value_counts().head(5).items()
                # High demand periods (by hour)
                df['hour'] = df['firstSeen'].apply(lambda x: datetime.utcfromtimestamp(x).strftime('%H:00') if pd.notnull(x) else 'UNK')
                high_demand_periods = list(df['hour'].value_counts().head(5).items())
                total_flights = len(df)
                high_demand_labels = [p[0] for p in high_demand_periods]
                high_demand_counts = [p[1] for p in high_demand_periods]
                insights = {
                    'popular_routes': list(popular_routes),
                    'high_demand_periods': high_demand_periods,
                    'total_flights': total_flights
                }
        except Exception as e:
            insights = {'error': f'Error fetching data: {e}'}
    return render_template('index.html', insights=insights, origin=origin, destination=destination, date=date, high_demand_labels=high_demand_labels, high_demand_counts=high_demand_counts)

@app.route('/scrape', methods=['POST'])
def scrape():
    airline = request.form.get('airline', '').upper()
    api_key = request.form.get('aviationstack_api_key', '').strip() or AVIATIONSTACK_API_KEY
    time_range = request.form.get('time_range', 'any')
    status_filter = request.form.get('status', 'any')
    if not api_key:
        error = 'AviationStack API key is required.'
        return render_template('index.html', error=error)
    flights = fetch_aviationstack_flights_by_airline(airline, api_key)
    # Filter by status
    if status_filter == 'scheduled':
        flights = [f for f in flights if f.get('status', '').lower() == 'scheduled']
    # Filter by time range
    def in_time_range(dt_str, rng):
        if not dt_str:
            return False
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            hour = dt.hour
            if rng == 'morning':
                return 5 <= hour < 12
            elif rng == 'afternoon':
                return 12 <= hour < 17
            elif rng == 'evening':
                return 17 <= hour < 23
            elif rng == 'night':
                return hour < 5 or hour >= 23
            else:
                return True
        except Exception:
            return False
    if time_range != 'any':
        flights = [f for f in flights if in_time_range(f.get('departure_time', ''), time_range)]
    # Prepare concise data for Gemini
    flight_lines = [
        f"{f['airline']} | {f['flight_number']} | {f['departure_airport']} -> {f['arrival_airport']} | {f['departure_time']} - {f['arrival_time']} | {f['status']}"
        for f in flights
    ]
    flights_summary = '\n'.join(flight_lines)
    ai_insights = ""
    if flights:
        try:
            prompt = f"""
            Given the following flight booking data for airline {airline}:
            {flights_summary}

            Extract and summarize:
            - Demand trends (e.g., busy times, days, or locations)
            - Pricing changes (if price data is available)
            - Popular routes (most frequent origin-destination pairs)

            Return the insights as clear bullet points under each section header:
            Demand Trends:
            - ...
            Pricing Changes:
            - ...
            Popular Routes:
            - ...
            """
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            ai_insights = response.text
        except Exception as e:
            ai_insights = f"Gemini API error: {e}"

    # --- Matplotlib Visualizations ---
    plot_routes = None
    plot_demand = None
    plot_pie = None
    if flights:
        # Popular routes (from -> to)
        route_counts = Counter(f"{f['departure_airport']} → {f['arrival_airport']}" for f in flights if f.get('departure_airport') and f.get('arrival_airport'))
        if route_counts:
            labels, counts = zip(*route_counts.most_common(5))
            plt.figure(figsize=(7, 3.5))
            plt.barh(labels, counts, color='#1976d2')
            plt.xlabel('Number of Flights')
            plt.title('Popular Routes')
            plt.tight_layout()
            plot_dir = 'static/plots'
            os.makedirs(plot_dir, exist_ok=True)
            plot_routes = f'{plot_dir}/routes_{airline}.png'
            plt.savefig(plot_routes)
            plt.close()
            plot_routes = plot_routes.replace('static/', '')
        # Most common departure airports
        dep_counts = Counter(f["departure_airport"] for f in flights if f.get("departure_airport"))
        if dep_counts:
            labels, counts = zip(*dep_counts.most_common(5))
            plt.figure(figsize=(7, 3.5))
            plt.barh(labels, counts, color='#388e3c')
            plt.xlabel('Number of Departures')
            plt.title('Top Departure Airports')
            plt.tight_layout()
            plot_dir = 'static/plots'
            os.makedirs(plot_dir, exist_ok=True)
            plot_demand = f'{plot_dir}/demand_{airline}.png'
            plt.savefig(plot_demand)
            plt.close()
            plot_demand = plot_demand.replace('static/', '')
        # Pie chart for flights and their frequency (by route)
        if route_counts:
            labels, counts = zip(*route_counts.most_common(5))
            plt.figure(figsize=(5, 5))
            plt.pie(counts, labels=labels, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
            plt.title('Flight Frequency by Route')
            plt.tight_layout()
            plot_dir = 'static/plots'
            os.makedirs(plot_dir, exist_ok=True)
            plot_pie = f'{plot_dir}/pie_{airline}.png'
            plt.savefig(plot_pie)
            plt.close()
            plot_pie = plot_pie.replace('static/', '')
    return render_template('scrape_results.html', flights=flights, ai_insights=ai_insights, airline=airline, plot_routes=plot_routes, plot_demand=plot_demand, plot_pie=plot_pie)

if __name__ == '__main__':
    app.run(debug=True) 