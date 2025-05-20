# utils.py
"""
Utility functions for AutoRevenue Enterprise Intelligence.
Includes robots.txt parsing and other common helpers.
"""
import time
import requests
import logging
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urljoin

from config import USER_AGENT, REQUEST_DELAY_SECONDS

logger = logging.getLogger(__name__)

# Cache for robots.txt parsers to avoid re-fetching and re-parsing
_robot_parsers_cache = {}

def get_robot_parser(base_url: str) -> RobotFileParser | None:
    """
    Fetches and parses the robots.txt file for a given base URL.
    Caches the parser object.
    """
    if base_url in _robot_parsers_cache:
        return _robot_parsers_cache[base_url]

    robots_url = urljoin(base_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        # It's good practice to have a timeout for fetching robots.txt as well
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(robots_url, headers=headers, timeout=10)
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
            _robot_parsers_cache[base_url] = parser
            logger.info(f"Successfully fetched and parsed robots.txt for {base_url}")
            return parser
        elif 400 <= response.status_code < 500: # Client errors (401, 403, 404)
             # Assume allow all if robots.txt is missing or inaccessible with client error
            logger.warning(f"robots.txt for {base_url} returned {response.status_code}. Assuming allow all.")
            parser.allow_all = True # Default behavior if file not found or access denied
            _robot_parsers_cache[base_url] = parser # Cache this decision
            return parser
        else:
            logger.error(f"Failed to fetch robots.txt for {base_url}: HTTP {response.status_code}")
            return None # Indicate failure to fetch
    except requests.RequestException as e:
        logger.error(f"Request error fetching robots.txt for {base_url}: {e}")
        # In case of network errors, safer to assume disallow or handle carefully
        # For now, let's assume allow all if robots.txt fetch fails, but log it.
        # A more conservative approach might be to disallow.
        parser.allow_all = True 
        _robot_parsers_cache[base_url] = parser
        return parser


def can_fetch(url: str, user_agent: str = USER_AGENT) -> bool:
    """
    Checks if the given URL can be fetched according to robots.txt.
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    parser = get_robot_parser(base_url)
    if parser:
        return parser.can_fetch(user_agent, url)
    
    # If robots.txt could not be fetched/parsed, default to a cautious approach (or log and allow)
    # Current get_robot_parser returns a parser with allow_all=True on fetch error,
    # so this will effectively allow if robots.txt is problematic.
    logger.warning(f"Could not get robots.txt parser for {base_url}. Assuming allowed for {url}.")
    return True


def respectful_request(method: str, url: str, **kwargs) -> requests.Response | None:
    """
    Makes an HTTP request if allowed by robots.txt and adds a delay.
    """
    if not can_fetch(url, USER_AGENT):
        logger.warning(f"Skipping {url} due to robots.txt restrictions for user-agent {USER_AGENT}.")
        return None

    # Add delay
    time.sleep(REQUEST_DELAY_SECONDS)
    
    headers = kwargs.pop('headers', {})
    headers['User-Agent'] = USER_AGENT
    
    try:
        response = requests.request(method, url, headers=headers, timeout=15, **kwargs)
        response.raise_for_status()  # Raise HTTPError for bad responses (4XX or 5XX)
        logger.debug(f"Successfully fetched {url} (status: {response.status_code})")
        return response
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error for {url}: {e}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error for {url}: {e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error for {url}: {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"General request error for {url}: {e}")
    return None

def normalize_text(text: str | None) -> str:
    """
    Normalizes text by converting to lowercase and removing extra whitespace.
    """
    if text is None:
        return ""
    return ' '.join(text.lower().split())

def generate_tender_id(url: str, title: str) -> str:
    """
    Generates a unique ID for a tender.
    Can be a hash of URL or a specific ID from the tender itself if available.
    For simplicity, let's use a hash of the URL.
    """
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:16]

if __name__ == '__main__':
    # Test functions
    # print("Testing can_fetch for Google (should be True for generic user agent):")
    # print(can_fetch("https://www.google.com/search", "TestAgent"))
    # print(can_fetch("https://www.google.com/search", "*")) # Specific disallowed path
    
    # print("\nTesting respectful_request (example):")
    # response = respectful_request("GET", "https://www.gov.uk")
    # if response:
    #     print(f"Fetched gov.uk, content length: {len(response.text)}")
    pass
