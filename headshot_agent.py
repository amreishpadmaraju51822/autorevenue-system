#!/usr/bin/env python3
import os
import logging
import requests
import json
import random
import sqlite3
import time
import re
import hashlib
import csv
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, urlparse, unquote
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- NEW IMPORTS ---
import feedparser # For RSS feeds
import spacy      # For NLP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HEADSHOT")

# --- NLP Model Loading (do this once) ---
NLP_MODEL = None
try:
    NLP_MODEL = spacy.load("en_core_web_sm") # Small English model
    logger.info("SpaCy NLP model 'en_core_web_sm' loaded successfully.")
except OSError:
    logger.error("SpaCy model 'en_core_web_sm' not found. Please download it by running: python -m spacy download en_core_web_sm")
    NLP_MODEL = None # Ensure it's None if loading fails

# Database path
DATABASE_PATH = "data/headshot_vault.db"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# User agent rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
]

# --- COMPANY PROFILES & SIGNALS (Keep as is, or expand) ---
# (COMPANY_PROFILES, PROFIT_SIGNALS, HIDDEN_OPPORTUNITY_SIGNALS remain the same as your previous version)
COMPANY_PROFILES = {
    "EzziUK": {
        "name": "EzziUK",
        "services": ["social housing solutions", "rent guarantee schemes", "landlord services", "property management for social housing", "tenant placement", "housing maintenance", "lettings management"],
        "target_sectors": ["housing associations", "local authorities", "councils", "government housing departments", "NHS trust accommodation"],
        "keywords": ["social housing", "HMO", "guaranteed rent", "lettings", "landlord", "property management", "housing association", "local authority housing", "supported living accommodation", "affordable housing", "temporary accommodation"],
        "geographic_focus": ["London", "Birmingham", "Manchester", "Leeds", "Sheffield", "Bristol"],
        "ideal_contract_duration": "3-5 years",
        "ideal_contract_value_range": (100000, 5000000),
        "competitor_names": ["Mears Group", "Pinnacle Group", "Places for People", "Civitas Housing", "Home Group", "Sanctuary Housing", "Clarion Housing", "L&Q"],
        "contract_success_signals": ["housing renewal", "management outsourcing", "housing stock transfer", "property portfolio expansion", "maintenance contract renewal", "urgent housing need", "temporary accommodation requirements"],
        "existing_buyers": ["London Borough of Hackney", "Birmingham City Council", "Manchester City Council", "Leeds Housing Options", "Sheffield Housing Services"],
        "buyer_decision_makers": {"role_titles": ["Head of Housing", "Director of Housing", "Procurement Manager", "Housing Options Manager", "Social Housing Lead"]},
        "minimum_profit_margin": 15
    },
    "RehabilityUK": {
        "name": "RehabilityUK",
        "services": ["supported living services", "domiciliary care", "complex care packages", "mental health support services", "learning disability services", "autism specialist care", "respite care"],
        "target_sectors": ["NHS", "Clinical Commissioning Groups", "local authority social care", "health trusts", "private healthcare groups"],
        "keywords": ["supported living", "care services", "domiciliary care", "NHS CCG", "local authority social care", "mental health", "learning disabilities", "autism care", "tender care", "framework agreement care", "CQC registered"],
        "geographic_focus": ["London", "Birmingham", "Manchester", "Liverpool", "Newcastle", "Edinburgh"],
        "ideal_contract_duration": "2-4 years",
        "ideal_contract_value_range": (200000, 3000000),
        "competitor_names": ["Dimensions UK", "Care UK", "HC-One", "Voyage Care", "Lifeways Group", "Turning Point", "The Priory Group", "Exemplar Health Care"],
        "contract_success_signals": ["care provider failure", "service quality issues", "commissioner dissatisfaction", "CQC improvement requirements", "urgent care needs", "hospital discharge targets", "delayed transfer of care", "integration of health and social care"],
        "existing_buyers": ["NHS England", "London Borough of Camden", "Birmingham Adult Social Care", "Manchester Health and Care Commissioning", "NHS Highland"],
        "buyer_decision_makers": {"role_titles": ["Commissioning Manager", "Head of Adult Social Care", "CCG Procurement Lead", "Director of Social Services", "Care Quality Lead"]},
        "minimum_profit_margin": 18
    }
}
PROFIT_SIGNALS = ["staff shortages", "service disruption", "operational challenges", "recruitment difficulties", "staffing crisis", "capacity issues", "emergency provision", "service failure", "intervention required", "financial difficulties", "budget pressure", "budget shortfall", "cost saving requirements", "efficiency targets", "funding gap", "tender republication", "contract rebid", "emergency procurement", "urgent requirement", "expedited procurement", "immediate need", "deadline extension", "rapid deployment", "immediate start", "quality concerns", "CQC report", "improvement required", "service rating decline", "performance issues", "compliance failure", "specialized provider", "niche requirement", "complex needs", "specific expertise", "technical requirement"]
HIDDEN_OPPORTUNITY_SIGNALS = ["direct award potential", "limited competition", "prior information notice", "reduced procedure", "specialist requirement", "incumbency challenge", "framework mini-competition", "call-off potential", "DPS opportunity", "low response expected", "limited market interest", "niche service area", "challenging requirements", "limited market supply", "specialist only", "expedited procurement", "streamlined process", "urgent need", "accelerated procedure", "emergency provision", "specific geographic requirement", "limited provider pool", "remote location", "challenging location", "accessibility issues"]
NEGATIVE_KEYWORDS = { # Keywords that might reduce opportunity score
    "expressions of interest only": -10,
    "market research only": -15,
    "indicative only": -5,
    "no funding secured": -20,
    "prior information notice for information only": -10,
    "archived tender": -25,
    "closed opportunity": -25, # If not an award notice
    "cancelled tender": -20
}
KEYWORD_WEIGHTS = { # Example weights, expand this
    "direct award": 15,
    "urgent requirement": 10,
    "emergency procurement": 12,
    "sole supplier": 10,
    "limited competition": 8,
    "incumbent failing": 20, # This would come from competitor analysis
    "cqc inadequate": 18 # From competitor analysis
}


