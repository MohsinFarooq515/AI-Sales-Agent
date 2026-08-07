import hashlib
import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.crawler.models import CrawledPage


def normalize_url(url: str) -> str:
    parsed = urlparse(url)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            "",
            parsed.query,
            "",
        )
    )


def is_internal_url(url: str, allowed_domain: str) -> bool:
    parsed = urlparse(url)

    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower().replace("www.", "")
        == allowed_domain.lower().replace("www.", "")
    )


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_boilerplate(soup: BeautifulSoup) -> None:
    """
    Remove common site-wide elements that should not enter the RAG KB.
    """

    # Semantic HTML
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "iframe",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
        ]
    ):
        tag.decompose()

    # Common WordPress / Elementor / navigation selectors
    selectors = [
        ".elementor-location-header",
        ".elementor-location-footer",
        ".site-header",
        ".site-footer",
        ".main-header",
        ".main-footer",
        ".main-navigation",
        ".navigation",
        ".navbar",
        ".nav-menu",
        ".menu",
        ".mobile-menu",
        ".header",
        ".footer",
        "#header",
        "#footer",
        "#masthead",
        "#site-header",
        "#site-footer",
        "[role='navigation']",
        "[role='banner']",
        "[role='contentinfo']",
    ]

    for selector in selectors:
        for element in soup.select(selector):
            element.decompose()


def extract_main_content(soup: BeautifulSoup):
    """
    Try increasingly broad containers.
    """

    selectors = [
        "main",
        "article",
        "#content",
        "#main",
        ".site-main",
        ".main-content",
        ".page-content",
        ".entry-content",
        ".content-area",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element:
            text = clean_text(
                element.get_text(separator=" ", strip=True)
            )

            if len(text) >= 200:
                return element

    return soup.body or soup


def parse_page(
    html: str,
    url: str,
    allowed_domain: str,
    status_code: int,
) -> CrawledPage:
    soup = BeautifulSoup(html, "lxml")

    # -------------------------------------------------
    # Discover links before removing navigation
    # -------------------------------------------------

    links: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()

        if not href:
            continue

        # Ignore non-page actions
        if href.startswith(
            (
                "mailto:",
                "tel:",
                "javascript:",
                "whatsapp:",
                "#",
            )
        ):
            continue

        absolute_url = normalize_url(
            urljoin(url, href)
        )

        if is_internal_url(
            absolute_url,
            allowed_domain,
        ):
            links.add(absolute_url)

    # -------------------------------------------------
    # Metadata
    # -------------------------------------------------

    title = ""

    if soup.title and soup.title.string:
        title = clean_text(soup.title.string)

    meta_description = ""

    description_tag = soup.find(
        "meta",
        attrs={
            "name": re.compile(
                "^description$",
                re.I,
            )
        },
    )

    if description_tag:
        meta_description = clean_text(
            description_tag.get(
                "content",
                ""
            )
        )

    canonical_url = normalize_url(url)

    canonical_tag = soup.find(
        "link",
        attrs={
            "rel": lambda value:
                value and "canonical" in value
        },
    )

    if (
        canonical_tag
        and canonical_tag.get("href")
    ):
        candidate = normalize_url(
            urljoin(
                url,
                canonical_tag["href"],
            )
        )

        if is_internal_url(
            candidate,
            allowed_domain,
        ):
            canonical_url = candidate

    # -------------------------------------------------
    # Remove boilerplate
    # -------------------------------------------------

    remove_boilerplate(soup)

    # -------------------------------------------------
    # Extract real page content
    # -------------------------------------------------

    main_content = extract_main_content(soup)

    content = clean_text(
        main_content.get_text(
            separator=" ",
            strip=True,
        )
    )

    # Remove common accessibility residue
    content = re.sub(
        r"^Skip to content\s*",
        "",
        content,
        flags=re.I,
    )

    content = clean_text(content)

    content_hash = hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    return CrawledPage(
        url=normalize_url(url),
        canonical_url=canonical_url,
        title=title,
        meta_description=meta_description,
        content=content,
        content_hash=content_hash,
        links=sorted(links),
        status_code=status_code,
    )