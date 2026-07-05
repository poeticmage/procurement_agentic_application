import time
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from google.adk.tools import LongRunningFunctionTool


class PageContent(BaseModel):
    url: str
    clean_text: str


class GenericScraper:
    def __init__(self, wait_time: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
        self.wait_time = wait_time

    def fetch(self, url: str) -> tuple[str | None, dict | None]:
        time.sleep(self.wait_time)

        try:
            response = self.session.get(url, timeout=20, allow_redirects=True)
        except requests.RequestException as exc:
            return None, {
                "blocked": False,
                "status_code": None,
                "reason": "request_error",
                "error": str(exc),
                "url": url,
            }

        if response.status_code == 403:
            return None, {
                "blocked": True,
                "status_code": response.status_code,
                "reason": "forbidden",
                "error": "Vendor blocked automated scraping for this URL.",
                "url": response.url,
            }

        if response.status_code in {401, 429, 503}:
            return None, {
                "blocked": True,
                "status_code": response.status_code,
                "reason": "blocked_or_rate_limited",
                "error": "Vendor blocked or rate-limited automated scraping for this URL.",
                "url": response.url,
            }

        if response.status_code >= 400:
            return None, {
                "blocked": False,
                "status_code": response.status_code,
                "reason": "http_error",
                "error": f"HTTP error {response.status_code}",
                "url": response.url,
            }

        return response.text, None

    def clean_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        return " ".join(text.split())

    def scrape(self, url: str) -> PageContent | dict:
        html, error = self.fetch(url)
        if error:
            return error

        text = self.clean_text(html)
        return PageContent(url=url, clean_text=text)


_scraper = GenericScraper()


def _web_scraping_tool(page_url: str) -> dict:
    result = _scraper.scrape(page_url)
    if isinstance(result, dict):
        return result
    return {
        "url": result.url,
        "clean_text": result.clean_text,
        "blocked": False,
        "status_code": 200,
        "reason": "ok",
    }


web_scraping_tool = LongRunningFunctionTool(
    func=_web_scraping_tool
)