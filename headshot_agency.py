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
from urllib.parse import urljoin, quote_plus
from collections import defaultdict, Counter # Added Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HEADSHOT")

# Database path
DATABASE_PATH = "data/headshot_vault.db"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # Used for higher API limits

# User agent rotation for avoiding detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36"
]

# Company Profiles - Highly detailed for precision targeting
COMPANY_PROFILES = {
    "EzziUK": {
        "name": "EzziUK",
        "services": [
            "social housing solutions", "rent guarantee schemes", "landlord services",
            "property management for social housing", "tenant placement",
            "housing maintenance", "lettings management"
        ],
        "target_sectors": [
            "housing associations", "local authorities", "councils",
            "government housing departments", "NHS trust accommodation"
        ],
        "keywords": [
            "social housing", "HMO", "guaranteed rent", "lettings", "landlord",
            "property management", "housing association", "local authority housing",
            "supported living accommodation", "affordable housing", "temporary accommodation"
        ],
        "geographic_focus": ["London", "Birmingham", "Manchester", "Leeds", "Sheffield", "Bristol"],
        "ideal_contract_duration": "3-5 years",
        "ideal_contract_value_range": (100000, 5000000),  # £100K to £5M
        "competitor_names": [
            "Mears Group", "Pinnacle Group", "Places for People", "Civitas Housing",
            "Home Group", "Sanctuary Housing", "Clarion Housing", "L&Q"
        ],
        "contract_success_signals": [
            "housing renewal", "management outsourcing", "housing stock transfer",
            "property portfolio expansion", "maintenance contract renewal",
            "urgent housing need", "temporary accommodation requirements"
        ],
        "existing_buyers": [
            "London Borough of Hackney", "Birmingham City Council", "Manchester City Council",
            "Leeds Housing Options", "Sheffield Housing Services"
        ],
        "buyer_decision_makers": {
            "role_titles": ["Head of Housing", "Director of Housing", "Procurement Manager",
                           "Housing Options Manager", "Social Housing Lead"]
        },
        "minimum_profit_margin": 15  # 15% gross margin requirement
    },
    "RehabilityUK": {
        "name": "RehabilityUK",
        "services": [
            "supported living services", "domiciliary care", "complex care packages",
            "mental health support services", "learning disability services",
            "autism specialist care", "respite care"
        ],
        "target_sectors": [
            "NHS", "Clinical Commissioning Groups", "local authority social care",
            "health trusts", "private healthcare groups"
        ],
        "keywords": [
            "supported living", "care services", "domiciliary care", "NHS CCG",
            "local authority social care", "mental health", "learning disabilities",
            "autism care", "tender care", "framework agreement care", "CQC registered"
        ],
        "geographic_focus": ["London", "Birmingham", "Manchester", "Liverpool", "Newcastle", "Edinburgh"],
        "ideal_contract_duration": "2-4 years",
        "ideal_contract_value_range": (200000, 3000000),  # £200K to £3M
        "competitor_names": [
            "Dimensions UK", "Care UK", "HC-One", "Voyage Care", "Lifeways Group",
            "Turning Point", "The Priory Group", "Exemplar Health Care"
        ],
        "contract_success_signals": [
            "care provider failure", "service quality issues", "commissioner dissatisfaction",
            "CQC improvement requirements", "urgent care needs", "hospital discharge targets",
            "delayed transfer of care", "integration of health and social care"
        ],
        "existing_buyers": [
            "NHS England", "London Borough of Camden", "Birmingham Adult Social Care",
            "Manchester Health and Care Commissioning", "NHS Highland"
        ],
        "buyer_decision_makers": {
            "role_titles": ["Commissioning Manager", "Head of Adult Social Care", "CCG Procurement Lead",
                           "Director of Social Services", "Care Quality Lead"]
        },
        "minimum_profit_margin": 18  # 18% gross margin requirement
    }
}

# Market signals that indicate high-profit potential
PROFIT_SIGNALS = [
    # Staffing and operational issues
    "staff shortages", "service disruption", "operational challenges",
    "recruitment difficulties", "staffing crisis", "capacity issues",
    "emergency provision", "service failure", "intervention required",

    # Financial distress
    "financial difficulties", "budget pressure", "budget shortfall",
    "cost saving requirements", "efficiency targets", "funding gap",
    "tender republication", "contract rebid", "emergency procurement",

    # Timeline pressure
    "urgent requirement", "expedited procurement", "immediate need",
    "deadline extension", "rapid deployment", "immediate start",

    # Quality issues
    "quality concerns", "CQC report", "improvement required",
    "service rating decline", "performance issues", "compliance failure",

    # Special requirements
    "specialized provider", "niche requirement", "complex needs",
    "specific expertise", "technical requirement"
]

# Hidden opportunity signals - these indicate contracts that might not be widely competed for
HIDDEN_OPPORTUNITY_SIGNALS = [
    # Procedural indicators
    "direct award potential", "limited competition", "prior information notice",
    "reduced procedure", "specialist requirement", "incumbency challenge",
    "framework mini-competition", "call-off potential", "DPS opportunity",

    # Low visibility indicators
    "low response expected", "limited market interest", "niche service area",
    "challenging requirements", "limited market supply", "specialist only",

    # Rapid/emergency procurement
    "expedited procurement", "streamlined process", "urgent need",
    "accelerated procedure", "emergency provision",

    # Geographic/access limitations
    "specific geographic requirement", "limited provider pool",
    "remote location", "challenging location", "accessibility issues"
]

