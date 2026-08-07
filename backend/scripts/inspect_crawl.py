import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "website_pages.json"


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Crawl file not found: {INPUT_FILE}"
        )

    pages = json.loads(
        INPUT_FILE.read_text(encoding="utf-8")
    )

    print()
    print("=" * 80)
    print("CRAWL INSPECTION")
    print("=" * 80)
    print(f"Total pages: {len(pages)}")
    print()

    for index, page in enumerate(pages, start=1):
        content = page.get("content", "")
        title = page.get("title", "")
        url = page.get("canonical_url") or page.get("url")

        print(f"[{index}] {title}")
        print(f"URL: {url}")
        print(f"Characters: {len(content)}")
        print(
            "Preview:",
            content[:250].replace("\n", " "),
        )
        print("-" * 80)


if __name__ == "__main__":
    main()