import requests
from bs4 import BeautifulSoup

## Tee time booking bot. should ideally work for any course that uses the teeitup.golf system

def fetchSiteInfo(baseUrl, date, courseIds, golfers):
    url = f"{baseUrl}/?course={courseIds}&date={date}&max=999999&golfers={golfers}"
    response = requests.get(url)

soup = BeautifulSoup(response.content, "html.parser")

print(soup)


if __name__ == "main":
    url = "https://fairfax-county-mco.book.teeitup.golf"
    date = "2025-08-31"
    courseIds = "7743,7756" # comma seperated list. twin lakes (lakes, oaks)
    golfers = "4"