class DatabaseManager:
    """Advanced database manager for opportunity tracking and analysis"""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """Create the database and tables with comprehensive structure"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Primary opportunities table - comprehensive structure
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            source TEXT,
            source_url TEXT,
            estimated_value REAL,
            estimated_profit_margin REAL,
            closing_date TEXT,
            discovery_date TEXT,
            buyer_name TEXT,
            buyer_type TEXT,
            headshot_score REAL,
            profit_probability REAL,
            win_probability REAL,
            competition_level TEXT,
            status TEXT,
            company TEXT,
            notification_sent INTEGER DEFAULT 0,
            analysis_complete INTEGER DEFAULT 0,
            follow_up_actions TEXT,
            data_json TEXT
        )
        ''')

        # Buyer intelligence table - track info about potential clients
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS buyers (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            region TEXT,
            website TEXT,
            procurement_approach TEXT,
            typical_contract_values TEXT,
            decision_makers TEXT,
            payment_history TEXT,
            satisfaction_indicators TEXT,
            last_updated TEXT,
            notes TEXT,
            data_json TEXT
        )
        ''')

        # Competitor intelligence table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS competitors (
            id TEXT PRIMARY KEY,
            name TEXT,
            website TEXT,
            strengths TEXT,
            weaknesses TEXT,
            win_rate REAL,
            typical_bids TEXT,
            pricing_strategy TEXT,
            target_sectors TEXT,
            last_updated TEXT,
            notes TEXT,
            data_json TEXT
        )
        ''')

        # Contract award history - to build patterns and predictions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contract_awards (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            buyer_id TEXT,
            buyer_name TEXT,
            winner_id TEXT,
            winner_name TEXT,
            award_date TEXT,
            start_date TEXT,
            end_date TEXT,
            value REAL,
            source TEXT,
            source_url TEXT,
            data_json TEXT,
            FOREIGN KEY(buyer_id) REFERENCES buyers(id),
            FOREIGN KEY(winner_id) REFERENCES competitors(id)
        )
        ''')

        # Decision maker profiles - for targeting specific individuals
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS decision_makers (
            id TEXT PRIMARY KEY,
            name TEXT,
            title TEXT,
            organization_id TEXT,
            organization_name TEXT,
            email TEXT,
            linkedin_url TEXT,
            procurement_involvement TEXT,
            last_updated TEXT,
            notes TEXT,
            data_json TEXT,
            FOREIGN KEY(organization_id) REFERENCES buyers(id)
        )
        ''')

        # Strategic intelligence - broader market movements
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS strategic_intelligence (
            id TEXT PRIMARY KEY,
            title TEXT,
            type TEXT,
            content TEXT,
            source TEXT,
            source_url TEXT,
            discovery_date TEXT,
            expiry_date TEXT,
            relevance_score REAL,
            company TEXT,
            data_json TEXT
        )
        ''')

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def save_opportunity(self, opportunity_data):
        """Save a headshot opportunity to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
            INSERT OR REPLACE INTO opportunities
            (id, title, description, source, source_url, estimated_value, estimated_profit_margin,
            closing_date, discovery_date, buyer_name, buyer_type, headshot_score,
            profit_probability, win_probability, competition_level, status, company,
            follow_up_actions, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                opportunity_data['id'],
                opportunity_data['title'],
                opportunity_data['description'],
                opportunity_data['source'],
                opportunity_data.get('source_url', ''),
                opportunity_data.get('estimated_value', 0),
                opportunity_data.get('estimated_profit_margin', 0),
                opportunity_data.get('closing_date'),
                opportunity_data.get('discovery_date', datetime.now().isoformat()),
                opportunity_data.get('buyer_name', ''),
                opportunity_data.get('buyer_type', ''),
                opportunity_data.get('headshot_score', 0),
                opportunity_data.get('profit_probability', 0),
                opportunity_data.get('win_probability', 0),
                opportunity_data.get('competition_level', 'Unknown'),
                opportunity_data.get('status', 'new'),
                opportunity_data.get('company'),
                opportunity_data.get('follow_up_actions', ''),
                json.dumps(opportunity_data.get('data_json', {}))
            ))

            conn.commit()
            logger.info(f"Saved headshot opportunity: {opportunity_data['title']} (Score: {opportunity_data.get('headshot_score', 0)})")
            return True

        except Exception as e:
            logger.error(f"Error saving opportunity: {e}")
            return False
        finally:
            conn.close()

    def save_buyer(self, buyer_data):
        """Save buyer intelligence to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
            INSERT OR REPLACE INTO buyers
            (id, name, type, region, website, procurement_approach, typical_contract_values,
            decision_makers, payment_history, satisfaction_indicators, last_updated, notes, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                buyer_data['id'],
                buyer_data['name'],
                buyer_data.get('type', ''),
                buyer_data.get('region', ''),
                buyer_data.get('website', ''),
                buyer_data.get('procurement_approach', ''),
                buyer_data.get('typical_contract_values', ''),
                buyer_data.get('decision_makers', ''),
                buyer_data.get('payment_history', ''),
                buyer_data.get('satisfaction_indicators', ''),
                datetime.now().isoformat(),
                buyer_data.get('notes', ''),
                json.dumps(buyer_data.get('data_json', {}))
            ))

            conn.commit()
            logger.info(f"Saved buyer intelligence: {buyer_data['name']}")
            return True

        except Exception as e:
            logger.error(f"Error saving buyer: {e}")
            return False
        finally:
            conn.close()

    def save_contract_award(self, award_data):
        """Save contract award information to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
            INSERT OR REPLACE INTO contract_awards
            (id, title, description, buyer_id, buyer_name, winner_id, winner_name,
            award_date, start_date, end_date, value, source, source_url, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                award_data['id'],
                award_data['title'],
                award_data.get('description', ''),
                award_data.get('buyer_id', ''),
                award_data.get('buyer_name', ''),
                award_data.get('winner_id', ''),
                award_data.get('winner_name', ''),
                award_data.get('award_date', ''),
                award_data.get('start_date', ''),
                award_data.get('end_date', ''),
                award_data.get('value', 0),
                award_data.get('source', ''),
                award_data.get('source_url', ''),
                json.dumps(award_data.get('data_json', {}))
            ))

            conn.commit()
            logger.info(f"Saved contract award: {award_data['title']} - Winner: {award_data.get('winner_name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Error saving contract award: {e}")
            return False
        finally:
            conn.close()

    def save_strategic_intelligence(self, intel_data):
        """Save strategic market intelligence to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
            INSERT OR REPLACE INTO strategic_intelligence
            (id, title, type, content, source, source_url, discovery_date, expiry_date,
            relevance_score, company, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                intel_data['id'],
                intel_data['title'],
                intel_data['type'],
                intel_data['content'],
                intel_data['source'],
                intel_data.get('source_url', ''),
                intel_data.get('discovery_date', datetime.now().isoformat()),
                intel_data.get('expiry_date', (datetime.now() + timedelta(days=90)).isoformat()),
                intel_data.get('relevance_score', 0),
                intel_data.get('company', ''),
                json.dumps(intel_data.get('data_json', {}))
            ))

            conn.commit()
            logger.info(f"Saved strategic intelligence: {intel_data['title']}")
            return True

        except Exception as e:
            logger.error(f"Error saving strategic intelligence: {e}")
            return False
        finally:
            conn.close()

    def get_headshot_opportunities(self, company=None, min_score=85, limit=5):
        """Get headshot opportunities with high scores that haven't been notified yet"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = '''
        SELECT * FROM opportunities
        WHERE notification_sent = 0
        AND headshot_score >= ?
        '''

        params = [min_score]
        if company:
            query += " AND company = ?"
            params.append(company)

        query += f" ORDER BY headshot_score DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def mark_notification_sent(self, opportunity_id):
        """Mark an opportunity as having been notified"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        UPDATE opportunities
        SET notification_sent = 1
        WHERE id = ?
        ''', (opportunity_id,))

        conn.commit()
        conn.close()

    def get_buyer_by_name(self, buyer_name):
        """Get buyer information by name"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT * FROM buyers
        WHERE name LIKE ?
        ''', (f"%{buyer_name}%",))

        result = cursor.fetchone()
        conn.close()

        return dict(result) if result else None

    def get_competitor_awards(self, competitor_name, limit=20):
        """Get recent contract awards for a competitor"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT * FROM contract_awards
        WHERE winner_name LIKE ?
        ORDER BY award_date DESC
        LIMIT ?
        ''', (f"%{competitor_name}%", limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def get_buyer_contracts(self, buyer_name, limit=20):
        """Get recent contracts from a specific buyer"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT * FROM contract_awards
        WHERE buyer_name LIKE ?
        ORDER BY award_date DESC
        LIMIT ?
        ''', (f"%{buyer_name}%", limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def get_active_buyers(self, num_months=6, limit=10):
        """Get the most active buyers in recent months"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=30*num_months)).isoformat()

        cursor.execute('''
        SELECT buyer_name, COUNT(*) as award_count, SUM(value) as total_value
        FROM contract_awards
        WHERE award_date > ?
        GROUP BY buyer_name
        ORDER BY award_count DESC
        LIMIT ?
        ''', (cutoff_date, limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def export_opportunities_csv(self, output_file="data/headshot_opportunities.csv"):
        """Export opportunities to CSV for external analysis"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
        SELECT
            id, title, description, source, source_url, estimated_value,
            estimated_profit_margin, closing_date, buyer_name, headshot_score,
            profit_probability, win_probability, competition_level, status, company
        FROM opportunities
        ORDER BY headshot_score DESC
        ''')

        rows = cursor.fetchall()

        # Get column names
        column_names = [description[0] for description in cursor.description]

        # Write to CSV
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as csv_file: # Added encoding
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(column_names)
            csv_writer.writerows(rows)

        conn.close()
        logger.info(f"Exported {len(rows)} opportunities to {output_file}")

        return output_file


class HeadshotAgent:
    """Elite opportunity hunter for finding guaranteed profit contracts"""

    def __init__(self):
        """Initialize the Headshot Agent"""
        self.db = DatabaseManager()

        # Strategic Intelligence Sources
        self.strategic_sources = [
            # Procurement policy and strategy
            {"name": "UK Government Procurement", "url": "https://www.gov.uk/government/organisations/crown-commercial-service"},
            {"name": "NHS England Procurement", "url": "https://www.england.nhs.uk/commissioning/"},
            {"name": "Cabinet Office Procurement", "url": "https://www.gov.uk/government/organisations/cabinet-office"},

            # Social housing policy and strategy
            {"name": "National Housing Federation", "url": "https://www.housing.org.uk/"},
            {"name": "Chartered Institute of Housing", "url": "https://www.cih.org/"},
            {"name": "Inside Housing", "url": "https://www.insidehousing.co.uk/"},

            # Health and social care policy and strategy
            {"name": "Care Quality Commission", "url": "https://www.cqc.org.uk/"},
            {"name": "NHS Providers", "url": "https://nhsproviders.org/"},
            {"name": "Skills for Care", "url": "https://www.skillsforcare.org.uk/"},

            # Local government
            {"name": "Local Government Association", "url": "https://www.local.gov.uk/"},
            {"name": "Municipal Journal", "url": "https://www.themj.co.uk/"},
            {"name": "LocalGov", "url": "https://www.localgov.co.uk/"}
        ]

        # Local authority targets - focus on key locations
        self.local_authority_targets = [
            # London
            {"name": "London Borough of Hackney", "url": "https://hackney.gov.uk/", "company": "EzziUK"},
            {"name": "London Borough of Camden", "url": "https://www.camden.gov.uk/", "company": "RehabilityUK"},
            {"name": "London Borough of Lambeth", "url": "https://www.lambeth.gov.uk/", "company": "EzziUK"},

            # Midlands
            {"name": "Birmingham City Council", "url": "https://www.birmingham.gov.uk/", "company": "both"},
            {"name": "Leicester City Council", "url": "https://www.leicester.gov.uk/", "company": "RehabilityUK"},
            {"name": "Nottingham City Council", "url": "https://www.nottinghamcity.gov.uk/", "company": "EzziUK"},

            # North
            {"name": "Manchester City Council", "url": "https://www.manchester.gov.uk/", "company": "both"},
            {"name": "Leeds City Council", "url": "https://www.leeds.gov.uk/", "company": "EzziUK"},
            {"name": "Liverpool City Council", "url": "https://www.liverpool.gov.uk/", "company": "RehabilityUK"},

            # South/East
            {"name": "Bristol City Council", "url": "https://www.bristol.gov.uk/", "company": "EzziUK"},
            {"name": "Brighton & Hove Council", "url": "https://www.brighton-hove.gov.uk/", "company": "RehabilityUK"}
        ]

        # NHS and care commissioning targets
        self.nhs_targets = [
            {"name": "NHS England", "url": "https://www.england.nhs.uk/", "company": "RehabilityUK"},
            {"name": "NHS North London Partners", "url": "https://northlondonpartners.org.uk/", "company": "RehabilityUK"},
            {"name": "NHS Birmingham and Solihull ICB", "url": "https://www.birminghamsolihull.icb.nhs.uk/", "company": "RehabilityUK"},
            {"name": "NHS Greater Manchester ICB", "url": "https://www.gmintegratedcare.org.uk/", "company": "RehabilityUK"},
            {"name": "NHS Leeds ICB", "url": "https://www.leedsccg.nhs.uk/", "company": "RehabilityUK"} # Note: CCGs are now ICBs, URL might need update
        ]

        # Housing association targets
        self.housing_association_targets = [
            {"name": "Clarion Housing Group", "url": "https://www.clarionhg.com/", "company": "EzziUK"},
            {"name": "L&Q", "url": "https://www.lqgroup.org.uk/", "company": "EzziUK"},
            {"name": "Sanctuary Housing", "url": "https://www.sanctuary.co.uk/", "company": "EzziUK"},
            {"name": "Peabody", "url": "https://www.peabody.org.uk/", "company": "EzziUK"},
            {"name": "Home Group", "url": "https://www.homegroup.org.uk/", "company": "EzziUK"}
        ]

        # Advanced search signals - these are powerful contract identifiers
        self.company_signals = {
            "EzziUK": [
                "housing crisis", "temporary accommodation shortage", "emergency housing need",
                "housing provider failure", "landlord compliance issues", "housing management issues",
                "void property management", "housing disrepair", "housing maintenance backlog",
                "homeless placement", "housing procurement failure", "failed housing procurement",
                "housing association merger", "social housing transfer", "temporary accommodation overspend"
            ],
            "RehabilityUK": [
                "care provider failure", "CQC inadequate rating", "special measures care",
                "safeguarding concerns", "care quality issues", "hospital discharge delays",
                "care staff shortage", "learning disability provision failure", "mental health service gap",
                "care provider insolvency", "care framework emergency", "complex care shortage",
                "autism service gap", "complex needs provision", "care market failure"
            ]
        }

        # Premium opportunity sources (where high-value contracts appear first)
        self.premium_sources = [
            # Direct award frameworks
            {"name": "Crown Commercial Service", "url": "https://www.crowncommercial.gov.uk/"},
            {"name": "NHS Shared Business Services", "url": "https://www.sbs.nhs.uk/"},
            {"name": "ESPO", "url": "https://www.espo.org/"},

            # Prior information notices
            {"name": "Tenders Electronic Daily", "url": "https://ted.europa.eu/TED/browse/browseByBO.do"}, # UK might use Find a Tender more now

            # Framework opportunites
            {"name": "London Housing Consortium", "url": "https://lhc.gov.uk/"},
            {"name": "Northern Housing Consortium", "url": "https://www.northern-consortium.org.uk/"},
            {"name": "NHS Commercial Solutions", "url": "https://commercialsolutions-sec.nhs.uk/"}
        ]

    def get_random_user_agent(self):
        """Get a random user agent to avoid detection"""
        return random.choice(USER_AGENTS)

    def request_with_retry(self, url, method="GET", headers=None, data=None, max_retries=3):
        """Make an HTTP request with retry logic and rotation of user agents"""
        if headers is None:
            headers = {"User-Agent": self.get_random_user_agent()}
        else: # Ensure User-Agent is present if custom headers are passed
            if "User-Agent" not in headers:
                 headers["User-Agent"] = self.get_random_user_agent()


        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=30
                )
                response.raise_for_status()

                # Respect rate limits - random delay between 1-3 seconds
                time.sleep(random.uniform(1, 3))

                return response
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt+1}/{max_retries}): {url} - {e}")
                if attempt + 1 < max_retries:
                    sleep_time = 2 ** attempt  # Exponential backoff
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed after {max_retries} attempts: {url}")
                    return None

    def extract_headshot_opportunity(self, text, company, source, url, buyer_name=None):
        """
        Extract a headshot opportunity using advanced pattern matching and profit probability
        This is the core intelligence function that identifies guaranteed profit opportunities
        """
        # Create a unique ID based on content
        content_hash = hashlib.md5(text.encode('utf-8')).hexdigest() # Added encoding
        opportunity_id = f"{company}-{content_hash[:12]}"

        # Initialize opportunity data structure
        opportunity = {
            "id": opportunity_id,
            "source": source,
            "source_url": url,
            "company": company,
            "discovery_date": datetime.now().isoformat(),
            "status": "headshot_candidate",
            "buyer_name": buyer_name,
            "data_json": {
                "raw_text": text[:5000]  # Store first 5000 chars of raw text
            }
        }

        # Extract title - look for key phrases indicating a tender or opportunity
        title_patterns = [
            r'(?:tender|contract|opportunity|procurement|callout)\s+for\s+([^\.\n]+)', # Changed from [^\.]+ to allow more chars
            r'(?:invitation|call)\s+to\s+(?:tender|bid)\s+for\s+([^\.\n]+)',
            r'(?:seeking|looking for|request for)\s+(?:providers|proposals|quotations|bids)\s+(?:for)?\s+([^\.\n]+)',
            r'procurement\s+of\s+([^\.\n]+)',
            r'commission(?:ing)?\s+(?:of)?\s+([^\.\n]+)'
        ]

        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                opportunity["title"] = match.group(1).strip()[:255] # Limit title length
                break

        if "title" not in opportunity:
            # Fallback - use first sentence that mentions relevant keywords
            sentences = re.split(r'[.!?]\s+', text)
            company_keywords = COMPANY_PROFILES[company]["keywords"]

            for sentence in sentences:
                if any(keyword.lower() in sentence.lower() for keyword in company_keywords):
                    opportunity["title"] = sentence.strip()[:100]
                    if len(opportunity["title"]) < 20 and sentences.index(sentence) < len(sentences)-1:  # If title is too short, add more context
                         opportunity["title"] += "..." + sentences[sentences.index(sentence)+1].strip()[:50]
                    break

        if "title" not in opportunity:
            # If still no title, use generic title with buyer name if available
            if buyer_name:
                opportunity["title"] = f"Potential opportunity with {buyer_name}"
            else:
                opportunity["title"] = f"Potential opportunity from {source}"
        opportunity["title"] = opportunity.get("title", "Untitled Opportunity")[:255] # Ensure title exists and limit length

        # Extract description - focus on the most relevant section
        text_lower = text.lower()

        # Define markers that typically precede the meat of a contract description
        description_markers = [
            "scope of", "specification", "description of", "overview of",
            "we are seeking", "the authority requires", "service requirement",
            "contract description", "background", "summary of requirement"
        ]

        # Find the start of the most relevant description section
        description_start = 0
        for marker in description_markers:
            pos = text_lower.find(marker)
            if pos > -1:
                description_start = pos
                break

        # Extract a reasonable description length
        description_text = text[description_start:description_start + 1000]
        if len(description_text) < 100 and description_start > 0:
            # If description is too short, use more of the original text
            description_text = text[:1000]

        opportunity["description"] = description_text

        # Extract estimated value
        value_patterns = [
            r'(?:value|worth|budget|fund(?:ing)?|cost)(?:\s+is|\s+of)?\s+(?:approximately|approx|around|about|up to|at least)?\s*(?:£|\$|€|GBP|USD|EUR)?\s*(\d[\d,\.]*\s*(?:million|m|k|thousand)?)', # Added \$
            r'(?:£|\$|€|GBP|USD|EUR)\s*(\d[\d,\.]*\s*(?:million|m|k|thousand)?)',
            r'(\d[\d,\.]*\s*(?:million|m|k|thousand)?)(?:\s+pounds|\s+sterling)?',
            r'contract value(?:d)?\s+(?:at|of)?\s+(?:£|\$|€|GBP|USD|EUR)?\s*(\d[\d,\.]*\s*(?:million|m|k|thousand)?)'
        ]

        for pattern in value_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_text = match.group(1).strip().lower()
                try:
                    # Remove commas
                    value_text = value_text.replace(',', '')

                    # Handle 'million', 'm', 'k', 'thousand'
                    multiplier = 1
                    if 'million' in value_text or (value_text.endswith('m') and not value_text.endswith('pm')): # avoid month
                        multiplier = 1000000
                        value_text = value_text.replace('million', '').replace('m', '')
                    elif 'thousand' in value_text or (value_text.endswith('k') and not value_text.endswith('uk')): # avoid uk
                        multiplier = 1000
                        value_text = value_text.replace('thousand', '').replace('k', '')

                    # Convert to float and apply multiplier
                    value_text = re.sub(r'[^\d\.]', '', value_text) # Clean non-numeric except dot
                    if value_text:
                        value = float(value_text) * multiplier
                        opportunity["estimated_value"] = value
                        break
                except Exception as e:
                    logger.debug(f"Error parsing value {value_text}: {e}")

        # Extract closing date
        date_patterns = [
            r'(?:closing|deadline|submission)\s+date\s+(?:is|of)?\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{2,4})', # Added optional comma, dot
            r'(?:closes|submissions due|deadline)\s+(?:on|by)?\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*\d{2,4})',
            r'(?:closing|deadline|submission)[^0-9]*?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', # Made it non-greedy before date
            r'(?:return by|submit by)[^0-9]*?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})'
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_text = match.group(1)
                try:
                    # Try various date formats
                    date_formats = [
                        "%d %B %Y", "%d %b %Y", "%d %B, %Y", "%d %b, %Y",
                        "%d/%m/%Y", "%d/%m/%y",
                        "%d.%m.%Y", "%d.%m.%y",
                        "%d-%m-%Y", "%d-%m-%y"
                    ]

                    closing_date = None
                    # Remove ordinal indicators (st, nd, rd, th) and any trailing dots
                    clean_date_text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text).replace('.','')

                    for fmt in date_formats:
                        try:
                            closing_date = datetime.strptime(clean_date_text.strip(), fmt)
                            break
                        except ValueError:
                            continue

                    if closing_date:
                        opportunity["closing_date"] = closing_date.isoformat()
                        break
                except Exception as e:
                    logger.debug(f"Error parsing date {date_text}: {e}")
                    # If parsing fails, just store the raw text
                    opportunity["data_json"]["closing_date_text"] = date_text # Store in data_json
        # Calculate estimated profit margin based on company profile
        if "estimated_value" in opportunity:
            value = opportunity["estimated_value"]

            # Base margin on contract value tier
            if value >= 1000000:  # £1M+
                base_margin = 0.12  # 12% base margin for large contracts
            elif value >= 500000:  # £500K+
                base_margin = 0.15  # 15% base margin for medium-large contracts
            elif value >= 100000:  # £100K+
                base_margin = 0.18  # 18% base margin for medium contracts
            else:
                base_margin = 0.20  # 20% base margin for smaller contracts

            # Adjust margin based on competition signals
            competition_signals = [
                "competitive tender", "open procedure", "multiple providers",
                "market testing", "value testing", "price competition"
            ]

            margin_adjustment = 0
            for signal in competition_signals:
                if signal.lower() in text_lower:
                    margin_adjustment -= 0.01  # Reduce margin for each competition signal

            # Adjust margin based on urgency signals (which often allow higher margins)
            urgency_signals = [
                "urgent requirement", "immediate start", "emergency procurement",
                "critical service", "expedited process", "exceptional circumstances"
            ]

            for signal in urgency_signals:
                if signal.lower() in text_lower:
                    margin_adjustment += 0.02  # Increase margin for each urgency signal

            # Adjust margin based on complexity signals (which often allow higher margins)
            complexity_signals = [
                "complex needs", "specialist provision", "niche requirement",
                "highly specialized", "technical requirement", "unique solution"
            ]

            for signal in complexity_signals:
                if signal.lower() in text_lower:
                    margin_adjustment += 0.015  # Increase margin for each complexity signal

            # Calculate final margin with adjustments
            final_margin = base_margin + margin_adjustment

            # Ensure within reasonable bounds
            final_margin = max(0.08, min(0.30, final_margin))  # Cap between 8% and 30%

            opportunity["estimated_profit_margin"] = round(final_margin * 100, 1)  # Store as percentage
            opportunity["data_json"]["margin_calculation"] = {
                "base_margin": base_margin * 100,
                "competition_adjustment": margin_adjustment * 100, # This was missing the "*100"
                "final_margin": final_margin * 100
            }

        # Determine competition level
        competition_level = "Medium"  # Default

        low_competition_signals = [
            "direct award", "single supplier", "limited market",
            "specialist only", "niche provider", "limited competition"
        ]

        high_competition_signals = [
            "highly competitive", "many providers", "competitive market",
            "multiple bidders", "significant interest", "market testing"
        ]

        if any(signal.lower() in text_lower for signal in low_competition_signals):
            competition_level = "Low"
        elif any(signal.lower() in text_lower for signal in high_competition_signals):
            competition_level = "High"

        opportunity["competition_level"] = competition_level

        # Calculate probability of profit
        profit_probability = 0.5  # Default 50%

        # Adjust based on competition level
        if competition_level == "Low":
            profit_probability += 0.2
        elif competition_level == "High":
            profit_probability -= 0.1

        # Adjust based on profit signals
        for signal in PROFIT_SIGNALS:
            if signal.lower() in text_lower:
                profit_probability += 0.05  # Each profit signal increases probability
                opportunity["data_json"].setdefault("profit_signals", []).append(signal)

        # Adjust based on hidden opportunity signals
        for signal in HIDDEN_OPPORTUNITY_SIGNALS:
            if signal.lower() in text_lower:
                profit_probability += 0.07  # Each hidden opportunity signal increases probability
                opportunity["data_json"].setdefault("hidden_signals", []).append(signal)

        # Adjust based on company-specific contract success signals
        for signal in COMPANY_PROFILES[company].get("contract_success_signals", []):
            if signal.lower() in text_lower:
                profit_probability += 0.08  # Company-specific signals are even stronger indicators
                opportunity["data_json"].setdefault("success_signals", []).append(signal)

        # Adjust based on whether the buyer is an existing client
        if buyer_name and buyer_name in COMPANY_PROFILES[company].get("existing_buyers", []):
            profit_probability += 0.15  # Existing relationships significantly increase profit probability
            opportunity["data_json"]["existing_client"] = True

        # Adjust probability for contract value range alignment
        if "estimated_value" in opportunity:
            value = opportunity["estimated_value"]
            ideal_min, ideal_max = COMPANY_PROFILES[company].get("ideal_contract_value_range", (0, float('inf')))

            if ideal_min <= value <= ideal_max:
                profit_probability += 0.1  # Value is in the ideal range
            elif value < ideal_min * 0.5 or value > ideal_max * 1.5:
                profit_probability -= 0.1  # Value is significantly outside ideal range

        # Cap probability between 0.1 and 0.95
        profit_probability = max(0.1, min(0.95, profit_probability))
        opportunity["profit_probability"] = round(profit_probability * 100, 1)  # Store as percentage

        # Calculate win probability (different from profit probability)
        win_probability = 0.3  # Default 30%

        # Adjust based on buyer relationship
        if buyer_name:
            if buyer_name in COMPANY_PROFILES[company].get("existing_buyers", []):
                win_probability += 0.3  # Existing client relationship is a major factor

        # Adjust based on geographic focus
        geo_focus = COMPANY_PROFILES[company].get("geographic_focus", [])
        geo_match = any(location.lower() in text_lower for location in geo_focus)
        if geo_match:
            win_probability += 0.1

        # Adjust based on competition level
        if competition_level == "Low":
            win_probability += 0.15
        elif competition_level == "High":
            win_probability -= 0.1

        # Cap win probability
        win_probability = max(0.05, min(0.9, win_probability))
        opportunity["win_probability"] = round(win_probability * 100, 1)  # Store as percentage

        # Calculate the HEADSHOT score - this is the core of our targeting system
        # A score of 85+ is considered a headshot opportunity (virtually guaranteed profit)

        # Start with base scores from profit and win probabilities
        headshot_score = (opportunity.get("profit_probability", 0) * 0.6) + (opportunity.get("win_probability", 0) * 0.4)

        # Bonus points for each headshot indicator
        bonus_points = 0

        # 1. Profit margin bonus (max +15 points to base score, not direct addition to headshot_score yet)
        if "estimated_profit_margin" in opportunity:
            margin = opportunity["estimated_profit_margin"]
            min_margin = COMPANY_PROFILES[company].get("minimum_profit_margin", 10)

            if margin >= min_margin * 1.5:  # 50% above minimum margin
                bonus_points += 15
            elif margin >= min_margin * 1.2:  # 20% above minimum margin
                bonus_points += 10
            elif margin >= min_margin:  # At or above minimum margin
                bonus_points += 5

        # 2. Urgent/emergency procurement bonus (max +20)
        urgent_terms = [
            "urgent", "emergency", "expedited", "immediate requirement",
            "critical need", "rapid deployment", "priority procurement"
        ]
        urgent_count = sum(1 for term in urgent_terms if term.lower() in text_lower)
        bonus_points += min(20, urgent_count * 5)  # Up to +20 points

        # 3. Existing client bonus (max +15)
        if buyer_name and buyer_name in COMPANY_PROFILES[company].get("existing_buyers", []):
            bonus_points += 15

        # 4. Success signal bonus (max +15)
        success_signal_count = len(opportunity.get("data_json", {}).get("success_signals", []))
        bonus_points += min(15, success_signal_count * 3)

        # 5. Hidden opportunity bonus (max +15)
        hidden_signal_count = len(opportunity.get("data_json", {}).get("hidden_signals", []))
        bonus_points += min(15, hidden_signal_count * 3)

        # Add bonus points to score
        # The original calculation adds `bonus_points * 0.2` to a score already in 0-100.
        # This means max `(15+20+15+15+15)*0.2 = 80*0.2 = 16` bonus to headshot_score.
        # Let's keep it as is, but it's a bit unusual.
        headshot_score += bonus_points * 0.2

        # Normalize score to 0-100
        headshot_score = min(100, max(0, headshot_score))
        opportunity["headshot_score"] = round(headshot_score, 1)

        # Generate follow-up actions based on score
        if headshot_score >= 85:
            follow_up = "IMMEDIATE ACTION: Contact procurement team directly. Request pre-market engagement. Review historical tender documents and pricing."
        elif headshot_score >= 70:
            follow_up = "HIGH PRIORITY: Contact buyer to discuss requirements. Research previous similar contracts and prepare key qualification materials."
        elif headshot_score >= 50:
            follow_up = "INVESTIGATE FURTHER: Gather more information on requirements and buyer needs. Evaluate resources needed for competitive bid."
        else:
            follow_up = "MONITOR: Track but low priority. Consider only if pipeline is light or if strategic value exists."

        opportunity["follow_up_actions"] = follow_up

        return opportunity

    def scan_local_authorities(self):
        """Scan local authority websites for headshot opportunities"""
        logger.info("Scanning local authority websites for headshot opportunities...")
        discovered_opportunities = []

        for authority in self.local_authority_targets:
            name = authority["name"]
            url = authority["url"]
            target_company = authority["company"]

            logger.info(f"Scanning {name} for opportunities...")

            try:
                # First check main procurement/contracts page if we can identify it
                procurement_urls = [
                    f"{url.rstrip('/')}/procurement",
                    f"{url.rstrip('/')}/contracts",
                    f"{url.rstrip('/')}/tenders",
                    f"{url.rstrip('/')}/business/procurement",
                    f"{url.rstrip('/')}/business/tenders",
                    f"{url.rstrip('/')}/business/supplying",
                    f"{url.rstrip('/')}/business/opportunities"
                ]

                scanned_any = False
                for proc_url in procurement_urls:
                    response = self.request_with_retry(proc_url)
                    if response:
                        logger.info(f"Found procurement page for {name}: {proc_url}")
                        scanned_any = True

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Look for tender links or opportunity listings
                        tender_links = []
                        for link_tag in soup.find_all('a', href=True): # Ensure href exists
                            href = link_tag.get('href')
                            text = link_tag.get_text()

                            if not text: # No need to check href again
                                continue

                            # Check if link looks like a tender/contract opportunity
                            if any(term in text.lower() for term in ["tender", "contract", "opportunity", "procurement"]):
                                url_path = urljoin(proc_url, href)
                                tender_links.append({"url": url_path, "text": text})

                        # Process found tender links
                        for link_data in tender_links[:5]:  # Process top 5 from each authority
                            tender_response = self.request_with_retry(link_data["url"])
                            if not tender_response:
                                continue

                            tender_soup = BeautifulSoup(tender_response.text, 'html.parser')

                            # Extract main content
                            main_content = tender_soup.find('main') or \
                                           tender_soup.find('article') or \
                                           tender_soup.find('div', {'class': ['content', 'main-content', 'main', 'page-content']}) # Added 'page-content'

                            if main_content:
                                content_text = main_content.get_text(' ', strip=True)
                            else:
                                # Fallback to body text without navigation and footer
                                for element_to_remove in tender_soup.find_all(['nav', 'footer', 'header', 'script', 'style']): # Added script, style
                                    element_to_remove.decompose()
                                if tender_soup.body:
                                    content_text = tender_soup.body.get_text(' ', strip=True)
                                else:
                                    content_text = tender_soup.get_text(' ', strip=True)


                            # Process for each relevant company
                            companies_to_check = []
                            if target_company == "both":
                                companies_to_check = ["EzziUK", "RehabilityUK"]
                            else:
                                companies_to_check = [target_company]

                            for company_name_iter in companies_to_check:
                                # Check if the tender text contains keywords relevant to the company
                                company_keywords = COMPANY_PROFILES[company_name_iter]["keywords"]
                                if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                    # Extract headshot opportunity
                                    opportunity = self.extract_headshot_opportunity(
                                        content_text,
                                        company_name_iter,
                                        f"Local Authority: {name}",
                                        link_data["url"],
                                        buyer_name=name
                                    )

                                    # Only save high-scoring opportunities
                                    if opportunity["headshot_score"] >= 50:
                                        self.db.save_opportunity(opportunity)
                                        discovered_opportunities.append(opportunity)
                                        logger.info(f"Discovered headshot opportunity for {company_name_iter} from {name} - Score: {opportunity['headshot_score']}")

                if not scanned_any:
                    # If no procurement pages found, scan main site for procurement terms
                    logger.info(f"No specific procurement page found for {name}, scanning main site {url}...")
                    response = self.request_with_retry(url)
                    if response:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        content_text = soup.get_text(' ', strip=True)

                        # Look for procurement terms on main page
                        if any(term in content_text.lower() for term in ["tender", "contract", "procurement", "supplier", "commission"]):
                            # Process for relevant companies
                            companies_to_check = []
                            if target_company == "both":
                                companies_to_check = ["EzziUK", "RehabilityUK"]
                            else:
                                companies_to_check = [target_company]

                            for company_name_iter in companies_to_check:
                                company_keywords = COMPANY_PROFILES[company_name_iter]["keywords"]
                                if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                    opportunity = self.extract_headshot_opportunity(
                                        content_text,
                                        company_name_iter,
                                        f"Local Authority: {name}",
                                        url,
                                        buyer_name=name
                                    )

                                    if opportunity["headshot_score"] >= 70:  # Higher threshold for main page content
                                        self.db.save_opportunity(opportunity)
                                        discovered_opportunities.append(opportunity)
                                        logger.info(f"Discovered potential headshot opportunity from {name} main page - Score: {opportunity['headshot_score']}")

            except Exception as e:
                logger.error(f"Error scanning {name} ({url}): {e}", exc_info=True) # Added exc_info

        logger.info(f"Local authority scan complete. Discovered {len(discovered_opportunities)} headshot opportunities")
        return discovered_opportunities

    def scan_nhs_commissioners(self):
        """Scan NHS commissioners for care contract opportunities"""
        logger.info("Scanning NHS and care commissioners for headshot opportunities...")
        discovered_opportunities = []

        for nhs_org in self.nhs_targets:
            name = nhs_org["name"]
            url = nhs_org["url"]
            company = nhs_org["company"] # This is the target_company (e.g. RehabilityUK)

            logger.info(f"Scanning {name} for opportunities...")

            try:
                # Identify potential procurement pages
                procurement_urls = [
                    f"{url.rstrip('/')}/commissioning",
                    f"{url.rstrip('/')}/procurement",
                    f"{url.rstrip('/')}/working-with-us",
                    f"{url.rstrip('/')}/tenders",
                    f"{url.rstrip('/')}/contracts",
                    f"{url.rstrip('/')}/provider-opportunities",
                    f"{url.rstrip('/')}/get-involved/providers"
                ]

                scanned_any = False
                for proc_url in procurement_urls:
                    response = self.request_with_retry(proc_url)
                    if response:
                        logger.info(f"Found procurement page for {name}: {proc_url}")
                        scanned_any = True

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Look for opportunity links
                        opportunity_links = []
                        for link_tag in soup.find_all('a', href=True):
                            href = link_tag.get('href')
                            text = link_tag.get_text()

                            if not text:
                                continue

                            # Check if link looks like a procurement opportunity
                            procurement_terms = ["tender", "contract", "opportunity", "procurement",
                                              "commission", "provider", "service", "care"]
                            if any(term in text.lower() for term in procurement_terms):
                                url_path = urljoin(proc_url, href)
                                opportunity_links.append({"url": url_path, "text": text})

                        # Process found opportunity links
                        for link_data in opportunity_links[:5]:  # Process top 5 from each source
                            opp_response = self.request_with_retry(link_data["url"])
                            if not opp_response:
                                continue

                            opp_soup = BeautifulSoup(opp_response.text, 'html.parser')

                            # Extract main content
                            main_content = opp_soup.find('main') or \
                                           opp_soup.find('article') or \
                                           opp_soup.find('div', {'class': ['content', 'main-content', 'main', 'page-content']})

                            if main_content:
                                content_text = main_content.get_text(' ', strip=True)
                            else:
                                for element_to_remove in opp_soup.find_all(['nav', 'footer', 'header', 'script', 'style']):
                                    element_to_remove.decompose()
                                if opp_soup.body:
                                    content_text = opp_soup.body.get_text(' ', strip=True)
                                else:
                                    content_text = opp_soup.get_text(' ', strip=True)


                            # Check if the opportunity text contains keywords relevant to the company
                            company_keywords = COMPANY_PROFILES[company]["keywords"]
                            if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                # Extract headshot opportunity
                                opportunity = self.extract_headshot_opportunity(
                                    content_text,
                                    company,
                                    f"NHS Commissioner: {name}",
                                    link_data["url"],
                                    buyer_name=name
                                )

                                # Only save high-scoring opportunities
                                if opportunity["headshot_score"] >= 50:
                                    self.db.save_opportunity(opportunity)
                                    discovered_opportunities.append(opportunity)
                                    logger.info(f"Discovered headshot opportunity from {name} - Score: {opportunity['headshot_score']}")

                # Also check for commissioner strategic plans - these often reveal future contracts
                strategic_urls = [
                    f"{url.rstrip('/')}/strategies",
                    f"{url.rstrip('/')}/plans",
                    f"{url.rstrip('/')}/publications",
                    f"{url.rstrip('/')}/about-us/plans"
                ]

                for strat_url in strategic_urls:
                    response = self.request_with_retry(strat_url)
                    if response:
                        logger.info(f"Found strategic page for {name}: {strat_url}")

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Look for strategic document links
                        doc_links = []
                        for link_tag in soup.find_all('a', href=True):
                            href = link_tag.get('href')
                            text = link_tag.get_text()

                            if not text:
                                continue

                            # Check if link looks like a strategic document
                            strategic_terms = ["strategy", "plan", "commissioning intentions",
                                           "market position", "future commissioning"]
                            if any(term in text.lower() for term in strategic_terms) and (href.endswith('.pdf') or href.endswith('.doc') or href.endswith('.docx')):
                                url_path = urljoin(strat_url, href)
                                doc_links.append({"url": url_path, "text": text})

                        # Process found strategic documents
                        for link_data in doc_links[:3]:  # Process top 3 strategic documents
                            # Note: Parsing PDF/DOC directly is complex and not implemented here.
                            # This part currently assumes the linked page is HTML or text is extractable.
                            # For actual PDF/DOC, you'd need libraries like PyPDF2, python-docx
                            doc_response = self.request_with_retry(link_data["url"])
                            if not doc_response:
                                continue

                            # Basic text extraction assuming it might be an HTML page linking to a doc, or simple text
                            # A proper implementation would try to download and parse the doc if it's a direct file link
                            doc_soup = BeautifulSoup(doc_response.text, 'html.parser')
                            content_text = doc_soup.get_text(' ', strip=True) # This will be limited for actual doc files

                            # Check for relevant keywords
                            company_keywords = COMPANY_PROFILES[company]["keywords"]
                            if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                # Create strategic intelligence item
                                intel_id = f"strategic-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

                                intel_item = {
                                    "id": intel_id,
                                    "title": f"Strategic Document: {link_data['text']}",
                                    "type": "commissioning_strategy",
                                    "content": f"Strategic commissioning document from {name} that may indicate future procurement intentions. Preview: {content_text[:500]}", # Added preview
                                    "source": f"NHS Strategy: {name}",
                                    "source_url": link_data["url"],
                                    "discovery_date": datetime.now().isoformat(),
                                    "relevance_score": 80,  # High relevance for strategic documents
                                    "company": company, # This should be the target company like "RehabilityUK"
                                    "data_json": {
                                        "raw_text_sample": content_text[:2000]
                                    }
                                }

                                self.db.save_strategic_intelligence(intel_item)
                                logger.info(f"Saved strategic intelligence from {name}: {link_data['text']}")

                                # Also check for specific mentions of future procurement
                                future_terms = ["future tender", "upcoming procurement", "planned commission",
                                             "will be procured", "contract renewal"]

                                if any(term in content_text.lower() for term in future_terms):
                                    # This is a strong signal of future procurement - create special opportunity
                                    opportunity = self.extract_headshot_opportunity(
                                        content_text,
                                        company, # This is the target company
                                        f"Future NHS Opportunity: {name}",
                                        link_data["url"],
                                        buyer_name=name
                                    )

                                    # Adjust headshot score for future opportunities
                                    opportunity["headshot_score"] = min(100, opportunity["headshot_score"] + 15)  # Bonus for pre-procurement knowledge
                                    opportunity["status"] = "future_opportunity"

                                    if opportunity["headshot_score"] >= 60:  # Lower threshold for future opportunities
                                        self.db.save_opportunity(opportunity)
                                        discovered_opportunities.append(opportunity)
                                        logger.info(f"Discovered future headshot opportunity from {name} - Score: {opportunity['headshot_score']}")

                if not scanned_any:
                    # If no specific pages found, check main site
                    logger.info(f"No specific procurement pages found for {name}, checking main site {url}...")
                    response = self.request_with_retry(url)
                    if response:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        content_text = soup.get_text(' ', strip=True)

                        # Quick check for relevant terms
                        if any(term in content_text.lower() for term in ["commission", "procurement", "provider", "tender"]):
                            company_keywords = COMPANY_PROFILES[company]["keywords"]
                            if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                opportunity = self.extract_headshot_opportunity(
                                    content_text,
                                    company, # Target company
                                    f"NHS Commissioner: {name}",
                                    url,
                                    buyer_name=name
                                )

                                if opportunity["headshot_score"] >= 70:  # Higher threshold for main page content
                                    self.db.save_opportunity(opportunity)
                                    discovered_opportunities.append(opportunity)
                                    logger.info(f"Discovered potential headshot opportunity from {name} main page - Score: {opportunity['headshot_score']}")

            except Exception as e:
                logger.error(f"Error scanning {name} ({url}): {e}", exc_info=True)

        logger.info(f"NHS commissioner scan complete. Discovered {len(discovered_opportunities)} headshot opportunities")
        return discovered_opportunities

    def scan_housing_associations(self):
        """Scan housing association sites for opportunities relevant to EzziUK"""
        logger.info("Scanning housing associations for headshot opportunities...")
        discovered_opportunities = []

        for ha in self.housing_association_targets:
            name = ha["name"]
            url = ha["url"]
            company = ha["company"] # Target company, e.g. "EzziUK"

            logger.info(f"Scanning {name} for opportunities...")

            try:
                # Look for procurement or business pages
                procurement_urls = [
                    f"{url.rstrip('/')}/procurement",
                    f"{url.rstrip('/')}/suppliers",
                    f"{url.rstrip('/')}/for-businesses",
                    f"{url.rstrip('/')}/working-with-us",
                    f"{url.rstrip('/')}/partnerships"
                ]

                scanned_any = False
                for proc_url in procurement_urls:
                    response = self.request_with_retry(proc_url)
                    if response:
                        logger.info(f"Found business page for {name}: {proc_url}")
                        scanned_any = True

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Look for opportunity links
                        opportunity_links = []
                        for link_tag in soup.find_all('a', href=True):
                            href = link_tag.get('href')
                            text = link_tag.get_text()

                            if not text:
                                continue

                            # Check if link looks like a procurement opportunity
                            procurement_terms = ["tender", "contract", "opportunity", "procurement",
                                              "works", "repairs", "maintenance", "housing management"]
                            if any(term in text.lower() for term in procurement_terms):
                                url_path = urljoin(proc_url, href)
                                opportunity_links.append({"url": url_path, "text": text})

                        # Process found links
                        for link_data in opportunity_links[:5]:  # Process top 5 from each source
                            opp_response = self.request_with_retry(link_data["url"])
                            if not opp_response:
                                continue

                            opp_soup = BeautifulSoup(opp_response.text, 'html.parser')

                            # Extract main content
                            main_content = opp_soup.find('main') or \
                                           opp_soup.find('article') or \
                                           opp_soup.find('div', {'class': ['content', 'main-content', 'main', 'page-content']})

                            if main_content:
                                content_text = main_content.get_text(' ', strip=True)
                            else:
                                for element_to_remove in opp_soup.find_all(['nav', 'footer', 'header', 'script', 'style']):
                                    element_to_remove.decompose()
                                if opp_soup.body:
                                    content_text = opp_soup.body.get_text(' ', strip=True)
                                else:
                                    content_text = opp_soup.get_text(' ', strip=True)


                            # Check if content contains keywords relevant to the company
                            company_keywords = COMPANY_PROFILES[company]["keywords"]
                            if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                # Extract headshot opportunity
                                opportunity = self.extract_headshot_opportunity(
                                    content_text,
                                    company, # Target company
                                    f"Housing Association: {name}",
                                    link_data["url"],
                                    buyer_name=name
                                )

                                # Only save high-scoring opportunities
                                if opportunity["headshot_score"] >= 50:
                                    self.db.save_opportunity(opportunity)
                                    discovered_opportunities.append(opportunity)
                                    logger.info(f"Discovered headshot opportunity from {name} - Score: {opportunity['headshot_score']}")

                # Also check news section for strategic changes (e.g., mergers, new development plans)
                news_urls = [
                    f"{url.rstrip('/')}/news",
                    f"{url.rstrip('/')}/media",
                    f"{url.rstrip('/')}/press-releases",
                    f"{url.rstrip('/')}/whats-new", # Corrected typo
                    f"{url.rstrip('/')}/latest"
                ]

                for news_url in news_urls:
                    response = self.request_with_retry(news_url)
                    if response:
                        logger.info(f"Found news page for {name}: {news_url}")

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Look for strategic change news
                        news_links = []
                        for link_tag in soup.find_all('a', href=True):
                            href = link_tag.get('href')
                            text = link_tag.get_text()

                            if not text:
                                continue

                            # Check if link looks like relevant news
                            strategic_terms = ["merger", "acquisition", "development", "expansion",
                                           "new homes", "investment", "partnership", "framework"]
                            if any(term in text.lower() for term in strategic_terms):
                                url_path = urljoin(news_url, href)
                                news_links.append({"url": url_path, "text": text})

                        # Process found news links
                        for link_data in news_links[:5]:  # Process top 5 news items
                            news_response = self.request_with_retry(link_data["url"])
                            if not news_response:
                                continue

                            news_soup = BeautifulSoup(news_response.text, 'html.parser')
                            for element_to_remove in news_soup.find_all(['nav', 'footer', 'header', 'script', 'style']): # Clean up
                                element_to_remove.decompose()
                            if news_soup.body:
                                content_text = news_soup.body.get_text(' ', strip=True)
                            else:
                                content_text = news_soup.get_text(' ', strip=True)


                            # Check for opportunity signals in news
                            opportunity_signals = ["procurement", "tender", "contract", "supplier", "provider"]
                            if any(signal in content_text.lower() for signal in opportunity_signals):
                                # Check if content contains keywords relevant to the company
                                company_keywords = COMPANY_PROFILES[company]["keywords"]
                                if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                    # Extract headshot opportunity
                                    opportunity = self.extract_headshot_opportunity(
                                        content_text,
                                        company, # Target company
                                        f"Housing Association News: {name}",
                                        link_data["url"],
                                        buyer_name=name
                                    )

                                    # Adjust score for news-derived opportunities
                                    opportunity["headshot_score"] = min(100, opportunity["headshot_score"] + 10)  # Bonus for news intelligence
                                    opportunity["status"] = "news_derived"

                                    if opportunity["headshot_score"] >= 60:  # Lower threshold for news-derived opportunities
                                        self.db.save_opportunity(opportunity)
                                        discovered_opportunities.append(opportunity)
                                        logger.info(f"Discovered news-derived headshot opportunity from {name} - Score: {opportunity['headshot_score']}")

                if not scanned_any:
                    # If no specific pages found, check main site
                    logger.info(f"No specific procurement pages found for {name}, checking main site {url}...")
                    response = self.request_with_retry(url)
                    if response:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        content_text = soup.get_text(' ', strip=True)

                        # Quick check for relevant terms
                        if any(term in content_text.lower() for term in ["procurement", "tender", "supplier", "contract"]):
                            company_keywords = COMPANY_PROFILES[company]["keywords"]
                            if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                                opportunity = self.extract_headshot_opportunity(
                                    content_text,
                                    company, # Target company
                                    f"Housing Association: {name}",
                                    url,
                                    buyer_name=name
                                )

                                if opportunity["headshot_score"] >= 70:  # Higher threshold for main page content
                                    self.db.save_opportunity(opportunity)
                                    discovered_opportunities.append(opportunity)
                                    logger.info(f"Discovered potential headshot opportunity from {name} main page - Score: {opportunity['headshot_score']}")

            except Exception as e:
                logger.error(f"Error scanning {name} ({url}): {e}", exc_info=True)

        logger.info(f"Housing association scan complete. Discovered {len(discovered_opportunities)} headshot opportunities")
        return discovered_opportunities

    def scan_competitor_failures(self):
        """Scan for competitor failures and service issues - these are prime headshot opportunities"""
        logger.info("Scanning for competitor failures and service issues...")
        discovered_opportunities = []

        for company_name, profile in COMPANY_PROFILES.items(): # company_name is EzziUK or RehabilityUK
            competitor_names = profile.get("competitor_names", [])

            for competitor in competitor_names:
                logger.info(f"Scanning for issues with competitor: {competitor} (for {company_name})")

                # Create search terms for different failure/issue scenarios
                failure_terms = [
                    f'"{competitor}" failure', # Added quotes for exact match
                    f'"{competitor}" special measures',
                    f'"{competitor}" contract termination',
                    f'"{competitor}" inadequate',
                    f'"{competitor}" CQC issues',
                    f'"{competitor}" service problems',
                    f'"{competitor}" breach of contract'
                ]

                # Search each term using Google News (via a scraping approach)
                for term in failure_terms:
                    try:
                        encoded_term = quote_plus(term)
                        search_url = f"https://www.google.com/search?q={encoded_term}&tbm=nws" # tbm=nws for news

                        headers = {
                            "User-Agent": self.get_random_user_agent(),
                            "Accept-Language": "en-US,en;q=0.9", # Standard header
                            "Referer": "https://www.google.com/" # Standard header
                        }

                        response = self.request_with_retry(search_url, headers=headers)
                        if not response:
                            continue

                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Extract news results - Google selectors can change, this is fragile
                        news_results = []
                        # Common selectors for Google News results - these might need updating
                        # Option 1: 'div.SoaBEf' (newer?) or 'div.Gx5Zad.fP1Qef.xpd.EtOod.pkphOe'
                        # Option 2: 'div.g' containing 'a' and 'div. Rússia' (snippet class)
                        # Option 3: 'div.WlydOe' (newer structure as of late 2023/early 2024)
                        # Using a more generic approach that might catch different structures
                        # Trying to find a container, then link, title, snippet
                        
                        # Google's HTML structure for search results changes frequently.
                        # The selectors 'div.xuvV6b', 'div.vJOb1e', 'div.GI74Re' are examples and might be outdated.
                        # A more robust solution would use a Google Search API or a dedicated scraping service.
                        # For now, we'll try a few common patterns.
                        
                        # Pattern 1 (example from user's code, might be outdated)
                        results_container = soup.select("div.xuvV6b") # This was likely custom/old
                        if not results_container:
                            results_container = soup.select("div. सोदाहरण") # Hindi for 'example', a common class Google uses for snippets
                        if not results_container:
                             results_container = soup.select("div.Gx5Zad") # Another common Google class
                        if not results_container:
                            results_container = soup.select("div.WlydOe") # Yet another one

                        for result_item in results_container:
                            title_elem = result_item.select_one("div[role='heading']") # Common for titles
                            link_elem = result_item.select_one("a")
                            # Snippet can be harder, often in a div without specific class under the link
                            snippet_elem_candidates = result_item.select("div[data-sncf='2'], div:not([role='heading']) > div") # Heuristic
                            snippet_elem = snippet_elem_candidates[0] if snippet_elem_candidates else None


                            if title_elem and link_elem and link_elem.get('href'):
                                title = title_elem.get_text(strip=True)
                                url = link_elem.get("href")
                                # Google news links are often relative /url?q=...
                                if url.startswith("/url?q="):
                                    url = url.split("/url?q=")[1].split("&sa=")[0]

                                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                                if not url.startswith("http"): # Skip if not a valid link
                                    continue

                                news_results.append({
                                    "title": title,
                                    "url": url,
                                    "snippet": snippet
                                })
                        if not news_results:
                            logger.warning(f"No news results found for term '{term}' using current selectors. Google HTML might have changed.")

                        # Process top 3 results
                        for result_data in news_results[:3]:
                            try:
                                logger.info(f"Processing article: {result_data['url']}")
                                article_response = self.request_with_retry(result_data["url"])
                                if not article_response:
                                    continue

                                article_soup = BeautifulSoup(article_response.text, 'html.parser')

                                # Extract article content
                                for script_or_style in article_soup(["script", "style"]):
                                    script_or_style.decompose()

                                # Try to find main content areas
                                article_body = article_soup.find('article') or \
                                               article_soup.find('main') or \
                                               article_soup.find('div', class_=re.compile(r'(content|article|story|post|body|main)')) or \
                                               article_soup.body
                                
                                article_text = ""
                                if article_body:
                                    article_text = article_body.get_text(" ", strip=True)
                                else:
                                    article_text = article_soup.get_text(" ", strip=True)


                                # Look for service failure indicators
                                service_failure_indicators = [
                                    "fail", "inadequate", "special measures", "terminate", "breach",
                                    "investigation", "issue", "problem", "complaint", "poor quality",
                                    "underperforming", "close down", "scandal", "crisis"
                                ]

                                if any(indicator in article_text.lower() for indicator in service_failure_indicators):
                                    # This is a potential replacement opportunity
                                    opportunity = self.extract_headshot_opportunity(
                                        article_text,
                                        company_name, # Target company (EzziUK or RehabilityUK)
                                        f"Competitor Issue: {competitor}",
                                        result_data["url"],
                                        buyer_name=None  # We don't know the specific buyer yet
                                    )

                                    # Add competitor failure bonus - these are high-value opportunities
                                    opportunity["headshot_score"] = min(100, opportunity["headshot_score"] + 25)  # Major bonus
                                    opportunity["status"] = "competitor_failure_opportunity"
                                    opportunity["data_json"]["competitor_name"] = competitor

                                    # Identify potential buyer from the article
                                    buyer_patterns = [
                                        r"(NHS\s+[\w\s]+(?:Trust|Foundation|CCG|ICB|England|Digital|X))", # Expanded NHS
                                        r"([\w\s]+(?:County|City|District|Borough|Metropolitan Borough)?\s+Council)", # Improved council
                                        r"([\w\s]+Housing\s+Association)"
                                    ]

                                    for pattern in buyer_patterns:
                                        buyer_match = re.search(pattern, article_text, re.IGNORECASE) # Added IGNORECASE
                                        if buyer_match:
                                            opportunity["buyer_name"] = buyer_match.group(1).strip()
                                            break

                                    if opportunity["headshot_score"] >= 50:  # Lower threshold due to high strategic value
                                        self.db.save_opportunity(opportunity)
                                        discovered_opportunities.append(opportunity)
                                        logger.info(f"Discovered competitor failure opportunity: {competitor} (for {company_name}) - Score: {opportunity['headshot_score']}")

                                    # Also create strategic intelligence item
                                    intel_id = f"competitor-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

                                    intel_item = {
                                        "id": intel_id,
                                        "title": f"Competitor Issue: {result_data['title']}",
                                        "type": "competitor_intelligence",
                                        "content": f"Potential service issues identified with competitor {competitor}. This may create replacement opportunities for {company_name}.",
                                        "source": "News Monitoring",
                                        "source_url": result_data["url"],
                                        "discovery_date": datetime.now().isoformat(),
                                        "relevance_score": 90,  # High relevance for competitor issues
                                        "company": company_name, # Target company
                                        "data_json": {
                                            "competitor_name": competitor,
                                            "article_snippet": result_data["snippet"],
                                            "article_title": result_data["title"]
                                        }
                                    }

                                    self.db.save_strategic_intelligence(intel_item)

                            except Exception as e_article: # Renamed to avoid conflict
                                logger.error(f"Error processing article {result_data['url']}: {e_article}", exc_info=True)

                    except Exception as e_search: # Renamed
                        logger.error(f"Error searching for '{term}': {e_search}", exc_info=True)

        logger.info(f"Competitor failure scan complete. Discovered {len(discovered_opportunities)} headshot opportunities")
        return discovered_opportunities

    def scan_premium_frameworks(self):
        """Scan high-value framework opportunities for direct award potential"""
        logger.info("Scanning premium framework opportunities...")
        discovered_opportunities = []

        for source_info in self.premium_sources: # Renamed source to source_info
            name = source_info["name"]
            url = source_info["url"]

            logger.info(f"Scanning premium source: {name}")

            try:
                response = self.request_with_retry(url)
                if not response:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract links to frameworks or direct award opportunities
                framework_links = []
                for link_tag in soup.find_all('a', href=True):
                    href = link_tag.get('href')
                    text = link_tag.get_text()

                    if not text:
                        continue

                    # Look for framework or direct award related links
                    framework_terms = ["framework", "direct award", "call-off",
                                     "approved supplier", "dynamic purchasing",
                                     "procurement solution"]

                    if any(term.lower() in text.lower() for term in framework_terms):
                        url_path = urljoin(url, href)
                        framework_links.append({"url": url_path, "text": text})

                # Process found framework links
                for link_data in framework_links[:5]:  # Process top 5 from each source
                    framework_response = self.request_with_retry(link_data["url"])
                    if not framework_response:
                        continue

                    framework_soup = BeautifulSoup(framework_response.text, 'html.parser')

                    # Extract main content
                    main_content = framework_soup.find('main') or \
                                   framework_soup.find('article') or \
                                   framework_soup.find('div', {'class': ['content', 'main-content', 'main', 'page-content']})

                    if main_content:
                        content_text = main_content.get_text(' ', strip=True)
                    else:
                        for element_to_remove in framework_soup.find_all(['nav', 'footer', 'header', 'script', 'style']):
                            element_to_remove.decompose()
                        if framework_soup.body:
                             content_text = framework_soup.body.get_text(' ', strip=True)
                        else:
                            content_text = framework_soup.get_text(' ', strip=True)


                    # Process for each company
                    for company_name, profile in COMPANY_PROFILES.items():
                        # Check if framework is relevant to company
                        company_keywords = profile["keywords"]
                        if any(keyword.lower() in content_text.lower() for keyword in company_keywords):
                            # Look specifically for direct award possibilities
                            direct_award_indicators = [
                                "direct award", "direct call-off", "without competition",
                                "single supplier", "simplified award", "immediate appointment",
                                "rapid appointment", "quick quote"
                            ]

                            is_direct_award = any(indicator.lower() in content_text.lower() for indicator in direct_award_indicators)

                            # Extract framework opportunity
                            opportunity = self.extract_headshot_opportunity(
                                content_text,
                                company_name, # Target company
                                f"Framework: {name}",
                                link_data["url"],
                                buyer_name=None  # Framework itself isn't a buyer, but a buyer uses it
                            )

                            # Add framework-specific data
                            opportunity["data_json"]["framework_name"] = link_data["text"]
                            opportunity["data_json"]["is_direct_award"] = is_direct_award

                            # Boost score for direct award frameworks
                            if is_direct_award:
                                opportunity["headshot_score"] = min(100, opportunity["headshot_score"] + 20)  # Major bonus
                                opportunity["status"] = "direct_award_framework"
                                opportunity["follow_up_actions"] = "URGENT: Identify buyers using this framework and establish contact. Prepare capability statement specific to framework requirements."

                            if opportunity["headshot_score"] >= 50:  # Lower threshold for strategic frameworks
                                self.db.save_opportunity(opportunity)
                                discovered_opportunities.append(opportunity)
                                logger.info(f"Discovered premium framework opportunity for {company_name} - Score: {opportunity['headshot_score']}")

            except Exception as e:
                logger.error(f"Error scanning premium source {name} ({url}): {e}", exc_info=True)

        logger.info(f"Premium framework scan complete. Discovered {len(discovered_opportunities)} headshot opportunities")
        return discovered_opportunities

    def monitor_contract_award_notices(self):
        """Monitor contract award notices to identify patterns and future opportunities"""
        logger.info("Monitoring contract award notices...")
        awards_found = []

        # Contract award sources (UK specific)
        award_sources = [
            {"name": "Contracts Finder", "url_template": "https://www.contractsfinder.service.gov.uk/Search/Results?&statuses=closed&page={page}#dashboard"}, # Added page template
            {"name": "Find a Tender", "url_template": "https://www.find-tender.service.gov.uk/Search/Results?status=awarded&page={page}#dashboard"} # Changed to awarded, added page template
        ]
        
        max_pages_to_scan = 2 # Limit pages to avoid excessive scanning

        for source_info in award_sources: # Renamed source to source_info
            name = source_info["name"]
            url_template = source_info["url_template"]

            logger.info(f"Checking award notices from {name}")
            
            for page_num in range(1, max_pages_to_scan + 1):
                url = url_template.format(page=page_num)
                logger.info(f"Scanning {name} - Page {page_num}: {url}")

                try:
                    response = self.request_with_retry(url)
                    if not response:
                        logger.warning(f"No response from {url}, skipping page.")
                        break # Stop trying further pages for this source if one fails

                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Extract award notice links
                    award_links = []

                    # Different selectors for different sources
                    if "contractsfinder" in url:
                        # Contracts Finder uses JS to load results, direct scraping of initial page is limited.
                        # This selector is for illustrative purposes if results were static.
                        # A more robust solution would use their API if available or Selenium.
                        for result in soup.select("div.search-result, li.search-result"): # Added li.search-result
                            link_elem = result.select_one("h2 > a, div.search-result-header > a") # More specific link
                            # Status is often part of the text or a label
                            status_text = result.get_text(" ", strip=True).lower()
                            if link_elem and ("awarded" in status_text or "closed" in status_text):
                                href = link_elem.get("href")
                                text = link_elem.get_text(strip=True)

                                if href and text:
                                    # Contracts Finder links are often relative
                                    url_path = urljoin("https://www.contractsfinder.service.gov.uk/", href)
                                    award_links.append({"url": url_path, "text": text, "source_name": name})
                    elif "find-tender" in url:
                        for result in soup.select("div.search-result, .govuk-summary-list__row"): # Adapted for FTS structure
                            link_elem = result.select_one("h2 > a, .govuk-link--no-visited-state")
                            status_elem = result.select_one(".govuk-tag, strong.govuk-tag--green") # FTS uses tags for status
                            
                            if link_elem and status_elem and "awarded" in status_elem.get_text(strip=True).lower():
                                href = link_elem.get("href")
                                text = link_elem.get_text(strip=True)

                                if href and text:
                                    url_path = urljoin("https://www.find-tender.service.gov.uk/", href)
                                    award_links.append({"url": url_path, "text": text, "source_name": name})
                    
                    if not award_links and page_num == 1: # If no links on first page, selectors might be broken
                        logger.warning(f"No award links found on {name} page {page_num}. Selectors might need update or page structure changed.")
                    
                    if not award_links: # If no links on current page, stop for this source
                        break

                    # Process award notices
                    for link_data in award_links[:20]:  # Process top 20 award notices per page
                        try:
                            logger.info(f"Processing award notice: {link_data['url']}")
                            award_response = self.request_with_retry(link_data["url"])
                            if not award_response:
                                continue

                            award_soup = BeautifulSoup(award_response.text, 'html.parser')
                            
                            # Extract main content area text for parsing
                            main_content_area = award_soup.find('main') or \
                                                award_soup.find('div', id='main-content') or \
                                                award_soup.find('div', class_='govuk-grid-column-two-thirds') or \
                                                award_soup.body # Fallback
                            
                            award_text = ""
                            if main_content_area:
                                award_text = main_content_area.get_text(" ", strip=True)
                            else:
                                award_text = award_soup.get_text(" ", strip=True)


                            # Extract relevant sections for each platform
                            contract_title = link_data["text"]
                            winner_name = None
                            value = None
                            buyer_name = None
                            award_date_str = None # For storing extracted date string

                            # --- Generic Extraction Logic (adapt per platform if needed) ---
                            # Extract the contract winner
                            winner_patterns = [
                                r"(?:Name and address of the contractor|Successful tenderer|Winning supplier|Awarded supplier|Supplier name)[\s:]*([^\n\.(]+(?:Ltd|Limited|PLC|LLC|LLP|Inc\.?|CIC)?)",
                                r"(?:Contractor|Supplier)[\s:]*([^\n\.(]+(?:Ltd|Limited|PLC|LLC|LLP|Inc\.?|CIC)?)"
                            ]
                            for pattern in winner_patterns:
                                winner_match = re.search(pattern, award_text, re.IGNORECASE)
                                if winner_match:
                                    winner_name = winner_match.group(1).strip().replace('\n', ' ').replace('  ', ' ')
                                    break
                            if not winner_name and "contractsfinder" in link_data['url']: # CF specific
                                winner_elem = award_soup.find(string=re.compile("Winning supplier"))
                                if winner_elem and winner_elem.find_next_sibling():
                                    winner_name = winner_elem.find_next_sibling().get_text(strip=True)


                            # Extract the contract value
                            value_patterns = [
                                r"(?:Total value of the contract|Contract value|Value of contract|Total final value|Award value)[\s:]*(?:GBP|£|\$|€)?\s*([\d,]+\.?\d*)",
                                r"(?:Value|Estimated value)[\s:]*(?:GBP|£|\$|€)?\s*([\d,]+\.?\d*)\s*(?:million|m|thousand|k)?",
                            ]
                            for pattern in value_patterns:
                                value_match = re.search(pattern, award_text, re.IGNORECASE)
                                if value_match:
                                    value_text = value_match.group(1).strip().lower()
                                    multiplier_text = value_match.group(0).lower() # Check full match for million/k
                                    try:
                                        value_text = value_text.replace(',', '')
                                        current_value = float(re.sub(r'[^\d\.]', '', value_text)) # Clean for float conversion

                                        if 'million' in multiplier_text or ' m' in multiplier_text: # Space before m
                                            current_value *= 1000000
                                        elif 'thousand' in multiplier_text or ' k' in multiplier_text: # Space before k
                                            current_value *= 1000
                                        value = current_value
                                        break
                                    except ValueError:
                                        logger.warning(f"Could not parse value from: {value_text}")
                                        pass
                            
                            # Extract the buyer name
                            buyer_patterns = [
                                r"(?:Name and address of the contracting authority|Contracting authority|Authority name|Buyer name)[\s:]*([^\n\(]+)",
                                r"([\w\s]+(?:Council|Borough|NHS Trust|CCG|ICB|Authority|Government Department|University|Police|Fire and Rescue))" # Generic public bodies
                            ]
                            for pattern in buyer_patterns:
                                buyer_match = re.search(pattern, award_text, re.IGNORECASE)
                                if buyer_match:
                                    buyer_name = buyer_match.group(1).strip().replace('\n', ' ').replace('  ', ' ')
                                    break
                            if not buyer_name and "contractsfinder" in link_data['url']: # CF specific
                                buyer_elem = award_soup.find(string=re.compile("Buyer"))
                                if buyer_elem and buyer_elem.find_next_sibling():
                                    buyer_name = buyer_elem.find_next_sibling().get_text(strip=True)
                            
                            # Extract Award Date
                            award_date_patterns = [
                                r"(?:Date of award of contract|Date of contract award|Award date)[\s:]*(\d{1,2}[./\s-]\w+[./\s-]\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
                                r"Published\s*:\s*(\d{1,2}\s\w+\s\d{4})" # Common on FTS/CF
                            ]
                            for pattern in award_date_patterns:
                                date_match = re.search(pattern, award_text, re.IGNORECASE)
                                if date_match:
                                    award_date_str = date_match.group(1).strip()
                                    try:
                                        # Try to parse into datetime object (optional, can store as string)
                                        # Simplified parsing attempt
                                        clean_date = award_date_str.replace('.', '/').replace('-', '/')
                                        if re.match(r'\d{1,2}/\w+/\d{4}', clean_date): # dd/Month/YYYY
                                            dt_obj = datetime.strptime(re.sub(r'(\d+)(st|nd|rd|th)',r'\1', clean_date), '%d/%B/%Y')
                                        elif re.match(r'\d{1,2}/\d{1,2}/\d{4}', clean_date): # dd/mm/YYYY
                                             dt_obj = datetime.strptime(clean_date, '%d/%m/%Y')
                                        elif re.match(r'\d{1,2}/\d{1,2}/\d{2}', clean_date): # dd/mm/YY
                                             dt_obj = datetime.strptime(clean_date, '%d/%m/%y')
                                        else: # Fallback for "DD Month YYYY"
                                            clean_date = re.sub(r'(\d+)(st|nd|rd|th)',r'\1', award_date_str)
                                            dt_obj = datetime.strptime(clean_date, '%d %B %Y')
                                        award_date_str = dt_obj.isoformat()
                                    except ValueError:
                                        logger.warning(f"Could not parse award date string: {award_date_str}")
                                        pass # Keep original string if parsing fails
                                    break
                            if not award_date_str: # Fallback to discovery date
                                award_date_str = datetime.now().isoformat()


                            # Create a unique ID for this award
                            award_id = f"award-{hashlib.md5(link_data['url'].encode('utf-8')).hexdigest()[:12]}"

                            # Create award record
                            award_data = {
                                "id": award_id,
                                "title": contract_title[:255], # Limit length
                                "description": award_text[:1000],  # First 1000 chars of award text
                                "buyer_name": buyer_name[:255] if buyer_name else None, # Limit length
                                "winner_name": winner_name[:255] if winner_name else None, # Limit length
                                "award_date": award_date_str,
                                "value": value,
                                "source": link_data['source_name'],
                                "source_url": link_data["url"],
                                "data_json": {
                                    "award_platform": link_data['source_name'],
                                    "award_link_text": link_data["text"][:255] # Limit length
                                }
                            }

                            # Save to database and add to results
                            if buyer_name and winner_name and value is not None: # Only save if key details are present
                                self.db.save_contract_award(award_data)
                                awards_found.append(award_data)
                                logger.info(f"Saved contract award: {contract_title[:50]}... - Buyer: {buyer_name} Winner: {winner_name} Value: {value}")
                            else:
                                logger.warning(f"Skipping incomplete award data for: {contract_title[:50]}... URL: {link_data['url']}")


                        except Exception as e_award_proc: # Renamed
                            logger.error(f"Error processing award notice {link_data['url']}: {e_award_proc}", exc_info=True)
                
                except Exception as e_page_scan: # Renamed
                    logger.error(f"Error monitoring award notices from {name} page {page_num} ({url}): {e_page_scan}", exc_info=True)
                    break # Stop trying further pages for this source if an error occurs during page fetching/parsing

        logger.info(f"Contract award monitoring complete. Found {len(awards_found)} award notices")
        return awards_found

    def get_buyer_patterns(self, awards_data):
        """Analyze contract awards to identify buyer patterns and future opportunities"""
        logger.info("Analyzing buyer patterns from contract awards...")

        # Group awards by buyer
        buyer_awards = defaultdict(list)
        for award in awards_data:
            if award.get("buyer_name"):
                buyer_awards[award["buyer_name"]].append(award)

        # Analyze patterns for each buyer with multiple awards
        results = []
        for buyer_name, awards in buyer_awards.items():
            if len(awards) < 2:
                continue  # Skip buyers with only one award

            logger.info(f"Analyzing patterns for buyer: {buyer_name} ({len(awards)} awards)")

            # Calculate average contract value
            values = [award.get("value") for award in awards if award.get("value") is not None] # Check for None
            avg_value = sum(values) / len(values) if values else None

            # Identify common winners
            winners = [award.get("winner_name") for award in awards if award.get("winner_name")]
            winner_counts = Counter(winners) # Use collections.Counter
            most_common_winners = winner_counts.most_common(3)

            # Look for patterns in contract titles/descriptions
            titles = [award.get("title", "") for award in awards]
            descriptions = [award.get("description", "") for award in awards]

            # Identify common words/phrases that might indicate buyer preferences
            all_text = " ".join(titles + descriptions).lower()

            # Extract potential patterns
            pattern_results = {
                "buyer_name": buyer_name,
                "awards_count": len(awards),
                "average_value": avg_value,
                "common_winners": most_common_winners,
                "contract_frequency": f"Approximately every {365 // max(1, len(awards))} days", # Approximation
                "value_trend": "Increasing" if len(values) >= 2 and values[-1] > values[0] else ("Decreasing" if len(values) >=2 and values[-1] < values[0] else "Stable"), # Added Decreasing
                "buyer_preferences": self._extract_buyer_preferences(all_text)
            }

            results.append(pattern_results)

            # For each buyer with patterns, create strategic intelligence
            intel_id = f"buyer-pattern-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

            # Determine which company this is most relevant for
            relevant_company_for_pattern = None # Renamed to avoid conflict
            # Check against keywords of all company profiles
            for company_name_iter, profile_iter in COMPANY_PROFILES.items():
                company_keywords_iter = profile_iter["keywords"]
                if any(keyword.lower() in all_text for keyword in company_keywords_iter):
                    relevant_company_for_pattern = company_name_iter
                    break # Assign to first matching company

            if relevant_company_for_pattern: # If a relevant company is found for this pattern
                intel_item_content = f"Analysis of {len(awards)} contract awards by {buyer_name}. "
                if avg_value is not None:
                    intel_item_content += f"Average value: {avg_value:,.0f}. "
                else:
                    intel_item_content += "Average value: Unknown. "
                intel_item_content += f"Common winners: {', '.join([w[0] for w in most_common_winners[:2]])}. "
                intel_item_content += f"Contract frequency: {pattern_results['contract_frequency']}."


                intel_item = {
                    "id": intel_id,
                    "title": f"Buyer Pattern Analysis: {buyer_name}",
                    "type": "buyer_pattern",
                    "content": intel_item_content,
                    "source": "Contract Award Analysis",
                    "source_url": "", # No specific URL for aggregated analysis
                    "discovery_date": datetime.now().isoformat(),
                    "relevance_score": 85,  # High relevance for buyer patterns
                    "company": relevant_company_for_pattern, # The company this pattern is relevant for
                    "data_json": pattern_results
                }

                self.db.save_strategic_intelligence(intel_item)
                logger.info(f"Saved buyer pattern intelligence for {buyer_name} (relevant to {relevant_company_for_pattern})")

                # If we detect a buyer is likely to procure soon, create a specific opportunity
                if self._is_buyer_likely_to_procure_soon(pattern_results, all_text):
                    future_contract_text_parts = [f"Based on historical pattern analysis, {buyer_name} is likely to procure a new contract soon."]
                    if avg_value is not None:
                         future_contract_text_parts.append(f"They typically award contracts valued at around {avg_value:,.0f}")
                    if most_common_winners:
                         future_contract_text_parts.append(f"and have previously worked with {', '.join([w[0] for w in most_common_winners[:2]])}.")
                    if pattern_results['buyer_preferences']:
                         future_contract_text_parts.append(f"Their procurement typically shows preferences for {', '.join(pattern_results['buyer_preferences'][:3])}.")
                    future_contract_text = " ".join(future_contract_text_parts)


                    opportunity = self.extract_headshot_opportunity(
                        future_contract_text,
                        relevant_company_for_pattern, # Target company
                        f"Predicted Opportunity: {buyer_name}",
                        "",  # No URL yet
                        buyer_name=buyer_name
                    )

                    # Set special values for predicted opportunities
                    opportunity["headshot_score"] = min(100, opportunity["headshot_score"] + 15)  # Bonus for prediction
                    opportunity["status"] = "predicted_opportunity"
                    opportunity["estimated_value"] = avg_value if avg_value else 0

                    # Calculate estimated timing
                    if len(awards) >= 2:
                        # Ensure data_json exists
                        if "data_json" not in opportunity: opportunity["data_json"] = {}
                        opportunity["data_json"]["estimated_procurement_month"] = self._predict_next_procurement_month(awards)

                    if opportunity["headshot_score"] >= 65:  # Lower threshold for predicted opportunities
                        self.db.save_opportunity(opportunity)
                        logger.info(f"Created predicted opportunity for {buyer_name} - Score: {opportunity['headshot_score']}")

        logger.info(f"Buyer pattern analysis complete. Analyzed {len(results)} buyers with multiple awards")
        return results

    def _extract_buyer_preferences(self, text):
        """Extract potential buyer preferences from contract text"""
        preferences = []
        # Look for phrases that indicate preferences
        preference_indicators = [
            "prefer", "requirement", "essential", "important", "priority",
            "experience in", "track record", "demonstrated", "evidence of", "key criteria"
        ]

        sentences = re.split(r'[.!?]\s+', text) # Split by sentence enders

        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(indicator in sentence_lower for indicator in preference_indicators):
                # Simplify the sentence to extract core preference
                # Remove common authority mentions to focus on the preference itself
                simple_pref = re.sub(r'(?:we|the authority|the council|the trust|the buyer)\s+(?:prefer|require|need|want|expect|look for|seek|value)', '', sentence_lower, flags=re.I).strip()
                # Remove leading "that", "to", etc.
                simple_pref = re.sub(r'^(that|to|for|an|a|the)\s+', '', simple_pref).strip()

                if 10 < len(simple_pref) < 150:  # Adjusted reasonable length
                    # Avoid overly generic phrases
                    if not any(generic in simple_pref for generic in ["value for money", "high quality", "cost effective"]):
                        preferences.append(simple_pref.capitalize()) # Capitalize for readability
        
        preferences = list(dict.fromkeys(preferences)) # Remove duplicates while preserving order

        # If we couldn't extract specific preferences, look for frequent noun phrases (more advanced)
        # This is a simplified version using n-grams if specific preferences are few
        if len(preferences) < 3:
            words = re.findall(r'\b\w+\b', text.lower()) # Get all words
            
            # Find common 3-grams and 4-grams
            ngrams_counts = Counter()
            for n in range(3, 5): # 3-grams and 4-grams
                for i in range(len(words) - n + 1):
                    ngram = " ".join(words[i:i+n])
                    # Filter out ngrams starting/ending with common stop words or too short individually
                    if len(ngram) > 15 and not (words[i] in ['the', 'a', 'of', 'for'] or words[i+n-1] in ['the', 'a', 'of', 'for']):
                         ngrams_counts[ngram] +=1
            
            for ngram, count in ngrams_counts.most_common(5):
                if count > 1 and not any(ngram in pref.lower() for pref in preferences): # Avoid adding if already covered
                    preferences.append(ngram.capitalize())


        return preferences[:5]  # Return top 5 unique preferences

    def _is_buyer_likely_to_procure_soon(self, pattern_results, text):
        """Determine if a buyer is likely to procure soon based on patterns"""
        # Check indicators in contract text (could be from recent award descriptions)
        procurement_indicators = [
            "renew", "re-procure", "re-tender", "replace", "upcoming",
            "future contract", "new procurement", "next phase", "market engagement"
        ]

        if any(indicator in text.lower() for indicator in procurement_indicators):
            return True

        # Check contract frequency - if they procure frequently, more likely to be soon
        frequency_text = pattern_results.get("contract_frequency", "")
        if "every" in frequency_text:
            try:
                days_match = re.search(r'every\s+(\d+)', frequency_text)
                if days_match:
                    days = int(days_match.group(1))
                    if days <= 180:  # If they procure every 6 months or less, likely soon
                        return True
            except (ValueError, TypeError):
                pass # Ignore if conversion fails

        # Check if contracts are increasing in value (could indicate growth and more procurement)
        if pattern_results.get("value_trend") == "Increasing":
            return True

        return False

    def _predict_next_procurement_month(self, awards):
        """Predict the next procurement month based on award history"""
        try:
            # Extract dates from awards
            dates = []
            for award in awards:
                award_date_val = award.get("award_date")
                if award_date_val:
                    try:
                        # Handle both datetime objects and ISO format strings
                        if isinstance(award_date_val, str):
                            date_obj = datetime.fromisoformat(award_date_val.replace('Z', '')) # Handle Zulu time
                        elif isinstance(award_date_val, datetime):
                            date_obj = award_date_val
                        else:
                            continue # Skip if not a recognized type
                        dates.append(date_obj)
                    except ValueError:
                        logger.debug(f"Could not parse date: {award_date_val}")
                        pass # Skip if date parsing fails

            if len(dates) < 2:
                return "Unknown (Insufficient Data)"

            # Sort dates
            dates.sort()

            # Calculate average interval in days
            intervals = []
            for i in range(1, len(dates)):
                interval_days = (dates[i] - dates[i-1]).days
                if interval_days > 0: # Consider only positive intervals
                    intervals.append(interval_days)

            if not intervals: # No valid intervals found
                 return "Unknown (No Valid Intervals)"

            avg_interval_days = sum(intervals) / len(intervals)

            if avg_interval_days <= 0: # Average interval is not useful
                 return "Unknown (Non-Positive Interval)"

            # Project next date
            next_date = dates[-1] + timedelta(days=avg_interval_days)

            return next_date.strftime("%B %Y")
        except Exception as e:
            logger.error(f"Error predicting next procurement month: {e}", exc_info=True)
            return "Unknown (Error)"

    def send_headshot_notifications(self):
        """Send notifications about high-scoring headshot opportunities"""
        if not DISCORD_WEBHOOK:
            logger.warning("Discord webhook not configured, skipping notifications")
            return False

        notification_sent_for_any_company = False # Track if any notification was sent

        for company_name in COMPANY_PROFILES.keys():
            # Get opportunities with score 85+ (default), or slightly lower for predicted (handled in their creation)
            opportunities = self.db.get_headshot_opportunities(company=company_name, min_score=80, limit=5) # Slightly lower general threshold

            if not opportunities:
                logger.info(f"No new headshot opportunities to notify for {company_name}")
                continue

            try:
                # Create a rich Discord embed for high-value opportunities
                embeds = []

                for opp in opportunities:
                    # Set color based on score
                    score = float(opp.get("headshot_score", 0)) # Default to 0 if missing
                    if score >= 90:
                        color = 0xFF0000  # Red - urgent headshot opportunity
                    elif score >= 85:
                        color = 0xFF6600  # Orange - high-value headshot opportunity
                    else: # 80-84
                        color = 0xFFCC00  # Yellow - good headshot opportunity

                    # Format value
                    value_str = "Unknown"
                    est_value = opp.get("estimated_value")
                    if est_value and isinstance(est_value, (int, float)) and est_value > 0:
                        value = float(est_value)
                        if value >= 1000000:
                            value_str = f"£{value/1000000:.1f}M"
                        elif value >= 1000:
                            value_str = f"£{value/1000:.1f}K"
                        else:
                            value_str = f"£{value:.0f}"

                    # Format profit information
                    profit_info = ""
                    est_profit_margin = opp.get("estimated_profit_margin")
                    if est_profit_margin and est_value and isinstance(est_profit_margin, (int, float)) and est_value > 0:
                        margin = float(est_profit_margin)
                        value = float(est_value) # Already defined
                        profit_amount = (margin / 100) * value

                        if profit_amount >= 1000000:
                            profit_str = f"£{profit_amount/1000000:.1f}M"
                        elif profit_amount >= 1000:
                            profit_str = f"£{profit_amount/1000:.1f}K"
                        else:
                            profit_str = f"£{profit_amount:.0f}"

                        profit_info = f"Est. Profit: {profit_str} ({margin:.1f}%)"

                    # Create embed
                    embed_description = opp.get("description", "No description available.")
                    embed_description = (embed_description[:450] + "...") if len(embed_description) > 450 else embed_description # Limit length

                    embed = {
                        "title": f"🎯 HEADSHOT: {opp.get('title', 'Untitled Opportunity')}",
                        "description": embed_description,
                        "color": color,
                        "fields": [
                            {
                                "name": "Buyer",
                                "value": opp.get("buyer_name", "Unknown"),
                                "inline": True
                            },
                            {
                                "name": "Est. Value",
                                "value": value_str,
                                "inline": True
                            },
                            {
                                "name": "Win Prob.",
                                "value": f"{opp.get('win_probability', 0):.1f}%",
                                "inline": True
                            },
                            {
                                "name": "Competition",
                                "value": opp.get("competition_level", "Unknown"),
                                "inline": True
                            },
                            {
                                "name": "Profit Prob.",
                                "value": f"{opp.get('profit_probability', 0):.1f}%",
                                "inline": True
                            },
                            {
                                "name": "HEADSHOT Score",
                                "value": f"**{score:.1f}/100**", # Use score variable
                                "inline": True
                            }
                        ],
                        "footer": {
                            "text": f"Source: {opp.get('source','N/A')} | ID: {opp.get('id','N/A')}"
                        },
                        "timestamp": datetime.now().isoformat() # Use UTC for consistency if possible
                    }
                    if opp.get("closing_date"):
                         embed["fields"].append({
                             "name": "Closing Date",
                             "value": datetime.fromisoformat(opp["closing_date"]).strftime('%d %b %Y') if opp["closing_date"] else "N/A",
                             "inline": True
                         })
                    if opp.get("follow_up_actions"):
                        embed["fields"].append({
                             "name": "Follow-up Actions",
                             "value": opp.get("follow_up_actions", "None specified")[:1000], # Limit length
                             "inline": False
                         })


                    # Add URL if available
                    if opp.get("source_url"):
                        embed["url"] = opp["source_url"]

                    # Add profit field if available
                    if profit_info:
                        embed["fields"].append({
                            "name": "Profit Estimate",
                            "value": profit_info,
                            "inline": True
                        })

                    embeds.append(embed)

                # Create message payload
                payload = {
                    "content": f"🚨 **{len(opportunities)} High-Value HEADSHOT Opportunities for {company_name}** 🚨",
                    "embeds": embeds
                }

                # Send to Discord
                response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10) # Added timeout

                if response.status_code == 204 or response.status_code == 200: # 200 is also success for some webhooks
                    logger.info(f"Successfully sent Discord notification for {company_name} with {len(embeds)} opportunities")
                    notification_sent_for_any_company = True
                    # Mark opportunities as notified
                    for opp_to_mark in opportunities: # Renamed opp
                        self.db.mark_notification_sent(opp_to_mark["id"])

                else:
                    logger.error(f"Failed to send Discord notification for {company_name}. Status: {response.status_code}, Response: {response.text}")
                    # Do not return False here, try other companies

            except Exception as e:
                logger.error(f"Error sending Discord notification for {company_name}: {e}", exc_info=True)
                # Do not return False here

        return notification_sent_for_any_company


    def run_headshot_scan(self):
        """Run a complete headshot scan for all sources and identify guaranteed profit opportunities"""
        logger.info("Starting HEADSHOT opportunity scan...")
        all_opportunities = [] # To collect opportunities from various scans

        # Using ThreadPoolExecutor for concurrent scanning of different source types
        # This can speed up I/O bound tasks like web scraping.
        # Adjust max_workers based on your system and the nature of the tasks.
        # For CPU-bound parsing, ProcessPoolExecutor might be better, but scraping is I/O.
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            # 1. Scan local authorities
            futures.append(executor.submit(self.scan_local_authorities))
            # 2. Scan NHS commissioners
            futures.append(executor.submit(self.scan_nhs_commissioners))
            # 3. Scan housing associations
            futures.append(executor.submit(self.scan_housing_associations))
            # 4. Check for competitors in trouble
            futures.append(executor.submit(self.scan_competitor_failures))
            # 5. Scan premium frameworks
            futures.append(executor.submit(self.scan_premium_frameworks))

            for future in as_completed(futures):
                try:
                    opportunities_from_scan = future.result()
                    if opportunities_from_scan: # Ensure it's not None and is a list
                        all_opportunities.extend(opportunities_from_scan)
                except Exception as e:
                    logger.error(f"Error in one of the scanning tasks: {e}", exc_info=True)


        # 6. Monitor contract awards to identify patterns and predict future opportunities
        # This is usually a slower process and might be better run less frequently or separately
        # For now, keeping it in the main scan.
        try:
            awards = self.monitor_contract_award_notices()
            if awards: # If new awards were found
                self.get_buyer_patterns(awards) # This can also create opportunities
        except Exception as e:
            logger.error(f"Error in contract award monitoring or pattern analysis: {e}", exc_info=True)


        # 7. Send notifications for headshot opportunities
        # This should run after all opportunities are gathered and scored.
        try:
            self.send_headshot_notifications()
        except Exception as e:
            logger.error(f"Error sending notifications: {e}", exc_info=True)


        # 8. Export opportunities to CSV for external analysis
        try:
            self.db.export_opportunities_csv()
        except Exception as e:
            logger.error(f"Error exporting opportunities to CSV: {e}", exc_info=True)


        logger.info(f"HEADSHOT scan complete. Found/processed {len(all_opportunities)} initial opportunities from direct scans.")
        # Note: all_opportunities doesn't include those generated by get_buyer_patterns or strategic intel directly.
        # The total impact is seen in the database and notifications.
        return all_opportunities


def main():
    """Main entry point for the HEADSHOT Agent"""
    logger.info("🎯 Starting HEADSHOT Agent - Target Acquisition Mode")

    # Create and run the headshot agent
    agent = HeadshotAgent()
    agent.run_headshot_scan()

    logger.info("🎯 HEADSHOT Agent mission complete")


if __name__ == "__main__":
    main()
