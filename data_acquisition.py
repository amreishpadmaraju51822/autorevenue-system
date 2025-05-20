# data_acquisition.py
"""
Modules for acquiring procurement opportunity data from various portals.
"""
import json
import logging
import datetime
import sqlite3
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from config import (
    PORTAL_CONFIGS, CACHE_FILE_PATH, CACHE_EXPIRY_DAYS,
    USER_AGENT, REQUEST_DELAY_SECONDS, PROCESSED_TENDERS_DB_PATH
)
from utils import respectful_request, normalize_text, generate_tender_id

logger = logging.getLogger(__name__)

# --- Data Caching (Simple JSON file-based) ---
# For a production system, consider a more robust caching solution (Redis, memcached)
# or a proper database for visited URLs and their content hashes.
_url_cache = {}

def load_url_cache():
    global _url_cache
    try:
        with open(CACHE_FILE_PATH, 'r') as f:
            _url_cache = json.load(f)
            # Remove expired entries
            now = datetime.datetime.now().timestamp()
            expiry_seconds = CACHE_EXPIRY_DAYS * 24 * 60 * 60
            _url_cache = {
                url: data for url, data in _url_cache.items()
                if (now - data.get("timestamp", 0)) < expiry_seconds
            }
    except FileNotFoundError:
        _url_cache = {}
    except json.JSONDecodeError:
        logger.error(f"Error decoding cache file {CACHE_FILE_PATH}. Starting with empty cache.")
        _url_cache = {}

def save_url_cache():
    try:
        with open(CACHE_FILE_PATH, 'w') as f:
            json.dump(_url_cache, f, indent=4)
    except IOError:
        logger.error(f"Could not write to cache file {CACHE_FILE_PATH}")

def add_to_url_cache(url: str, content_hash: str):
    _url_cache[url] = {"timestamp": datetime.datetime.now().timestamp(), "hash": content_hash}

def is_url_cached_and_unchanged(url: str, current_content_hash: str) -> bool:
    cached_data = _url_cache.get(url)
    if cached_data and cached_data.get("hash") == current_content_hash:
        return True
    return False

