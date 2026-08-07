import asyncio
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(BACKEND_DIR))


from app.crawler.crawler import WebsiteCrawler


WEBSITE_URL = "https://systematicitsolutions.com/"


async def main():
    crawler = WebsiteCrawler(
        start_url=WEBSITE_URL,
        max_pages=100,
        request_delay=0.25,
    )

    pages = await crawler.crawl()

    output_directory = PROJECT_ROOT / "data" / "raw"
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_directory / "website_pages.json"
    )

    data = [
        page.model_dump()
        for page in pages
    ]

    output_file.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("-----------------------------")
    print("CRAWL COMPLETE")
    print("-----------------------------")
    print(f"Pages saved: {len(pages)}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())