# config.py
"""
Configuration file for AutoRevenue Enterprise Intelligence v10.0
"""
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file for local development

# --- Company Profiles ---
# These profiles will drive the relevance scoring and strategic analysis
COMPANY_PROFILES = {
    "EzziUK": {
        "name": "EzziUK",
        "services": [
            "social housing solutions", "rent guarantee schemes", "landlord services",
            "property management for social housing", "tenant placement",
            "housing maintenance", "lettings management"
        ],
        "keywords": [
            "social housing", "HMO", "guaranteed rent", "lettings", "landlord",
            "property management", "housing association", "local authority housing",
            "supported living accommodation" # Overlap/synergy with RehabilityUK
        ],
        "strengths": ["Strong network in social housing", "Expertise in rent guarantee"],
        "weaknesses": ["Limited capacity for large-scale construction", "New to certain geographical areas"]
    },
    "RehabilityUK": {
        "name": "RehabilityUK",
        "services": [
            "supported living services", "domiciliary care", "complex care packages",
            "mental health support services", "learning disability services",
            "autism specialist care", "respite care"
        ],
        "keywords": [
            "supported living", "care services", "domiciliary care", "NHS CCG",
            "local authority social care", "mental health", "learning disabilities",
            "autism care", "tender care", "framework agreement care"
        ],
        "strengths": ["Highly trained care staff", "CQC registered", "Strong clinical governance"],
        "weaknesses": ["Geographically limited service areas initially", "Dependent on commissioner funding cycles"]
    }
}

# --- Data Acquisition Settings ---
# User-Agent for web scraping
USER_AGENT = "AutoRevenueEnterpriseIntelligence/10.0 (Python Scraper; +http://example.com/botinfo)" # Replace with actual info URL

# List of portals to scan. Each entry should be a dictionary.
# 'type' can be 'api', 'rss', 'generic_scrape'
# 'url' is the base URL or API endpoint
# 'parser_func' (for 'generic_scrape') would be a reference to a specific parsing function if needed
PORTAL_CONFIGS = [
    {
        "name": "Contracts Finder (Opportunities)",
        "type": "api",
        "url": "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/search?pg=1&results_size=50", # Example for first 50, pagination needed
        "keywords_param": "q", # Parameter name for keywords in API if supported, or None
        "api_specific_params": {"stages": "opportunity"}, # Additional params
        "max_pages_to_scan": 2 # Limit for demo purposes
    },
    {
        "name": "Find a Tender Service (FTS)",
        "type": "api", # FTS uses an OCDS-like structure but might require different endpoints/auth
        "url": "https://www.find-tender.service.gov.uk/ mahdollisuuksia/api/v1/releasepackages?page={page_num}&size=20", # Placeholder URL, FTS API details need verification
        "keywords_param": "searchTerm", # Example
        "api_specific_params": {},
        "max_pages_to_scan": 1
    },
    # Add more portal configurations here.
    # Example for a generic local authority (conceptual - would need specific scraper logic)
    # {
    #     "name": "Example Local Authority",
    #     "type": "generic_scrape",
    #     "start_url": "https://www.example-council.gov.uk/tenders",
    #     "link_selector": "a.tender-link", # CSS selector for tender links
    #     "robots_txt_url": "https://www.example-council.gov.uk/robots.txt"
    # },
]

# --- Intelligence Analyzer Settings ---
SCORING_WEIGHTS = {
    "keyword_match": 0.4,
    "value_tier": 0.3,     # Based on estimated contract value
    "company_fit": 0.2,    # How well it aligns with core services
    "urgency": 0.1         # Closeness to deadline
}
MIN_RELEVANCE_SCORE_TO_REPORT = 60 # Out of 100

# --- Reporting Settings ---
# Email settings using Google OAuth
# These will be loaded from environment variables in a production GitHub Actions setup
# For local testing, you can use a .env file or set them directly (not recommended for commit)
EMAIL_SENDER = os.getenv("GMAIL_SENDER_ADDRESS")
EMAIL_RECIPIENTS = { # Company name to recipient email mapping
    "EzziUK": os.getenv("EZZIUK_RECIPIENT_EMAIL"),
    "RehabilityUK": os.getenv("REHABILITYUK_RECIPIENT_EMAIL")
}
# Path to Google OAuth credentials files (expected to be populated from GitHub Secrets)
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
EMAIL_SUBJECT_PREFIX = "AutoRevenue Intel: "

# --- Data Storage & Caching ---
CACHE_FILE_PATH = "data/cache.json"
PROCESSED_TENDERS_DB_PATH = "data/processed_tenders.db" # SQLite DB
CACHE_EXPIRY_DAYS = 1 # How long to keep items in URL cache
TENDER_HISTORY_DAYS = 365 # How far back to look for pattern analysis

# --- System Settings ---
LOG_LEVEL = "INFO" # DEBUG, INFO, WARNING, ERROR
MAX_CONCURRENT_SCRAPERS = 3 # If implementing concurrency
REQUEST_DELAY_SECONDS = 2 # Base delay between requests to the same domain
MAX_RETRIES = 3 # For network requests

# GitHub Actions specific settings
GITHUB_WORKSPACE = os.getenv("GITHUB_WORKSPACE", ".")