# --- Processed Tenders Database (SQLite) ---
def init_db():
    conn = sqlite3.connect(PROCESSED_TENDERS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenders (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT UNIQUE,
            source TEXT,
            published_date TEXT,
            closing_date TEXT,
            description TEXT,
            value_text TEXT, -- Store as text, parse later if needed
            data_json TEXT, -- Store raw JSON data from API if available
            first_seen_date TEXT,
            last_seen_date TEXT,
            status TEXT DEFAULT 'new' -- e.g., new, processing, reported, archived
        )
    ''')
    conn.commit()
    conn.close()

def is_tender_processed(tender_id: str, conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tenders WHERE id = ?", (tender_id,))
    return cursor.fetchone() is not None

def store_tender_data(tender_data: Dict[str, Any], conn: sqlite3.Connection):
    cursor = conn.cursor()
    now_iso = datetime.datetime.now().isoformat()
    try:
        cursor.execute("""
            INSERT INTO tenders (id, title, url, source, published_date, closing_date, description, value_text, data_json, first_seen_date, last_seen_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                closing_date=excluded.closing_date,
                value_text=excluded.value_text,
                data_json=excluded.data_json,
                last_seen_date=excluded.last_seen_date
        """, (
            tender_data['id'],
            tender_data['title'],
            tender_data['url'],
            tender_data['source'],
            tender_data.get('published_date'),
            tender_data.get('closing_date'),
            tender_data['description'],
            tender_data.get('value_text'),
            json.dumps(tender_data.get('raw_data', {})),
            now_iso,
            now_iso
        ))
        conn.commit()
        logger.info(f"Stored/Updated tender: {tender_data['id']} from {tender_data['source']}")
    except sqlite3.Error as e:
        logger.error(f"SQLite error storing tender {tender_data['id']}: {e}")


class Tender:
    """Represents a procurement opportunity."""
    def __init__(self, id: str, title: str, url: str, source: str, description: str,
                 published_date: Optional[str] = None, closing_date: Optional[str] = None,
                 value_text: Optional[str] = None, raw_data: Optional[Dict] = None):
        self.id = id
        self.title = normalize_text(title)
        self.url = url
        self.source = source
        self.description = normalize_text(description)
        self.published_date = published_date
        self.closing_date = closing_date
        self.value_text = value_text
        self.raw_data = raw_data if raw_data else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "published_date": self.published_date,
            "closing_date": self.closing_date,
            "value_text": self.value_text,
            "raw_data": self.raw_data
        }

class BasePortalScanner(ABC):
    """Abstract base class for portal scanners."""
    def __init__(self, portal_config: Dict[str, Any]):
        self.name = portal_config['name']
        self.config = portal_config
        self.db_conn = sqlite3.connect(PROCESSED_TENDERS_DB_PATH) # Each scanner gets its own connection for thread safety if threaded later

    def __del__(self):
        if self.db_conn:
            self.db_conn.close()

    @abstractmethod
    def scan(self) -> List[Tender]:
        """Scans the portal and returns a list of Tender objects."""
        pass

    def _process_tender_item(self, item_data: Dict[str, Any], source_name: str) -> Optional[Tender]:
        """
        Processes a raw item from a portal into a Tender object.
        This method needs to be adapted by subclasses based on the portal's data structure.
        """
        # Common fields extraction logic (example, needs customization)
        title = item_data.get('title')
        url = item_data.get('url') # This should be a direct link to the tender
        description = item_data.get('description')
        
        if not all([title, url, description]):
            logger.warning(f"Missing essential data (title, url, or description) for an item from {source_name}. Skipping.")
            return None

        tender_id = generate_tender_id(url, title)

        # Check if tender is already processed and unchanged (not implemented here, could use content hash)
        # For now, we check if it's in the DB. If new, it gets added. If existing, it gets updated.
        # if is_tender_processed(tender_id, self.db_conn):
        #     logger.debug(f"Tender {tender_id} already processed. Checking for updates.")
            # Further logic might be needed to see if it truly changed if an update mechanism is desired beyond just last_seen_date

        return Tender(
            id=tender_id,
            title=str(title),
            url=str(url),
            source=source_name,
            description=str(description),
            published_date=item_data.get('published_date'),
            closing_date=item_data.get('closing_date'),
            value_text=item_data.get('value_text'),
            raw_data=item_data.get('raw_data')
        )

class ContractsFinderScanner(BasePortalScanner):
    """Scanner for Contracts Finder (gov.uk) using their OCDS-based API."""
    def scan(self) -> List[Tender]:
        logger.info(f"Scanning {self.name}...")
        found_tenders: List[Tender] = []
        base_url = self.config['url'] # Base search URL
        max_pages = self.config.get('max_pages_to_scan', 1)
        page_num = 1

        while page_num <= max_pages:
            # Contracts Finder API seems to use 'pg' for page number
            # And results_size for items per page.
            # The provided URL already has pg=1. We need to adjust it.
            if "pg=" in base_url:
                 current_url = base_url.replace(f"pg={base_url.split('pg=')[1].split('&')[0]}", f"pg={page_num}")
            else: # If pg parameter not in base_url, append it.
                separator = '&' if '?' in base_url else '?'
                current_url = f"{base_url}{separator}pg={page_num}"

            logger.debug(f"Fetching from URL: {current_url}")
            response = respectful_request("GET", current_url)
            if not response:
                logger.warning(f"Failed to fetch data from {self.name} at page {page_num}.")
                break 

            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON from {self.name} at page {page_num}. Content: {response.text[:200]}")
                break
            
            releases = data.get("releases", [])
            if not releases:
                logger.info(f"No more releases found on {self.name} at page {page_num}.")
                break

            for release in releases:
                tender_data = self._parse_ocds_release(release)
                if tender_data:
                    tender_obj = self._process_tender_item(tender_data, self.name)
                    if tender_obj:
                        if not is_tender_processed(tender_obj.id, self.db_conn):
                             found_tenders.append(tender_obj)
                        store_tender_data(tender_obj.to_dict(), self.db_conn)

            logger.info(f"Found {len(releases)} items on page {page_num} of {self.name}. Processed {len(found_tenders)} new tenders so far from this source.")
            page_num += 1
            if page_num > data.get("max_pg", max_pages): # Check if API provides max pages
                break

        return found_tenders

    def _parse_ocds_release(self, release: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses a single OCDS release from Contracts Finder."""
        try:
            # Navigate OCDS structure (this is a simplified example)
            # OCID is often used as a unique ID, but URL itself is also good for our system's ID generation.
            # ocid = release.get("ocid")
            
            tender_info = release.get("tender", {})
            title = tender_info.get("title")
            description = tender_info.get("description")
            
            # Try to find a canonical URL to the tender notice
            # This can be complex in OCDS; often in documents or related processes
            # For Contracts Finder, the direct link is usually available via their website,
            # but the API might not directly expose it in an obvious field.
            # A common pattern for Contracts Finder is: https://www.contractsfinder.service.gov.uk/Notice/{GUID}
            # The GUID might be part of the OCID or another identifier.
            # For this example, we'll construct a placeholder or use a link from `tender` if available.
            # Let's assume `id` in `tender` might be part of the URL or use `release.get('id')` if it's more suitable.
            # This part is CRITICAL and needs careful mapping from actual API responses.
            # For now, using a placeholder based on title.
            # A better approach: search for `uri` fields within `tender.documents` or `tender.items`.
            # For Contracts Finder, a notice ID often forms part of the OCID: "ocds-b5fd17-nnnnnnnn-nnnn-nnnn-nnnn-nnnnnnnnnnnn"
            # The actual notice ID is after the prefix.
            ocid = release.get("ocid")
            notice_id_part = None
            if ocid and "ocds-b5fd17-" in ocid: # Common prefix for Contracts Finder
                notice_id_part = ocid.split("ocds-b5fd17-", 1)[-1]
            
            # If we have multiple tags, we might have multiple URLs.
            # For now, we look for a canonical one.
            # In OCDS, `tenderUrl` or similar within `tender` or `planning` objects.
            # Contracts Finder web UI links look like: https://www.contractsfinder.service.gov.uk/Notice/GUID
            # Let's try to find such a GUID. The 'id' of the release package might be it.
            # If the 'id' in the release is a UUID-like string, it's a good candidate.
            # Or sometimes `tender.id` can be the notice ID.
            # This needs checking with actual API response.
            # For example, if `release.id` is "ocds-b5fd17-e892e9e2-...." then "e892e9e2-..." is the notice ID.
            
            url = f"https://www.contractsfinder.service.gov.uk/Notice/{notice_id_part}" if notice_id_part else f"https://www.contractsfinder.service.gov.uk/Search/Results?query={title.replace(' ','+')}" # Fallback URL

            if hasattr(tender_info, 'documents') and tender_info['documents']:
                for doc in tender_info['documents']:
                    if doc.get('documentType') == 'notice' and doc.get('url'):
                        url = doc['url'] # Prefer an official notice URL
                        break
            
            # Sometimes the most direct link might be in `tender.electronicAuctions.url` or similar location depending on notice type.
            # A more robust way for Contracts Finder:
            # The OCID itself often contains the Notice ID that can be used to construct the URL.
            # e.g. ocid = "ocds-b5fd17-04b04858-5891-4c32-a879-34cb97a5f5a9"
            # URL = "https://www.contractsfinder.service.gov.uk/Notice/04b04858-5891-4c32-a879-34cb97a5f5a9"
            if ocid:
                parts = ocid.split('-')
                if len(parts) > 1 and len(parts[-1]) == 36 and len(parts[-2]) == 4 and len(parts[-3]) == 4 and len(parts[-4]) == 4 and len(parts[-5]) == 8 : # UUID check
                    potential_id = "-".join(parts[-(len(parts)-1):]) if "ocds-b5fd17-" in ocid else ocid
                    if len(potential_id) > 30: # Heuristic for UUID-like structure
                         url = f"https://www.contractsfinder.service.gov.uk/Notice/{potential_id}"


            published_date = release.get("date") # Publication date of this release
            closing_date = tender_info.get("tenderPeriod", {}).get("endDate")
            
            value_info = tender_info.get("value", {})
            value_text = f"{value_info.get('amount')} {value_info.get('currency')}" if value_info.get('amount') else None

            if not title or not url:
                logger.warning(f"Could not parse essential fields (title/url) from OCDS release: {ocid}")
                return None

            return {
                "title": title,
                "url": url,
                "description": description,
                "published_date": published_date,
                "closing_date": closing_date,
                "value_text": value_text,
                "raw_data": release # Store the whole release for deeper analysis later
            }
        except Exception as e:
            logger.error(f"Error parsing OCDS release: {e}. Release data: {json.dumps(release)[:500]}")
            return None


class GenericWebsiteScraper(BasePortalScanner):
    """
    Conceptual scraper for generic websites.
    Requires specific selectors and parsing logic per site.
    This is a placeholder to show the structure.
    """
    def scan(self) -> List[Tender]:
        logger.info(f"Scanning {self.name} (generic web scraper)...")
        found_tenders: List[Tender] = []
        
        start_url = self.config.get("start_url")
        if not start_url:
            logger.error(f"No start_url configured for {self.name}")
            return []

        response = respectful_request("GET", start_url)
        if not response or not response.text:
            logger.error(f"Failed to fetch start page for {self.name}: {start_url}")
            return []

        # Basic caching check based on page content hash (simple example)
        # import hashlib
        # content_hash = hashlib.md5(response.text.encode()).hexdigest()
        # if is_url_cached_and_unchanged(start_url, content_hash):
        #     logger.info(f"Page {start_url} unchanged since last scan,_url_cache.")
        #     # return [] # Or load from a more persistent cache if needed.
        # add_to_url_cache(start_url, content_hash)
        
        soup = BeautifulSoup(response.text, 'lxml') # 'lxml' is usually faster
        
        # --- This part is highly site-specific ---
        # Example: find links to tender detail pages
        link_selector = self.config.get("link_selector") # e.g., "a.tender-notice-link"
        if not link_selector:
            logger.error(f"No link_selector configured for {self.name}")
            return []

        for link_tag in soup.select(link_selector):
            tender_url = link_tag.get('href')
            if not tender_url:
                continue
            
            # Ensure URL is absolute
            from urllib.parse import urljoin
            tender_url = urljoin(start_url, tender_url)
            
            # Now, fetch and parse the tender detail page
            # This would involve another respectful_request and parsing logic
            logger.debug(f"Found potential tender link: {tender_url} on {self.name}")

            # Check if already processed (using URL)
            temp_tender_id = generate_tender_id(tender_url, tender_url) # Temp ID with URL as title
            if is_tender_processed(temp_tender_id, self.db_conn):
                logger.debug(f"Tender at {tender_url} likely processed. Checking for updates or skipping.")
                # For now, we skip if ID exists. A more robust way is to fetch and compare.
                # Or update last_seen_date if fetched and identical.
                continue 

            # Placeholder for fetching and parsing detail page
            # tender_page_response = respectful_request("GET", tender_url)
            # if tender_page_response and tender_page_response.text:
            #     detail_soup = BeautifulSoup(tender_page_response.text, 'lxml')
            #     # Extract title, description, dates, value etc. from detail_soup
            #     # This is the most complex part of web scraping.
            #     title = detail_soup.select_one("h1.tender-title").text # Example
            #     description = detail_soup.select_one("div.tender-description").text # Example
            #     ...
            #     tender_item_data = {
            #         "title": title, "url": tender_url, "description": description, ...
            #     }
            #     tender_obj = self._process_tender_item(tender_item_data, self.name)
            #     if tender_obj:
            #         found_tenders.append(tender_obj)
            #         store_tender_data(tender_obj.to_dict(), self.db_conn)
            
            logger.warning(f"GenericWebsiteScraper for {self.name} is conceptual. Detail page parsing for {tender_url} not implemented.")

        logger.info(f"Generic scan of {self.name} complete. Found {len(found_tenders)} new tenders.")
        return found_tenders


def get_scanner_for_portal(portal_config: Dict[str, Any]) -> Optional[BasePortalScanner]:
    """Factory function to get the appropriate scanner for a portal type."""
    portal_type = portal_config.get("type")
    if portal_type == "api":
        # For now, assume Contracts Finder is the main API type implemented
        if "contractsfinder.service.gov.uk" in portal_config.get("url", ""):
            return ContractsFinderScanner(portal_config)
        # Add other API scanner types here, e.g., FTSScanner
        logger.warning(f"API scanner for {portal_config['name']} not fully implemented, using generic approach if possible or skipping.")
        # Fallback or specific handling for other APIs can be added.
        return None # Or a more generic APIScanner if one is created
    elif portal_type == "generic_scrape":
        logger.warning(f"GenericWebsiteScraper for {portal_config['name']} is conceptual and may not yield results without specific parsing logic.")
        return GenericWebsiteScraper(portal_config)
    # Add other types like 'rss', 'nhs_specific_api', etc.
    else:
        logger.error(f"Unknown portal type: {portal_type} for {portal_config['name']}")
        return None

def run_all_scanners() -> List[Tender]:
    """Runs all configured scanners and aggregates new tenders."""
    init_db() # Ensure DB and table exist
    load_url_cache() # Load URL cache at the beginning of a scan run
    
    all_new_tenders: List[Tender] = []
    for portal_conf in PORTAL_CONFIGS:
        logger.info(f"Initializing scanner for: {portal_conf['name']}")
        scanner = get_scanner_for_portal(portal_conf)
        if scanner:
            try:
                new_tenders_from_portal = scanner.scan()
                all_new_tenders.extend(new_tenders_from_portal)
                logger.info(f"Scanner {scanner.name} found {len(new_tenders_from_portal)} new tenders.")
            except Exception as e:
                logger.error(f"Error running scanner {scanner.name}: {e}", exc_info=True)
        else:
            logger.warning(f"No suitable scanner found or configured for {portal_conf['name']}. Skipping.")
            
    save_url_cache() # Save cache at the end
    logger.info(f"All scanners finished. Total new tenders found: {len(all_new_tenders)}")
    return all_new_tenders

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting data acquisition test run...")
    # Create dummy data folder if it doesn't exist
    import os
    if not os.path.exists("data"):
        os.makedirs("data")
    
    new_tenders = run_all_scanners()
    if new_tenders:
        print(f"\n--- Found {len(new_tenders)} New Tenders ---")
        for i, tender in enumerate(new_tenders):
            print(f"{i+1}. {tender.title} ({tender.source}) - {tender.url}")
            if i > 5 : break # print only few
    else:
        print("No new tenders found in this test run.")

    # Example: Querying the DB
    conn = sqlite3.connect(PROCESSED_TENDERS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url, source, status FROM tenders ORDER BY first_seen_date DESC LIMIT 5")
    print("\n--- Last 5 Processed Tenders from DB ---")
    for row in cursor.fetchall():
        print(row)
    conn.close()
