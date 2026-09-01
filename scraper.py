"""
scraper.py

The scraping engine for BizLeadBot.

Responsibilities:
- Validate URLs (including basic SSRF protection against private/internal IPs).
- Fetch public HTML pages with sane timeouts and headers.
- Extract useful links, titles, and text snippets.
- Normalize and de-duplicate results.
- Follow simple "next page" pagination links, up to a page limit.
- Respect maximum page / result limits.

This module deliberately does NOT attempt to:
- bypass CAPTCHAs, logins, paywalls, or anti-bot protection
- access non-public / internal network addresses
- scrape anything requiring authentication

It only processes publicly reachable HTML that a normal browser could load.
"""

import csv
import ipaddress
import os
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

USER_AGENT = "BizLeadBotScraper/1.0 (+https://github.com/) respectful-scraper"

# Common "next page" link text/rel patterns used for simple pagination.
_NEXT_PAGE_HINTS = ("next", "older", "»", "next page", "load more")


class ScraperError(Exception):
    """Raised for any user-facing scraping failure (invalid URL, network error, etc.)."""


@dataclass
class Lead:
    title: str
    url: str
    snippet: str


@dataclass
class ScrapeResult:
    leads: List[Lead] = field(default_factory=list)
    pages_scanned: int = 0


# --- URL validation / SSRF protection -----------------------------------------

def _is_private_host(hostname: str) -> bool:
    """
    Resolve the hostname and check whether it points at a private, loopback,
    link-local, or otherwise internal address. Blocks common SSRF vectors
    like localhost, 127.0.0.1, 169.254.x.x (cloud metadata), 10.x, 192.168.x, etc.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # DNS failure will be surfaced later as a fetch error; treat as unsafe here.
        return True

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def validate_url(url: str) -> str:
    """
    Validate a user-supplied URL. Returns the normalized URL if valid,
    otherwise raises ScraperError with a user-friendly message.
    """
    url = url.strip()
    if not url:
        raise ScraperError("الرابط فارغ. أرسل رابط صفحة ويب عامة صالح.")

    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ScraperError("البروتوكول غير مدعوم. استخدم رابط http أو https فقط.")

    if not parsed.hostname:
        raise ScraperError("الرابط غير صالح. تأكد من كتابته بشكل صحيح.")

    if parsed.hostname.lower() in ("localhost",):
        raise ScraperError("لا يمكن الوصول إلى عناوين داخلية أو محلية.")

    if _is_private_host(parsed.hostname):
        raise ScraperError("لا يمكن الوصول إلى عناوين شبكة داخلية/خاصة لأسباب أمنية.")

    return url


# --- Fetching -------------------------------------------------------------------

def _fetch(url: str) -> requests.Response:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=config.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        raise ScraperError("انتهت مهلة الاتصال بالموقع. حاول مرة أخرى لاحقاً.")
    except requests.exceptions.ConnectionError:
        raise ScraperError("تعذر الاتصال بالموقع. تأكد من صحة الرابط.")
    except requests.exceptions.RequestException:
        raise ScraperError("حدث خطأ أثناء محاولة الوصول إلى الموقع.")

    # Re-validate the final URL after redirects, to prevent redirect-based SSRF.
    final_host = urlparse(response.url).hostname
    if final_host and _is_private_host(final_host):
        raise ScraperError("تم رفض إعادة التوجيه إلى عنوان شبكة داخلية.")

    if response.status_code == 403:
        raise ScraperError("الموقع رفض الوصول (403). قد يكون محمياً ضد الزحف الآلي.")
    if response.status_code == 404:
        raise ScraperError("الصفحة غير موجودة (404).")
    if response.status_code == 429:
        raise ScraperError("عدد كبير جداً من الطلبات (429). حاول لاحقاً.")
    if 500 <= response.status_code < 600:
        raise ScraperError(f"خطأ في خادم الموقع ({response.status_code}).")
    if not response.ok:
        raise ScraperError(f"طلب غير ناجح (رمز الحالة {response.status_code}).")

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ScraperError("المحتوى ليس صفحة HTML قابلة للاستخراج.")

    return response


# --- Extraction -----------------------------------------------------------------

def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_leads(html: str, base_url: str) -> List[Lead]:
    soup = BeautifulSoup(html, "html.parser")
    leads = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https"):
            continue

        title = _normalize_text(a_tag.get_text()) or "(بدون عنوان)"

        # Try to build a short snippet from surrounding text (parent element).
        parent_text = ""
        if a_tag.parent:
            parent_text = _normalize_text(a_tag.parent.get_text())
        snippet = parent_text[:200] if parent_text else title[:200]

        leads.append(Lead(title=title, url=absolute_url, snippet=snippet))

    return leads


def _find_next_page_url(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")

    # Prefer semantic <link rel="next">
    link_tag = soup.find("link", rel="next")
    if link_tag and link_tag.get("href"):
        return urljoin(base_url, link_tag["href"])

    # Fall back to anchor text hints.
    for a_tag in soup.find_all("a", href=True):
        text = _normalize_text(a_tag.get_text()).lower()
        rel = " ".join(a_tag.get("rel", [])).lower()
        if any(hint in text for hint in _NEXT_PAGE_HINTS) or "next" in rel:
            return urljoin(base_url, a_tag["href"])

    return None


def _deduplicate(leads: List[Lead]) -> List[Lead]:
    seen = set()
    unique = []
    for lead in leads:
        key = lead.url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    return unique


# --- Public entry point -----------------------------------------------------------

def scrape(url: str, max_pages: int) -> ScrapeResult:
    """
    Scrape up to `max_pages` pages starting at `url`, following simple
    pagination, and return de-duplicated leads (capped at config.MAX_LEADS).
    """
    max_pages = min(max_pages, config.MAX_PAGES)
    validated_url = validate_url(url)

    all_leads: List[Lead] = []
    current_url = validated_url
    pages_scanned = 0
    visited = set()

    for _ in range(max_pages):
        if current_url in visited:
            break
        visited.add(current_url)

        response = _fetch(current_url)
        pages_scanned += 1

        page_leads = _extract_leads(response.text, response.url)
        all_leads.extend(page_leads)

        if len(all_leads) >= config.MAX_LEADS:
            break

        next_url = _find_next_page_url(response.text, response.url)
        if not next_url or next_url == current_url:
            break
        current_url = next_url

    unique_leads = _deduplicate(all_leads)[: config.MAX_LEADS]

    return ScrapeResult(leads=unique_leads, pages_scanned=pages_scanned)


# --- CSV export ---------------------------------------------------------------

def export_to_csv(result: ScrapeResult, telegram_id: int) -> str:
    """
    Write the scrape result to a uniquely named CSV file and return its path.
    Uses UTF-8 with BOM so Excel correctly displays Arabic / international text.
    """
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"bizleadbot_{telegram_id}_{timestamp}_{unique_id}.csv"
    filepath = os.path.join(config.OUTPUT_DIR, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "snippet"])
        for lead in result.leads:
            writer.writerow([lead.title, lead.url, lead.snippet])

    return filepath