# --- DatabaseManager Class (Largely the same, minor improvements for robustness) ---
class DatabaseManager:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._initialize_db()

    def _execute_query(self, query, params=None, commit=False, fetch_one=False, fetch_all=False):
        """Helper function to execute database queries."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10) # Added timeout
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if commit:
                conn.commit()
            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
            return cursor # For operations like lastrowid or rowcount
        except sqlite3.Error as e:
            logger.error(f"DATABASE_ERROR :: Query: {query[:100]}... :: Error: {e}", exc_info=True)
            # For critical errors like "database is locked", re-raising might be an option
            # or specific handling. For now, just log.
            if "locked" in str(e).lower():
                logger.warning("Database is locked. This might be due to concurrent access or long transaction.")
            return None
        finally:
            if conn:
                conn.close()

    def _initialize_db(self):
        # ... (Keep the _initialize_db method exactly as in your previous working version) ...
        # ... (It was quite comprehensive and good) ...
        # Primary opportunities table - comprehensive structure
        create_opportunities_table = '''
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY, title TEXT, description TEXT, source TEXT, source_url TEXT,
            estimated_value REAL, estimated_profit_margin REAL, closing_date TEXT, discovery_date TEXT,
            buyer_name TEXT, buyer_type TEXT, headshot_score REAL, profit_probability REAL,
            win_probability REAL, competition_level TEXT, status TEXT, company TEXT,
            notification_sent INTEGER DEFAULT 0, analysis_complete INTEGER DEFAULT 0,
            follow_up_actions TEXT, data_json TEXT
        )'''
        self._execute_query(create_opportunities_table, commit=True)
        # Buyer intelligence table
        create_buyers_table = '''
        CREATE TABLE IF NOT EXISTS buyers (
            id TEXT PRIMARY KEY, name TEXT, type TEXT, region TEXT, website TEXT, procurement_approach TEXT,
            typical_contract_values TEXT, decision_makers TEXT, payment_history TEXT,
            satisfaction_indicators TEXT, last_updated TEXT, notes TEXT, data_json TEXT
        )'''
        self._execute_query(create_buyers_table, commit=True)
        # Competitor intelligence table
        create_competitors_table = '''
        CREATE TABLE IF NOT EXISTS competitors (
            id TEXT PRIMARY KEY, name TEXT, website TEXT, strengths TEXT, weaknesses TEXT, win_rate REAL,
            typical_bids TEXT, pricing_strategy TEXT, target_sectors TEXT, last_updated TEXT,
            notes TEXT, data_json TEXT
        )'''
        self._execute_query(create_competitors_table, commit=True)
        # Contract award history
        create_contract_awards_table = '''
        CREATE TABLE IF NOT EXISTS contract_awards (
            id TEXT PRIMARY KEY, title TEXT, description TEXT, buyer_id TEXT, buyer_name TEXT,
            winner_id TEXT, winner_name TEXT, award_date TEXT, start_date TEXT, end_date TEXT,
            value REAL, source TEXT, source_url TEXT, data_json TEXT,
            FOREIGN KEY(buyer_id) REFERENCES buyers(id), FOREIGN KEY(winner_id) REFERENCES competitors(id)
        )'''
        self._execute_query(create_contract_awards_table, commit=True)
        # Decision maker profiles
        create_decision_makers_table = '''
        CREATE TABLE IF NOT EXISTS decision_makers (
            id TEXT PRIMARY KEY, name TEXT, title TEXT, organization_id TEXT, organization_name TEXT,
            email TEXT, linkedin_url TEXT, procurement_involvement TEXT, last_updated TEXT,
            notes TEXT, data_json TEXT, FOREIGN KEY(organization_id) REFERENCES buyers(id)
        )'''
        self._execute_query(create_decision_makers_table, commit=True)
        # Strategic intelligence
        create_strategic_intelligence_table = '''
        CREATE TABLE IF NOT EXISTS strategic_intelligence (
            id TEXT PRIMARY KEY, title TEXT, type TEXT, content TEXT, source TEXT, source_url TEXT,
            discovery_date TEXT, expiry_date TEXT, relevance_score REAL, company TEXT, data_json TEXT
        )'''
        self._execute_query(create_strategic_intelligence_table, commit=True)
        logger.info(f"Database initialized/verified at {self.db_path}")


    def save_opportunity(self, opp_data):
        query = '''INSERT OR REPLACE INTO opportunities
                   (id, title, description, source, source_url, estimated_value, estimated_profit_margin,
                    closing_date, discovery_date, buyer_name, buyer_type, headshot_score,
                    profit_probability, win_probability, competition_level, status, company,
                    follow_up_actions, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        params = (
            opp_data.get('id'), opp_data.get('title', 'N/A')[:255], opp_data.get('description', 'N/A')[:2000], # Limit length
            opp_data.get('source', 'N/A'), opp_data.get('source_url', ''), opp_data.get('estimated_value'),
            opp_data.get('estimated_profit_margin'), opp_data.get('closing_date'),
            opp_data.get('discovery_date', datetime.now().isoformat()), opp_data.get('buyer_name', '')[:255], # Limit length
            opp_data.get('buyer_type', ''), opp_data.get('headshot_score', 0),
            opp_data.get('profit_probability', 0), opp_data.get('win_probability', 0),
            opp_data.get('competition_level', 'Unknown'), opp_data.get('status', 'new'),
            opp_data.get('company'), opp_data.get('follow_up_actions', ''),
            json.dumps(opp_data.get('data_json', {}))
        )
        if self._execute_query(query, params, commit=True):
            logger.info(f"Saved/Replaced opportunity: {opp_data.get('title', 'N/A')[:50]}... (Score: {opp_data.get('headshot_score', 0)})")
            return True
        return False

    def save_contract_award(self, award_data):
        query = '''INSERT OR REPLACE INTO contract_awards
                   (id, title, description, buyer_id, buyer_name, winner_id, winner_name,
                    award_date, start_date, end_date, value, source, source_url, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        params = (
            award_data['id'], award_data.get('title', 'N/A')[:255], award_data.get('description', '')[:1000],
            award_data.get('buyer_id', ''), award_data.get('buyer_name', '')[:255],
            award_data.get('winner_id', ''), award_data.get('winner_name', '')[:255],
            award_data.get('award_date', ''), award_data.get('start_date', ''), award_data.get('end_date', ''),
            award_data.get('value'), award_data.get('source', ''), award_data.get('source_url', ''),
            json.dumps(award_data.get('data_json', {}))
        )
        if self._execute_query(query, params, commit=True):
            logger.info(f"Saved/Replaced contract award: {award_data.get('title', 'N/A')[:50]}...")
            return True
        return False

    def save_strategic_intelligence(self, intel_data):
        query = '''INSERT OR REPLACE INTO strategic_intelligence
                   (id, title, type, content, source, source_url, discovery_date, expiry_date,
                    relevance_score, company, data_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        params = (
            intel_data['id'], intel_data['title'][:255], intel_data['type'], intel_data['content'][:2000],
            intel_data['source'], intel_data.get('source_url', ''),
            intel_data.get('discovery_date', datetime.now().isoformat()),
            intel_data.get('expiry_date', (datetime.now() + timedelta(days=90)).isoformat()),
            intel_data.get('relevance_score', 0), intel_data.get('company', ''),
            json.dumps(intel_data.get('data_json', {}))
        )
        if self._execute_query(query, params, commit=True):
            logger.info(f"Saved/Replaced strategic intelligence: {intel_data['title'][:50]}...")
            return True
        return False

    def get_headshot_opportunities(self, company=None, min_score=80, limit=5): # Lowered default min_score for notifications
        query = 'SELECT * FROM opportunities WHERE notification_sent = 0 AND headshot_score >= ?'
        sql_params = [min_score]
        if company:
            query += ' AND company = ?'
            sql_params.append(company)
        query += ' ORDER BY headshot_score DESC LIMIT ?'
        sql_params.append(limit)
        
        rows = self._execute_query(query, tuple(sql_params), fetch_all=True)
        return [dict(row) for row in rows] if rows else []

    def mark_notification_sent(self, opportunity_id):
        query = 'UPDATE opportunities SET notification_sent = 1 WHERE id = ?'
        self._execute_query(query, (opportunity_id,), commit=True)

    def export_opportunities_csv(self, output_file="data/headshot_opportunities.csv"):
        # ... (Keep as is, it was good) ...
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT id, title, description, source, source_url, estimated_value,
               estimated_profit_margin, closing_date, buyer_name, headshot_score,
               profit_probability, win_probability, competition_level, status, company, follow_up_actions
        FROM opportunities ORDER BY headshot_score DESC
        ''') # Added follow_up_actions
        rows = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(column_names)
            csv_writer.writerows(rows)
        conn.close()
        logger.info(f"Exported {len(rows)} opportunities to {output_file}")
        return output_file


# --- HeadshotAgent Class (Major Upgrades) ---
class HeadshotAgent:
    def __init__(self):
        self.db = DatabaseManager()
        self.nlp = NLP_MODEL # Use the globally loaded NLP model
        self.session = requests.Session() # Use a session for potential cookie persistence, connection pooling
        self.session.headers.update({"User-Agent": self.get_random_user_agent()})

        # --- Target Lists (Keep as is or update URLs manually) ---
        self.local_authority_targets = COMPANY_PROFILES_TARGETS_CONFIG.get("local_authority_targets", [])
        self.nhs_targets = COMPANY_PROFILES_TARGETS_CONFIG.get("nhs_targets", [])
        self.housing_association_targets = COMPANY_PROFILES_TARGETS_CONFIG.get("housing_association_targets", [])
        self.premium_sources = COMPANY_PROFILES_TARGETS_CONFIG.get("premium_sources", [])
        # New: RSS Feeds for Competitor News (Examples, find actual feeds)
        self.competitor_news_rss_feeds = {
            "General UK Business News": "http://feeds.bbci.co.uk/news/business/rss.xml",
            "Public Sector News (Example)": "https://www.publictechnology.net/rss.xml",
            # Add more specific industry news RSS feeds if available
        }
        self.common_procurement_paths = ["/procurement", "/tenders", "/contracts", "/supplying", "/working-with-us", "/business/procurement", "/business/tenders-and-contracts"]


    def get_random_user_agent(self):
        return random.choice(USER_AGENTS)

    def request_with_retry(self, url, method="GET", headers=None, data=None, params=None, max_retries=3, base_delay=2, allow_redirects=True, referer_url=None):
        """Upgraded request method with better headers and error logging."""
        current_headers = self.session.headers.copy() # Start with session headers (which includes UA)
        if headers:
            current_headers.update(headers)
        if referer_url: # Add Referer if provided
            current_headers["Referer"] = referer_url

        for attempt in range(max_retries):
            try:
                logger.debug(f"Requesting (Attempt {attempt+1}/{max_retries}): {method} {url} with params {params}")
                response = self.session.request(
                    method=method, url=url, headers=current_headers, data=data, params=params,
                    timeout=30, verify=True, # Keep verify=True for security, handle SSL errors specifically
                    allow_redirects=allow_redirects
                )
                response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
                delay = random.uniform(base_delay, base_delay * 2) # Random delay after success
                logger.debug(f"Request successful, sleeping for {delay:.2f}s")
                time.sleep(delay)
                return response
            except requests.exceptions.SSLError as e:
                logger.error(f"SSL_ERROR :: URL: {url} :: Error: {e}")
                # For specific, known problematic sites, you *could* retry with verify=False, but it's risky.
                # For now, we let it fail for SSL issues.
                break # Don't retry SSL errors usually
            except requests.exceptions.RequestException as e:
                error_type = type(e).__name__
                status_code = e.response.status_code if e.response is not None else "N/A"
                logger.warning(f"REQUEST_FAILED (Attempt {attempt+1}/{max_retries}) :: URL: {url} :: Status: {status_code} :: ErrorType: {error_type} :: Error: {str(e)[:200]}")
                if attempt + 1 < max_retries:
                    sleep_time = (base_delay * 2) * (2 ** attempt) + random.uniform(0,1) # Exponential backoff
                    logger.info(f"Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"WEB_REQUEST_FAILED_PERMANENTLY :: URL: {url} :: After {max_retries} attempts. Last Status: {status_code}, Error: {e}")
                    return None
        return None # Should be unreachable if loop completes, but as a fallback

    def _get_clean_text(self, soup_element):
        """Extracts and cleans text from a BeautifulSoup element."""
        if not soup_element:
            return ""
        # Remove script, style, nav, footer, header before text extraction
        for useless_tag in soup_element.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
            useless_tag.decompose()
        text = soup_element.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text) # Normalize whitespace
        return text

    def _extract_entities_with_spacy(self, text):
        """Uses spaCy to extract ORG, MONEY, DATE, GPE (Locations)."""
        entities = {"organizations": [], "money": [], "dates": [], "locations": []}
        if not self.nlp or not text:
            return entities
        try:
            doc = self.nlp(text[:100000]) # Process up to 100k chars for performance
            for ent in doc.ents:
                if ent.label_ == "ORG":
                    entities["organizations"].append(ent.text.strip())
                elif ent.label_ == "MONEY":
                    entities["money"].append(ent.text.strip())
                elif ent.label_ == "DATE":
                    entities["dates"].append(ent.text.strip())
                elif ent.label_ == "GPE": # Geopolitical Entity (cities, countries)
                    entities["locations"].append(ent.text.strip())
            # Deduplicate
            for key in entities: entities[key] = sorted(list(set(entities[key])))
        except Exception as e:
            logger.error(f"SPACY_ERROR :: Error extracting entities: {e}", exc_info=False) # Keep log concise
        return entities

    # --- extract_headshot_opportunity (Major NLP and Logic Upgrade) ---
    def extract_headshot_opportunity(self, text_content, company_profile_name, source, url, buyer_name_hint=None):
        opp_id_text = url + text_content[:500] # Use URL and some text for ID
        opportunity_id = f"{company_profile_name}-{hashlib.md5(opp_id_text.encode('utf-8')).hexdigest()[:12]}"
        
        company_info = COMPANY_PROFILES.get(company_profile_name, {})
        opportunity = {
            "id": opportunity_id, "source": source, "source_url": url, "company": company_profile_name,
            "discovery_date": datetime.now().isoformat(), "status": "candidate",
            "data_json": {"raw_text_sample": text_content[:2000], "extracted_entities": {}, "scoring_contributors": []}
        }

        if not text_content:
            logger.warning(f"EMPTY_CONTENT :: No text content to analyze for URL: {url}")
            return None # Cannot process empty content

        # 1. NLP Entity Extraction
        extracted_entities = self._extract_entities_with_spacy(text_content)
        opportunity["data_json"]["extracted_entities"] = extracted_entities

        # 2. Title Extraction (Improved)
        # ... (Keep your existing title_patterns or refine, spaCy entities can also hint at titles) ...
        # For brevity, I'll use a simplified version here, but your regex was decent.
        title_match = re.search(r'(?:tender|contract|opportunity|procurement|invitation to quote|ITT)\s+(?:for|of)\s+([^\.\n]{20,150})', text_content, re.I)
        opportunity["title"] = title_match.group(1).strip()[:250] if title_match else f"Potential Opportunity: {source}"

        # 3. Description (Simplified, main content is key)
        opportunity["description"] = text_content[:1500] # Use more of the initial text as description

        # 4. Buyer Name (Prioritize hint, then NLP ORG, then regex)
        if buyer_name_hint:
            opportunity["buyer_name"] = buyer_name_hint
        elif extracted_entities["organizations"]:
            # Try to find a plausible buyer from ORGs (e.g., contains "Council", "NHS", "Authority")
            for org in extracted_entities["organizations"]:
                if any(kw in org.lower() for kw in ["council", "borough", "authority", "nhs", "trust", "government", "department", "commissioning"]):
                    opportunity["buyer_name"] = org
                    break
        if not opportunity.get("buyer_name"): # Regex fallback
            buyer_match = re.search(r"(?:contracting authority|buyer|client|issued by)[:\s]+([^\n\(,]{5,100}\b(?:Council|Authority|NHS Trust|ICB|Ltd|PLC|LLP)\b)", text_content, re.I)
            if buyer_match: opportunity["buyer_name"] = buyer_match.group(1).strip()

        # 5. Estimated Value (Use NLP MONEY first, then regex)
        # ... (Your regex for value was good, spaCy's MONEY entity can help confirm/find)
        # This needs robust parsing of "£1.2 million", "500k" etc. from spaCy's MONEY entities or regex.
        # Simplified for this example:
        if extracted_entities["money"]:
            # A proper parser would convert "£1.2 million" to 1200000
            # For now, just store the first one found by spaCy if regex fails
            val_text = extracted_entities["money"][0]
            # Basic parsing attempt
            try:
                parsed_val = float(re.sub(r'[^\d\.]', '', val_text.split(' ')[0])) # take first number part
                if "million" in val_text.lower() or "m" in val_text.lower(): parsed_val *= 1000000
                elif "thousand" in val_text.lower() or "k" in val_text.lower(): parsed_val *= 1000
                opportunity["estimated_value"] = parsed_val
            except: pass # Fallback to regex
        # (Your value regex was good, integrate it here as fallback if spaCy part is too simple)

        # 6. Closing Date (Use NLP DATE first, then regex)
        # ... (Your date regex was good, spaCy's DATE entity can help)
        # This also needs robust parsing of various date formats from spaCy's DATE entities.
        # Simplified for this example:
        if extracted_entities["dates"]:
            for date_str in extracted_entities["dates"]:
                # Try to parse common date formats, look for "deadline" "closing" nearby
                if any(kw in text_content[max(0, text_content.lower().find(date_str.lower())-30):text_content.lower().find(date_str.lower())+len(date_str)+30].lower() for kw in ["closing", "deadline", "submission by", "return by"]):
                    try:
                        # Add more formats to dateparser or use datetime.strptime with many formats
                        from dateutil import parser # robust date parsing
                        dt_obj = parser.parse(date_str, fuzzy=False) # fuzzy=False for stricter parsing
                        if dt_obj > datetime.now(): # Only future dates for closing
                            opportunity["closing_date"] = dt_obj.isoformat()
                            break
                    except: pass
        # (Your date regex as fallback)


        # --- SCORING LOGIC (Enhanced with weights & NLP context) ---
        headshot_score = 50 # Base score
        opportunity["data_json"]["scoring_contributors"].append(f"Base: {headshot_score}")

        # Negative keywords penalty
        for neg_kw, penalty in NEGATIVE_KEYWORDS.items():
            if neg_kw.lower() in text_content.lower():
                headshot_score += penalty # penalty is negative
                opportunity["data_json"]["scoring_contributors"].append(f"NegativeKW '{neg_kw}': {penalty}")
        
        # Weighted positive keywords
        for kw, weight in KEYWORD_WEIGHTS.items():
            if kw.lower() in text_content.lower():
                headshot_score += weight
                opportunity["data_json"]["scoring_contributors"].append(f"PositiveKW '{kw}': {weight}")

        # Profit & Hidden Signals (keep your existing logic or refine)
        # ...
        profit_signal_count = 0
        for signal in PROFIT_SIGNALS:
            if signal.lower() in text_content.lower():
                profit_signal_count+=1
                opportunity["data_json"].setdefault("profit_signals_found", []).append(signal)
        if profit_signal_count > 0:
            bonus = min(15, profit_signal_count * 3)
            headshot_score += bonus
            opportunity["data_json"]["scoring_contributors"].append(f"ProfitSignals ({profit_signal_count}): +{bonus}")
        
        # Existing Client (Huge boost)
        if opportunity.get("buyer_name") and company_info.get("existing_buyers") and opportunity["buyer_name"] in company_info["existing_buyers"]:
            headshot_score += 20
            opportunity["data_json"]["scoring_contributors"].append("ExistingClient: +20")

        # Value Alignment
        est_val = opportunity.get("estimated_value")
        if est_val and company_info.get("ideal_contract_value_range"):
            ideal_min, ideal_max = company_info["ideal_contract_value_range"]
            if ideal_min <= est_val <= ideal_max:
                headshot_score += 10
                opportunity["data_json"]["scoring_contributors"].append(f"ValueInRange ({est_val:.0f}): +10")
            elif est_val < ideal_min * 0.5 or est_val > ideal_max * 2:
                headshot_score -= 5
                opportunity["data_json"]["scoring_contributors"].append(f"ValueOutOfRange ({est_val:.0f}): -5")

        # Urgency (from text or signals)
        if any(urg_kw in text_content.lower() for urg_kw in ["urgent", "immediate start", "expedited"]):
            headshot_score += 10
            opportunity["data_json"]["scoring_contributors"].append("UrgencyText: +10")

        # Minimum Profit Margin Check (conceptual, margin calculation needs to be robust)
        # ... (Your previous estimated_profit_margin logic can be integrated here) ...
        # if opportunity.get("estimated_profit_margin", 0) < company_info.get("minimum_profit_margin", 10):
        #     headshot_score -= 10
        #     opportunity["data_json"]["scoring_contributors"].append(f"LowMargin: -10")


        opportunity["headshot_score"] = min(100, max(0, round(headshot_score))) # Normalize
        opportunity["status"] = "scored"

        # ... (Your follow_up_actions logic based on score) ...
        # Generate follow-up actions based on score
        score = opportunity["headshot_score"]
        if score >= 85:
            opportunity["follow_up_actions"] = "IMMEDIATE ACTION: Likely HEADSHOT. Verify details, contact buyer if appropriate, prepare to engage."
        elif score >= 70:
            opportunity["follow_up_actions"] = "HIGH PRIORITY: Strong potential. In-depth review, research buyer, prepare qualification."
        elif score >= 50:
            opportunity["follow_up_actions"] = "MEDIUM PRIORITY: Investigate further. Gather more info on requirements and competition."
        else:
            opportunity["follow_up_actions"] = "LOW PRIORITY: Monitor. Consider if strategic or pipeline is light."


        return opportunity


    def _scan_website_for_links(self, base_url, search_terms, company_profile_name, source_name, buyer_name_hint, path_suffixes=None, referer_url=None):
        """Generic helper to scan a base URL (and common paths) for links matching search terms."""
        discovered_opportunities = []
        if path_suffixes is None:
            path_suffixes = [""] # Scan base_url itself if no suffixes

        urls_to_scan = [urljoin(base_url, suffix.strip('/')) for suffix in path_suffixes]
        scanned_page_content = set() # To avoid rescanning identical page content from different URL aliases

        for page_url in urls_to_scan:
            if not page_url.startswith("http"): # Ensure valid URL
                logger.warning(f"INVALID_URL_SCHEME :: Skipping URL: {page_url}")
                continue

            logger.info(f"SCANNING_PAGE :: URL: {page_url} for {source_name}")
            response = self.request_with_retry(page_url, referer_url=referer_url or base_url) # Pass referer
            if not response:
                # Try one common alternative if the direct path failed
                if any(p in page_url for p in self.common_procurement_paths): # Only if it was a common path
                    for alt_suffix in random.sample(self.common_procurement_paths, 2): # Try 2 random alternatives
                        alt_url = urljoin(base_url, alt_suffix.strip('/'))
                        if alt_url != page_url:
                            logger.info(f"RETRY_ALT_PATH :: Original failed, trying: {alt_url}")
                            response = self.request_with_retry(alt_url, referer_url=base_url)
                            if response:
                                page_url = alt_url # Update if successful
                                break # Found one
                if not response:
                    continue # Still no response

            page_content_hash = hashlib.md5(response.text.encode('utf-8')).hexdigest()
            if page_content_hash in scanned_page_content:
                logger.info(f"DUPLICATE_PAGE_CONTENT :: Skipping already processed content from {page_url}")
                continue
            scanned_page_content.add(page_content_hash)

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Option 1: Extract opportunities directly from this page's text
            main_page_text = self._get_clean_text(soup.find('main') or soup.find('article') or soup.body)
            if main_page_text and any(term.lower() in main_page_text.lower() for term in COMPANY_PROFILES[company_profile_name]["keywords"]):
                 if any(st.lower() in main_page_text.lower() for st in search_terms): # "tender", "opportunity"
                    opp = self.extract_headshot_opportunity(main_page_text, company_profile_name, source_name, page_url, buyer_name_hint)
                    if opp and opp.get("headshot_score",0) >= 40: # Lower initial threshold for direct page content
                        self.db.save_opportunity(opp)
                        discovered_opportunities.append(opp)
                        logger.info(f"OPP_FROM_PAGE :: {company_profile_name} from {source_name} ({page_url}) - Score: {opp['headshot_score']}")

            # Option 2: Find links on this page and scan those
            links_found = []
            for link_tag in soup.find_all('a', href=True):
                href = link_tag.get('href', '').strip()
                link_text = link_tag.get_text(strip=True)
                
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                if href.startswith("mailto:"): # Skip mailto links early
                    continue

                full_url = urljoin(page_url, href) # Make absolute

                # Check if link text or URL itself looks like an opportunity
                if any(term.lower() in link_text.lower() for term in search_terms) or \
                   any(term.lower() in href.lower() for term in search_terms):
                    # Avoid crawling too deep or off-site excessively
                    if urlparse(full_url).netloc == urlparse(base_url).netloc or "gov.uk" in full_url or "nhs.uk" in full_url:
                        links_found.append({"url": full_url, "text": link_text, "source_page_url": page_url})
            
            for link_info in links_found[:5]: # Limit linked pages to process
                if link_info["url"] == page_url: continue # Avoid self-loop
                logger.info(f"SCANNING_LINKED_PAGE :: URL: {link_info['url']} (from {link_info['text']})")
                link_response = self.request_with_retry(link_info["url"], referer_url=link_info["source_page_url"])
                if link_response:
                    link_soup = BeautifulSoup(link_response.text, 'html.parser')
                    link_page_text = self._get_clean_text(link_soup.find('main') or link_soup.find('article') or link_soup.body)
                    if link_page_text and any(term.lower() in link_page_text.lower() for term in COMPANY_PROFILES[company_profile_name]["keywords"]):
                        opp = self.extract_headshot_opportunity(link_page_text, company_profile_name, source_name, link_info["url"], buyer_name_hint)
                        if opp and opp.get("headshot_score",0) >= 50:
                            self.db.save_opportunity(opp)
                            discovered_opportunities.append(opp)
                            logger.info(f"OPP_FROM_LINK :: {company_profile_name} from {source_name} ({link_info['url']}) - Score: {opp['headshot_score']}")
        return discovered_opportunities

    def scan_local_authorities(self):
        logger.info("Scanning local authority websites...")
        all_opps = []
        for authority in self.local_authority_targets:
            companies_to_check = ["EzziUK", "RehabilityUK"] if authority["company"] == "both" else [authority["company"]]
            for company_name in companies_to_check:
                opps = self._scan_website_for_links(
                    base_url=authority["url"],
                    search_terms=["tender", "contract", "opportunity", "procurement", "e-tendering", "supplying"],
                    company_profile_name=company_name,
                    source_name=f"Local Authority: {authority['name']}",
                    buyer_name_hint=authority['name'],
                    path_suffixes=self.common_procurement_paths + ["/business", ""] # Check various common paths
                )
                all_opps.extend(opps)
        logger.info(f"Local authority scan discovered {len(all_opps)} potential opportunities.")
        return all_opps

    # ... (scan_nhs_commissioners and scan_housing_associations would use _scan_website_for_links similarly) ...
    def scan_nhs_commissioners(self):
        logger.info("Scanning NHS & care commissioners...")
        all_opps = []
        for nhs_org in self.nhs_targets:
            # NHS sites often use "commissioning", "provider", "services"
            opps = self._scan_website_for_links(
                base_url=nhs_org["url"],
                search_terms=["tender", "contract", "opportunity", "procurement", "commissioning", "services", "provider", "framework"],
                company_profile_name=nhs_org["company"], # Should be "RehabilityUK" mostly
                source_name=f"NHS Org: {nhs_org['name']}",
                buyer_name_hint=nhs_org['name'],
                path_suffixes=self.common_procurement_paths + ["/commissioning-intentions", "/publications", "/about-us/corporate-information", ""]
            )
            all_opps.extend(opps)
             # Also check for strategic plans (simplified for now, more advanced parsing needed for PDFs)
            for strat_suffix in ["/strategies", "/plans", "/publications"]:
                strat_url = urljoin(nhs_org["url"], strat_suffix)
                # ... (logic to find PDF/doc links and extract text or summarize if possible - complex) ...
        logger.info(f"NHS commissioner scan discovered {len(all_opps)} potential opportunities.")
        return all_opps

    def scan_housing_associations(self):
        logger.info("Scanning housing associations...")
        all_opps = []
        for ha in self.housing_association_targets:
            opps = self._scan_website_for_links(
                base_url=ha["url"],
                search_terms=["tender", "contract", "opportunity", "procurement", "works", "maintenance", "development"],
                company_profile_name=ha["company"], # Should be "EzziUK" mostly
                source_name=f"Housing Assoc: {ha['name']}",
                buyer_name_hint=ha['name'],
                path_suffixes=self.common_procurement_paths + ["/development-opportunities", "/news", ""]
            )
            all_opps.extend(opps)
        logger.info(f"Housing association scan discovered {len(all_opps)} potential opportunities.")
        return all_opps

    def scan_premium_frameworks(self): # Uses _scan_website_for_links too
        logger.info("Scanning premium framework websites...")
        all_opps = []
        for source_info in self.premium_sources:
            # Frameworks are relevant to all companies, check keywords
            for company_name in COMPANY_PROFILES.keys():
                opps = self._scan_website_for_links(
                    base_url=source_info["url"],
                    search_terms=["framework", "direct award", "call-off", "dynamic purchasing system", "dps", "opportunities"],
                    company_profile_name=company_name,
                    source_name=f"Premium Framework: {source_info['name']}",
                    buyer_name_hint=source_info['name'], # The framework org itself
                    path_suffixes=["/frameworks", "/opportunities", "/solutions", ""]
                )
                all_opps.extend(opps)
        logger.info(f"Premium framework scan discovered {len(all_opps)} potential opportunities.")
        return all_opps


    # --- scan_competitor_failures (Upgraded with RSS and better Google handling) ---
    def scan_competitor_failures(self):
        logger.info("Scanning for competitor failures (RSS & Google News)...")
        discovered_opportunities = []

        # 1. Scan RSS Feeds
        for feed_name, feed_url in self.competitor_news_rss_feeds.items():
            logger.info(f"COMPETITOR_NEWS_RSS :: Checking feed: {feed_name} ({feed_url})")
            try:
                parsed_feed = feedparser.parse(feed_url)
                for entry in parsed_feed.entries[:20]: # Check last 20 entries
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    link = entry.get("link", "")
                    content_text = f"{title} {summary}"

                    for company_profile_name, profile in COMPANY_PROFILES.items():
                        for competitor in profile.get("competitor_names", []):
                            if competitor.lower() in content_text.lower():
                                for fail_kw in ["fail", "issue", "problem", "cqc", "inadequate", "measures", "terminate", "breach", "scandal"]:
                                    if fail_kw in content_text.lower():
                                        logger.info(f"COMPETITOR_RSS_HIT :: Competitor '{competitor}' mentioned with '{fail_kw}' in RSS feed '{feed_name}' for {company_profile_name}")
                                        opp = self.extract_headshot_opportunity(
                                            self._get_clean_text(BeautifulSoup(entry.get("content", [{}])[0].get("value", summary), 'html.parser')), # Try to get full content
                                            company_profile_name,
                                            f"Competitor Issue (RSS: {feed_name}): {competitor}",
                                            link,
                                            buyer_name_hint=None # Buyer usually unknown from general news
                                        )
                                        if opp:
                                            opp["status"] = "competitor_failure_rss"
                                            opp["headshot_score"] = min(100, opp.get("headshot_score",0) + 20) # Boost for RSS hits
                                            if opp["headshot_score"] >= 60:
                                                self.db.save_opportunity(opp)
                                                discovered_opportunities.append(opp)
                                        break # Found a failure keyword for this competitor
            except Exception as e:
                logger.error(f"COMPETITOR_RSS_ERROR :: Failed to parse RSS feed {feed_url}: {e}")
            time.sleep(random.uniform(3,7)) # Delay between RSS feeds

        # 2. Scan Google News (VERY BRITTLE, use with caution, expect 429s)
        logger.info("COMPETITOR_NEWS_GOOGLE :: Attempting Google News scan (highly rate-limited and fragile).")
        for company_profile_name, profile in COMPANY_PROFILES.items():
            for competitor in profile.get("competitor_names", []):
                failure_terms = [f'"{competitor}" CQC inadequate', f'"{competitor}" contract terminated', f'"{competitor}" service failure', f'"{competitor}" special measures']
                for term in failure_terms:
                    logger.info(f"Searching Google News for: {term} (for {company_profile_name})")
                    # VERY IMPORTANT: Add significant delay to avoid immediate blocking by Google
                    time.sleep(random.uniform(20, 45)) # 20-45 seconds delay

                    search_url = f"https://www.google.com/search?q={quote_plus(term)}&tbm=nws"
                    response = self.request_with_retry(search_url, headers={"User-Agent": self.get_random_user_agent()}) # Fresh UA
                    
                    if response:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        # --- THIS GOOGLE PARSING IS A BEST-EFFORT AND WILL BREAK OFTEN ---
                        # Google actively changes its HTML. These selectors are examples.
                        # Look for common patterns of result blocks.
                        news_results_data = []
                        # Try finding elements that typically wrap a search result link and description
                        # Common patterns: div.g, div.Gx5Zad, div.rc, div.WlydOe, div.Nv2PK (newer)
                        # This list needs to be updated as Google changes.
                        potential_result_blocks = soup.select('div.Gx5Zad, div.g, div.Nv2PK, div.WlydOe, div.xpd, div. સમાચાર') # Added more, including Indic
                        
                        for item_block in potential_result_blocks[:3]: # Process only top 3 to be less aggressive
                            link_tag = item_block.find('a', href=True)
                            if not link_tag or not link_tag['href']:
                                continue

                            url = link_tag['href']
                            if url.startswith("/url?q="): # Google redirect
                                url = unquote(url.split("/url?q=")[1].split("&sa=")[0])
                            elif not url.startswith("http"):
                                continue # Skip if not a full URL

                            # Skip common non-news links
                            if any(skip_domain in url for skip_domain in ["google.com/search", "accounts.google", "support.google"]):
                                continue
                            
                            title_tag = item_block.find(['h3', 'div'], role='heading') or link_tag.find(['h3','div'], recursive=False)
                            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True) or "Untitled News"
                            title = title[:150] # Truncate

                            # Snippet extraction is also very fragile
                            snippet_text = ""
                            snippet_div = item_block.select_one('div[role="text"], div[data-sncf="2"], .GI74Re, .st, .VwiC3b')
                            if snippet_div:
                                snippet_text = snippet_div.get_text(separator=" ", strip=True)
                            else: # Fallback: get text from the block, excluding title
                                all_strings = [s.strip() for s in item_block.find_all(string=True) if s.strip() and s.strip().lower() not in title.lower()]
                                snippet_text = " ".join(all_strings)
                            snippet_text = snippet_text[:300] # Truncate

                            if title and url:
                                news_results_data.append({"title": title, "url": url, "snippet": snippet_text})
                        
                        if not news_results_data:
                             logger.warning(f"GOOGLE_NEWS_EMPTY :: No results or parse error for '{term}'. Google HTML may have changed / CAPTCHA.")

                        for result in news_results_data: # news_results_data replaces news_results
                            logger.info(f"COMPETITOR_GOOGLE_HIT :: Processing article: {result['url']}")
                            # Get full article text (this also needs robust parsing)
                            article_response = self.request_with_retry(result["url"])
                            if article_response:
                                article_soup = BeautifulSoup(article_response.text, 'html.parser')
                                article_text = self._get_clean_text(article_soup.find("article") or article_soup.find("main") or article_soup.body)
                                if article_text:
                                    opp = self.extract_headshot_opportunity(
                                        article_text, company_profile_name,
                                        f"Competitor Issue (Google News): {competitor}",
                                        result["url"], buyer_name_hint=None
                                    )
                                    if opp:
                                        opp["status"] = "competitor_failure_gnews"
                                        opp["headshot_score"] = min(100, opp.get("headshot_score",0) + 25)
                                        opp["data_json"]["competitor_name"] = competitor
                                        opp["data_json"]["news_title"] = result["title"]
                                        if opp["headshot_score"] >= 65:
                                            self.db.save_opportunity(opp)
                                            discovered_opportunities.append(opp)
        logger.info(f"Competitor failure scan complete. Discovered {len(discovered_opportunities)} potential opportunities.")
        return discovered_opportunities

    # --- monitor_contract_award_notices (MAJOR REWRITE TO SIMULATE API USAGE) ---
    def monitor_contract_award_notices(self):
        logger.info("Monitoring contract award notices (Simulating API usage)...")
        awards_found = []
        
        # --- !!! IMPORTANT !!! ---
        # The following simulates using an API. You NEED to replace this with actual
        # API calls to Contracts Finder and Find a Tender (FTS) after researching their documentation.
        # This placeholder will NOT fetch real data.
        # Search for "Contracts Finder API documentation" and "Find a Tender Service API documentation".
        
        api_sources = [
            {
                "name": "Contracts Finder API (Placeholder)",
                "base_url": "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices", # Fictional API endpoint
                "params": {"status": "awarded", "size": 20, "publishedFrom": (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00Z')}
            },
            {
                "name": "Find a Tender API (Placeholder)",
                "base_url": "https://www.find-tender.service.gov.uk/api/1.0/search", # Fictional API endpoint
                "params": {"noticeState": "AWARDED_CONTRACT", "resultsPerPage": 20, "publishedDateFrom": (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}
            }
        ]

        for source in api_sources:
            logger.info(f"API_SIM :: Checking {source['name']}")
            # In a real scenario, you'd make a request here:
            # response = self.request_with_retry(source['base_url'], params=source['params'], headers={"Authorization": "Bearer YOUR_API_KEY_IF_NEEDED"})
            # For now, we'll simulate a response structure.
            
            # --- SIMULATED API RESPONSE (REPLACE WITH ACTUAL API CALL AND PARSING) ---
            simulated_api_data = []
            if "Contracts Finder" in source['name']: # Simulate CF-like data
                for i in range(random.randint(0,3)): # Simulate 0 to 3 awards
                    simulated_api_data.append({
                        "id": f"cf-sim-{random.randint(10000,99999)}",
                        "title": f"Simulated CF Award Title {i+1} - {random.choice(['Services', 'Goods', 'Works'])}",
                        "description": f"This is a simulated description for a contract awarded via Contracts Finder. Buyer: Simulated Council {chr(65+i)}. Winner: Simulated Winner Ltd {i+1}.",
                        "buyer": {"name": f"Simulated Council {chr(65+i)}"},
                        "suppliers": [{"name": f"Simulated Winner Ltd {i+1}"}],
                        "publicationDate": (datetime.now() - timedelta(days=random.randint(1,7))).isoformat(),
                        "awardValue": {"amount": random.uniform(50000, 2000000)},
                        "links": {"self": {"href": f"https://www.contractsfinder.service.gov.uk/simulated-notice/{random.randint(1000,9999)}"}}
                    })
            elif "Find a Tender" in source['name']: # Simulate FTS-like data
                 for i in range(random.randint(0,2)):
                    simulated_api_data.append({
                        "documentId": f"fts-sim-{random.randint(10000,99999)}",
                        "title": f"Simulated FTS Award: {random.choice(['Framework', 'Contract'])} {i+1}",
                        "summary": f"Summary of FTS awarded notice. Buyer is NHS Simulated Trust {chr(88+i)}, and the winner is Another Winner PLC {i+1}.",
                        "contractingAuthority": {"name": f"NHS Simulated Trust {chr(88+i)}"},
                        "awardedSupplier": {"name": f"Another Winner PLC {i+1}"},
                        "publicationDate": (datetime.now() - timedelta(days=random.randint(1,7))).strftime('%Y-%m-%d'),
                        "estimatedValue": {"netAmount": random.uniform(100000, 5000000)},
                        "url": f"https://www.find-tender.service.gov.uk/simulated-notice/{random.randint(1000,9999)}"
                    })
            # --- END SIMULATED API RESPONSE ---

            if not simulated_api_data: # if response and response.status_code == 200: api_response_json = response.json() else: continue
                logger.info(f"API_SIM :: No new awards found (or simulated) from {source['name']}.")
                continue
            
            # Actual parsing would depend on the real API's JSON structure
            for item in simulated_api_data: # api_response_json.get('releases', []) or api_response_json.get('results', [])
                try:
                    award_details = {}
                    if "Contracts Finder" in source['name']:
                        award_details = {
                            "id": item.get("id", f"cf-award-{hashlib.md5(item.get('links', {}).get('self', {}).get('href','').encode()).hexdigest()[:12]}"),
                            "title": item.get("title"),
                            "description": item.get("description"),
                            "buyer_name": item.get("buyer", {}).get("name"),
                            "winner_name": item.get("suppliers", [{}])[0].get("name") if item.get("suppliers") else None,
                            "award_date": item.get("publicationDate"), # or a specific awardDate field
                            "value": item.get("awardValue", {}).get("amount"),
                            "source_url": item.get("links", {}).get("self", {}).get("href")
                        }
                    elif "Find a Tender" in source['name']:
                        award_details = {
                            "id": item.get("documentId", f"fts-award-{hashlib.md5(item.get('url','').encode()).hexdigest()[:12]}"),
                            "title": item.get("title"),
                            "description": item.get("summary"), # FTS has summary
                            "buyer_name": item.get("contractingAuthority", {}).get("name"),
                            "winner_name": item.get("awardedSupplier", {}).get("name"),
                            "award_date": item.get("publicationDate"),
                            "value": item.get("estimatedValue",{}).get("netAmount"), # FTS uses estimatedValue
                            "source_url": item.get("url")
                        }
                    
                    if award_details.get("buyer_name") and award_details.get("winner_name") and award_details.get("value") is not None:
                        award_data = {
                            "id": award_details["id"], "title": award_details["title"],
                            "description": award_details["description"], "buyer_name": award_details["buyer_name"],
                            "winner_name": award_details["winner_name"], "award_date": award_details["award_date"],
                            "value": award_details["value"], "source": source['name'].replace(" (Placeholder)",""),
                            "source_url": award_details["source_url"], "data_json": {"api_item": item} # Store raw API item
                        }
                        self.db.save_contract_award(award_data)
                        awards_found.append(award_data)
                    else:
                        logger.warning(f"API_SIM_INCOMPLETE_DATA :: Skipping item from {source['name']} due to missing key fields: {item.get('id') or item.get('documentId')}")
                except Exception as e_item:
                    logger.error(f"API_PARSE_ERROR :: Error processing item from {source['name']}: {e_item} :: Item: {str(item)[:200]}...")
        
        logger.info(f"Contract award monitoring (API Sim) complete. Found {len(awards_found)} 'awards'.")
        return awards_found


    # ... (get_buyer_patterns, _extract_buyer_preferences, _is_buyer_likely_to_procure_soon, _predict_next_procurement_month remain largely the same,
    #      but _extract_buyer_preferences could also be enhanced with spaCy for noun phrase chunking)

    # --- send_headshot_notifications (Minor enhancements for clarity) ---
    def send_headshot_notifications(self):
        # ... (Keep your existing send_headshot_notifications logic. It was good.
        #      Maybe add the "scoring_contributors" to the Discord message if space allows, or top 3.)
        # One small addition:
        # Inside the loop for opp in opportunities:
        #   embed_description += f"\n**Key Score Drivers:** {', '.join(opp.get('data_json',{}).get('scoring_contributors',[])[:3])}"
        # This would add the top 3 reasons for the score to the Discord message.
        # For brevity, I'm not pasting the whole method again.
        if not DISCORD_WEBHOOK:
            logger.warning("DISCORD_WEBHOOK not set. Skipping notifications.")
            return False
        
        any_notified = False
        for company_name in COMPANY_PROFILES.keys():
            opportunities = self.db.get_headshot_opportunities(company=company_name, min_score=75, limit=5) # Slightly lower threshold for notification
            if not opportunities:
                logger.info(f"No new high-score opportunities for {company_name} to notify.")
                continue

            embeds = []
            for opp in opportunities:
                # ... (your existing embed creation logic from previous version)
                # Simplified for brevity, but use your full embed logic
                score = opp.get('headshot_score', 0)
                color = 0xFF0000 if score >= 90 else (0xFF6600 if score >= 85 else 0xFFCC00)
                
                desc_parts = [opp.get('description', 'N/A')[:400] + "..."]
                # Add scoring contributors to description
                contributors = opp.get('data_json', {}).get('scoring_contributors', [])
                if contributors:
                    desc_parts.append(f"\n**Score Insights:** {'; '.join(contributors[:3])}") # Top 3 reasons

                embed = {
                    "title": f"🎯 HEADSHOT: {opp.get('title', 'N/A')[:100]} (Score: {score})",
                    "description": "\n".join(desc_parts),
                    "url": opp.get('source_url'), "color": color,
                    "fields": [
                        {"name": "Buyer", "value": opp.get('buyer_name', 'N/A'), "inline": True},
                        {"name": "Est. Value", "value": f"£{opp.get('estimated_value', 0):,.0f}" if opp.get('estimated_value') else 'N/A', "inline": True},
                        {"name": "Actions", "value": opp.get('follow_up_actions', 'Review')[:1000], "inline": False} # Limit action length
                    ],
                    "footer": {"text": f"Source: {opp.get('source', 'N/A')} | ID: {opp.get('id')}"},
                    "timestamp": datetime.utcnow().isoformat() + "Z" # Ensure UTC for Discord
                }
                embeds.append(embed)

            if embeds:
                payload = {"content": f"🔥 **Top HEADSHOT Opportunities for {company_name}!** 🔥", "embeds": embeds[:10]} # Discord limit 10 embeds
                try:
                    response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
                    response.raise_for_status()
                    logger.info(f"DISCORD_SENT :: Successfully sent {len(embeds)} opportunity notifications for {company_name}.")
                    for opp_notified in opportunities: self.db.mark_notification_sent(opp_notified["id"])
                    any_notified = True
                except requests.RequestException as e:
                    logger.error(f"DISCORD_ERROR :: Failed to send notification for {company_name}: {e}")
        return any_notified


    def run_headshot_scan(self):
        logger.info("🎯 ADVANCED HEADSHOT SCAN INITIATED 🎯")
        all_opportunities_discovered_count = 0 # Track count from direct scans

        # Use ThreadPoolExecutor for I/O-bound scanning tasks
        with ThreadPoolExecutor(max_workers=4) as executor: # Reduced workers slightly
            future_to_scan = {
                executor.submit(self.scan_local_authorities): "Local Authorities",
                executor.submit(self.scan_nhs_commissioners): "NHS Commissioners",
                executor.submit(self.scan_housing_associations): "Housing Associations",
                executor.submit(self.scan_premium_frameworks): "Premium Frameworks",
                executor.submit(self.scan_competitor_failures): "Competitor Failures (RSS/Google)"
            }
            for future in as_completed(future_to_scan):
                scan_name = future_to_scan[future]
                try:
                    results = future.result() # List of opportunities
                    if results: # It should return a list
                        all_opportunities_discovered_count += len(results)
                    logger.info(f"SCAN_COMPLETE :: {scan_name} scan finished, found {len(results) if results else 0} direct opportunities.")
                except Exception as e:
                    logger.error(f"SCAN_TASK_ERROR :: Error in {scan_name} scan: {e}", exc_info=True) # exc_info for traceback

        # Sequential: Contract Award Monitoring and Pattern Analysis (uses API sim)
        try:
            logger.info("Starting contract award monitoring and pattern analysis...")
            awards = self.monitor_contract_award_notices() # This now simulates API
            if awards:
                self.get_buyer_patterns(awards) # This can also create opportunities in DB
            logger.info("Contract award and pattern analysis complete.")
        except Exception as e:
            logger.error(f"AWARD_PATTERN_ERROR :: {e}", exc_info=True)

        # Notifications and Export
        self.send_headshot_notifications()
        self.db.export_opportunities_csv()

        logger.info(f"🎯 ADVANCED HEADSHOT SCAN COMPLETE. Initial direct discoveries: {all_opportunities_discovered_count}.")
        # Note: total impact includes predicted opps, strategic intel, etc., visible in DB/notifications.

# --- Helper for config (keeps main script cleaner) ---
COMPANY_PROFILES_TARGETS_CONFIG = {
    "local_authority_targets": [
        {"name": "London Borough of Hackney", "url": "https://hackney.gov.uk/", "company": "EzziUK"},
        {"name": "London Borough of Camden", "url": "https://www.camden.gov.uk/", "company": "RehabilityUK"},
        # ... Add all your other local_authority_targets here ...
        {"name": "Brighton & Hove Council", "url": "https://www.brighton-hove.gov.uk/", "company": "RehabilityUK"}
    ],
    "nhs_targets": [
        {"name": "NHS England", "url": "https://www.england.nhs.uk/", "company": "RehabilityUK"},
        # ... Add all your nhs_targets ...
        {"name": "NHS Leeds ICB", "url": "https://www.leedsccg.nhs.uk/", "company": "RehabilityUK"} # URL might be outdated
    ],
    "housing_association_targets": [
        {"name": "Clarion Housing Group", "url": "https://www.clarionhg.com/", "company": "EzziUK"},
        # ... Add all your housing_association_targets ...
        {"name": "Home Group", "url": "https://www.homegroup.org.uk/", "company": "EzziUK"}
    ],
    "premium_sources": [
        {"name": "Crown Commercial Service", "url": "https://www.crowncommercial.gov.uk/"},
        # ... Add all your premium_sources ...
        {"name": "NHS Commercial Solutions", "url": "https://commercialsolutions-sec.nhs.uk/"} # Had DNS issues
    ]
}


def main():
    if NLP_MODEL is None:
        logger.critical("CRITICAL: SpaCy NLP model failed to load. Key functionalities will be impaired. Please run 'python -m spacy download en_core_web_sm'")
        # Decide if you want to exit or continue with reduced functionality
        # return # Exit if NLP is absolutely critical
    
    agent = HeadshotAgent()
    agent.run_headshot_scan()

if __name__ == "__main__":
    main()
