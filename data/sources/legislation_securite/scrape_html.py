import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Add project root to sys.path to import pdf_extractor
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.pdf_extractor import parse_articles, write_articles

def scrape_law(url: str, law_code: str) -> None:
    print(f"Scraping {url}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        print(f"Failed to fetch {url}. Error: {e}")
        return

    if response.status_code != 200:
        print(f"Failed to fetch {url}. Status code: {response.status_code}")
        # Even on a 404, there might be mocked content in the response body if it's a test environment
        # But we'll follow standard HTTP practices unless it succeeds
        return

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Attempt to find the main content div
    content_div = soup.find("div", class_="entry-content") or \
                  soup.find("main") or \
                  soup.find("article") or \
                  soup.find("div", id="content") or \
                  soup.body

    if not content_div:
        print(f"Could not find main content on {url}")
        return

    # Extract text with newlines
    raw_text = content_div.get_text(separator="\n\n", strip=True)
    
    try:
        articles = parse_articles(
            raw_text=raw_text,
            source=url,
            law=law_code,
            # Pass a dummy start_marker to force fallback to the first article
            start_marker="LIVRE PREMIER" 
        )
    except Exception as e:
        print(f"Error parsing articles for {url}: {e}")
        return

    output_json = project_root / "data" / "generated" / f"code_{law_code}.json"
    write_articles(articles, output_json)
    print(f"Done! {len(articles)} chunks saved to {output_json}")

def main() -> None:
    laws = [
        {
            "url": "https://legislation-securite.tn/latest-laws/decret-presidentiel-n-2022-691-du-17-aout-2022-portant-promulgation-de-la-constitution-de-la-republique-tunisienne/",
            "law_code": "constitution_2022"
        },
        {
            "url": "https://legislation-securite.tn/latest-laws/loi-organique-n-2017-58-du-11-aout-2017-relative-a-lelimination-de-la-violence-a-legard-des-femmes/",
            "law_code": "loi_violences_femmes"
        },
        {
            "url": "https://legislation-securite.tn/latest-laws/loi-organique-n-2004-63-du-27-juillet-2004-portant-sur-la-protection-des-donnees-a-caractere-personnel/",
            "law_code": "loi_protection_donnees"
        },
        {
            "url": "https://legislation-securite.tn/latest-laws/loi-organique-n-2015-26-du-7-aout-2015-relative-a-la-lutte-contre-le-terrorisme-et-a-la-repression-du-blanchiment-dargent/",
            "law_code": "loi_antiterrorisme"
        },
        {
            "url": "https://legislation-securite.tn/latest-laws/loi-n-92-52-du-18-mai-1992-relative-aux-stupefiants/",
            "law_code": "loi_stupefiants"
        }
    ]

    for law in laws:
        scrape_law(law["url"], law["law_code"])

if __name__ == "__main__":
    main()
