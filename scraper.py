from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def scrape_skyscanner(origin, destination, date):
    # Skyscanner expects date in YYMMDD format
    date_fmt = date.replace('-', '')[2:]
    url = f"https://www.skyscanner.com/transport/flights/{origin.lower()}/{destination.lower()}/{date_fmt}/"
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        # Wait for flight cards to load (up to 20 seconds)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.DayViewItinerary'))
        )
        flights = []
        cards = driver.find_elements(By.CSS_SELECTOR, 'div.DayViewItinerary')
        for card in cards[:10]:  # Limit to first 10 flights
            try:
                airline = card.find_element(By.CSS_SELECTOR, 'span.LegInfo__carrier').text
            except:
                airline = ''
            try:
                dep_time = card.find_element(By.CSS_SELECTOR, 'span.LegInfo__times__departure').text
            except:
                dep_time = ''
            try:
                arr_time = card.find_element(By.CSS_SELECTOR, 'span.LegInfo__times__arrival').text
            except:
                arr_time = ''
            try:
                price = card.find_element(By.CSS_SELECTOR, 'span.Price_mainPriceContainer__1dqsw').text
            except:
                price = ''
            flights.append({
                'airline': airline,
                'departure_time': dep_time,
                'arrival_time': arr_time,
                'price': price
            })
        return flights
    finally:
        driver.quit() 