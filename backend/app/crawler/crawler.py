import asyncio
from collections import deque
from urllib.parse import urlparse

import httpx

from app.crawler.models import CrawledPage
from app.crawler.parser import normalize_url, parse_page


class WebsiteCrawler:
    def __init__(
        self,
        start_url: str,
        max_pages: int = 100,
        request_delay: float = 0.25,
    ):
        self.start_url = normalize_url(start_url)

        parsed = urlparse(self.start_url)

        self.domain = parsed.netloc
        self.max_pages = max_pages
        self.request_delay = request_delay

        self.visited: set[str] = set()
        self.content_hashes: set[str] = set()

    async def crawl(self) -> list[CrawledPage]:
        queue = deque([self.start_url])
        pages: list[CrawledPage] = []

        headers = {
            "User-Agent": (
                "SystematicITSolutions-AISalesAgentDemo/1.0 "
                "(website knowledge crawler)"
            )
        }

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=20.0,
        ) as client:

            while queue and len(pages) < self.max_pages:
                url = queue.popleft()

                if url in self.visited:
                    continue

                self.visited.add(url)

                print(f"[CRAWL] {url}")

                try:
                    response = await client.get(url)

                except httpx.HTTPError as exc:
                    print(f"[ERROR] {url}: {exc}")
                    continue

                if response.status_code != 200:
                    print(
                        f"[SKIP {response.status_code}] {url}"
                    )
                    continue

                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()

                if "text/html" not in content_type:
                    continue

                page = parse_page(
                    html=response.text,
                    url=str(response.url),
                    allowed_domain=self.domain,
                    status_code=response.status_code,
                )

                # Ignore almost-empty pages
                if len(page.content) < 100:
                    continue

                # Prevent duplicate content
                if page.content_hash in self.content_hashes:
                    print(
                        f"[DUPLICATE] {page.canonical_url}"
                    )
                    continue

                self.content_hashes.add(page.content_hash)
                pages.append(page)

                for link in page.links:
                    if link not in self.visited:
                        queue.append(link)

                await asyncio.sleep(self.request_delay)

        return pages