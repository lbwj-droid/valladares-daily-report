#!/usr/bin/env python3
"""
Valladares' Daily Report — Automated Daily Curator (update_news.py)
Fetches fresh stories + exact article lead images from progressive Indian sources,
global contrast feeds (France/Italy), Culture/K-Pop/Fashion, Cricket, AI, and Money,
rewrites headlines in a snarky Drudge-style voice, and updates index.html directly.
"""

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Bypass SSL certificate quirks on macOS Python installs when reading RSS feeds
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# 1. YOUR CURATED RSS & YOUTUBE FEEDS (No Godi Media; Progressive India + Global Contrast)
FEEDS = {
    "siren": [
        # Direct YouTube RSS feed for The Wire + Google News search for Neha Bora / CJP / CEC
        ("The Wire • YouTube", "https://www.youtube.com/feeds/videos.xml?channel_id=UChWtJey46brNr7qHQpN6KLQ"),
        ("Progressive India Wire", "https://news.google.com/rss/search?q=%22Neha+Bora%22+OR+%22Cockroach+Janata+Party%22+OR+%22Gyanesh+Kumar%22+OR+%22Abhijeet+Dipke%22+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
    ],
    "india_pulse": [
        # Direct Publisher Feeds first (for real article photos) + CJP / SIR / INC targeted feeds + 1 Global Contrast
        ("The Hindu • National", "https://www.thehindu.com/news/national/feeder/default.rss"),
        ("CJP & Anti-SIR Movement", "https://news.google.com/rss/search?q=%22Saurav+Das%22+OR+%22Ashutosh+Ranka%22+OR+%22Abhijeet+Dipke%22+OR+%22Neha+Bora%22+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("INC & Independent Voices", "https://news.google.com/rss/search?q=%22Rahul+Gandhi%22+OR+%22Dhruv+Rathee%22+OR+%22Yogendra+Yadav%22+CEC+OR+SIR+OR+protest+when:7d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("Scroll.in", "https://feeds.feedburner.com/ScrollinArticles.rss"),
        ("Indian Express • India", "https://indianexpress.com/section/india/feed/"),
        ("Global Contrast • Europe", "https://www.theguardian.com/world/europe-news/rss"),
    ],
    "global_geopolitics": [
        ("The Guardian • Europe", "https://www.theguardian.com/world/europe-news/rss"),
        ("BBC World • Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("Al Jazeera Global", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
    "culture_kpop_fashion": [
        ("GQ • Style & Menswear", "https://www.gq.com/feed/rss"),
        ("The Guardian • Fashion", "https://www.theguardian.com/fashion/rss"),
        ("The Guardian • K-Pop & Music", "https://www.theguardian.com/music/k-pop/rss"),
        ("The Verge • Culture", "https://www.theverge.com/rss/culture/index.xml"),
    ],
    "sports": [
        ("ESPNCricinfo • India Cricket", "https://www.espncricinfo.com/rss/content/story/feeds/6.xml"),
        ("BBC Sport • Cricket", "https://feeds.bbci.co.uk/sport/cricket/rss.xml"),
    ],
    "tech_ai": [
        ("TechCrunch • AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("The Verge • AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ],
    "money_climate_internet": [
        ("The Guardian • Climate & Environment", "https://www.theguardian.com/environment/climate-crisis/rss"),
        ("Scroll.in • Economy & Tech", "https://feeds.feedburner.com/ScrollinArticles.rss"),
        ("Al Jazeera • Global Economy", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
}

# Godi Media / Pro-Establishment Filter (excluded automatically)
AVOID_DOMAINS = [
    "republicworld.com",
    "opindia.com",
    "timesnownews.com",
    "zeenews.india.com",
    "sudarshannews.in",
]

# Reject generic placeholder icons (blocks the giant Google News 'G' logo)
BAD_IMAGE_PATTERNS = [
    "googleusercontent.com",
    "gstatic.com",
    "google.com/logos",
    "favicon",
    "logo",
    "avatar",
]


def is_valid_article_photo(img_url):
    """Returns True only if img_url is a real article photo and NOT a Google News / site logo."""
    if not img_url or not img_url.startswith("http"):
        return False
    lower = img_url.lower()
    for bad in BAD_IMAGE_PATTERNS:
        if bad in lower:
            return False
    return True


def fetch_url(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def resolve_real_article_and_image(url, title="", source=""):
    """
    Finds the real article photo for a story:
    1. If YouTube link, extracts exact video thumbnail.
    2. If direct publisher URL, scrapes <meta property="og:image"> and rejects Google logos.
    3. If Google News redirect wrapper, queries Bing News RSS for the exact headline to get the publisher's real photo.
    """
    yt_match = re.search(r"(?:youtube\.com/(?:watch\?v=|live/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    if yt_match:
        return f"https://i.ytimg.com/vi/{yt_match.group(1)}/hqdefault.jpg"

    if "news.google.com" not in url:
        try:
            html = fetch_url(url, timeout=6)
            for pattern in [
                r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\'](https?://[^"\']+)["\']',
                r'<meta[^>]+content=["\'](https?://[^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\']',
            ]:
                m = re.search(pattern, html, re.IGNORECASE)
                if m and is_valid_article_photo(m.group(1)):
                    return m.group(1).replace("&amp;", "&")
        except Exception:
            pass

    if title:
        try:
            clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
            query = urllib.parse.quote(f"{clean_title} {source}".strip())
            bing_rss = f"https://www.bing.com/news/search?q={query}&format=rss"
            xml_text = fetch_url(bing_rss, timeout=6)
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item"):
                for child in item:
                    if "Image" in child.tag and child.text and child.text.startswith("http"):
                        return child.text.strip()
                    if "thumbnail" in child.tag or "content" in child.tag:
                        u = child.attrib.get("url", "")
                        if u.startswith("http"):
                            return u
        except Exception:
            pass

    return ""


def parse_rss_items(feed_label, feed_url, max_items=2):
    """Reads an RSS or Atom (YouTube) feed and returns clean title, link, source, and real media image."""
    items = []
    try:
        xml_text = fetch_url(feed_url)
        root = ET.fromstring(xml_text)

        entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in entries:
            title = (
                item.findtext("title")
                or item.findtext("{http://www.w3.org/2005/Atom}title")
                or ""
            ).strip()

            link = (item.findtext("link") or "").strip()
            if not link:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.attrib.get("href", "").strip()

            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None and source_el.text else feed_label

            if any(bad in link.lower() or bad in source.lower() for bad in AVOID_DOMAINS):
                continue

            img = ""
            for child in item.iter():
                if "thumbnail" in child.tag or "content" in child.tag or "enclosure" in child.tag:
                    candidate = child.attrib.get("url", "")
                    if is_valid_article_photo(candidate):
                        img = candidate
                        break

            if not img:
                desc = item.findtext("description") or ""
                img_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', desc)
                if img_match and is_valid_article_photo(img_match.group(1)):
                    img = img_match.group(1)

            if title and link:
                items.append({"headline": title, "url": link, "source": source, "image": img})
                if len(items) >= max_items:
                    break
    except Exception as e:
        print(f"  [!] Skipped feed ({feed_label}): {e}")
    return items


def snarky_drudge_rewrite(headline, category):
    """
    Rewrites headlines into ALL-CAPS, punchy Drudge-style copy for Gen-Z niblings.
    If GEMINI_API_KEY is set in your environment, uses Gemini 2.5 Flash with your exact brief;
    otherwise applies instant rule-based Drudge formatting.
    """
    clean = re.sub(r"\s+-\s+[^-]+$", "", headline).strip()
    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            prompt = (
                "Rewrite this news headline in a snarky, breezy, ALL-CAPS Drudge Report style for Gen-Z Indian niblings. "
                "Punch up at authorities on protest/CEC/SIR stories, explain what students are fighting for in under 22 words, "
                f"and avoid cringe slang. Category: {category}. Original headline: {clean}"
            )
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ai_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return ai_text.replace('"', "").upper()
        except Exception:
            pass

    return clean.upper()


def build_daily_edition():
    """Fetches stories across all 6 columns + Lead Siren story and attaches exact article images."""
    print("1. Fetching Siren Lead Story...")
    siren_candidates = []
    for label, url in FEEDS["siren"]:
        siren_candidates.extend(parse_rss_items(label, url, max_items=2))

    lead = None
    for cand in siren_candidates:
        img = cand.get("image") or resolve_real_article_and_image(cand["url"], cand["headline"], cand["source"])
        if is_valid_article_photo(img):
            cand["image"] = img
            cand["headline"] = snarky_drudge_rewrite(cand["headline"], "Lead Siren Story")
            lead = cand
            break

    if not lead:
        lead = {
            "headline": "NEHA BORA & CJP CHALLENGE PREVENTIVE DETENTIONS AND ₹10,000 PEACE BONDS AS ANTI-SIR PROTESTS GROW",
            "source": "The Wire • Interview",
            "url": "https://www.youtube.com/live/_BsnYa2ZlcA",
            "image": "https://i.ytimg.com/vi/_BsnYa2ZlcA/hqdefault.jpg",
        }

    section_configs = [
        ("India Pulse (5:1 Mix)", "india_pulse", 1),
        ("Global & Geopolitics (France & Italy)", "global_geopolitics", 1),
        ("Culture, K-Pop & Men's Fashion", "culture_kpop_fashion", 1),
        ("Sports (Cricket & Global)", "sports", 2),
        ("Tech & AI", "tech_ai", 2),
        ("Money, Climate & Internet Culture", "money_climate_internet", 1),
    ]

    columns = []
    for col_title, feed_key, items_per_feed in section_configs:
        print(f"2. Curating column: {col_title}...")
        col_stories = []
        for feed_label, feed_url in FEEDS[feed_key]:
            fetched = parse_rss_items(feed_label, feed_url, max_items=items_per_feed)
            for item in fetched:
                raw_title = item["headline"]
                prefix = "[GLOBAL CONTRAST] " if "Global Contrast" in feed_label else ""
                item["raw_title"] = raw_title
                item["headline"] = prefix + snarky_drudge_rewrite(raw_title, col_title)
                col_stories.append(item)

        # Find a real article photo for the top story (and promote the first story with a verified photo to #0)
        for idx, st in enumerate(col_stories):
            img = st.get("image") or resolve_real_article_and_image(st["url"], st.get("raw_title", ""), st["source"])
            if is_valid_article_photo(img):
                st["image"] = img
                if idx > 0:
                    col_stories.insert(0, col_stories.pop(idx))
                break
            else:
                st["image"] = ""

        for st in col_stories:
            st.pop("raw_title", None)

        columns.append({"title": col_title, "stories": col_stories[:6]})

    return {"splash": lead, "columns": columns}


def update_index_html(news_payload, html_path="index.html"):
    """Injects the newly curated daily news JSON directly into index.html (matches any indentation)."""
    if not os.path.exists(html_path):
        print(f"[!] Could not find {html_path} in current directory.")
        return False

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    new_json_str = "var defaultNews = " + json.dumps(news_payload, indent=4, ensure_ascii=False) + ";"
    # Matches var/const/let defaultNews = { ... }; regardless of indentation or how many times the script ran before!
    pattern = r"(?:var|const|let)\s+defaultNews\s*=\s*\{[\s\S]*?\n\s*\};"

    if not re.search(pattern, html):
        print("[!] Could not locate defaultNews block in index.html")
        return False

    updated_html = re.sub(pattern, lambda _: new_json_str, html, count=1)

    siren_source = news_payload.get("splash", {}).get("source", "DAILY LEAD STORY").upper()
    updated_html = re.sub(
        r'<div class="splash-sub">.*?</div>',
        f'<div class="splash-sub">[{siren_source}] &mdash; Tap headline to read or watch the full lead report</div>',
        updated_html,
    )

    today_key = "valladaresReport_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    updated_html = re.sub(r'var STORAGE_KEY = "[^"]+";', f'var STORAGE_KEY = "{today_key}";', updated_html)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(updated_html)
    print(f"[✓] Updated {html_path} with fresh stories and real article images ({today_key})!")
    return True


if __name__ == "__main__":
    edition = build_daily_edition()
    update_index_html(edition)
