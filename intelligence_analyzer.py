# intelligence_analyzer.py
"""
Components for strategic business intelligence analysis of procurement opportunities.
"""
import logging
import re
import datetime
from typing import List, Dict, Any, Optional, Tuple

from config import COMPANY_PROFILES, SCORING_WEIGHTS, MIN_RELEVANCE_SCORE_TO_REPORT, TENDER_HISTORY_DAYS
from data_acquisition import Tender # Re-using the Tender class

logger = logging.getLogger(__name__)

class CompanyProfile:
    def __init__(self, name: str, services: List[str], keywords: List[str], strengths: List[str], weaknesses: List[str]):
        self.name = name
        self.services = [s.lower() for s in services]
        self.keywords = [k.lower() for k in keywords]
        self.strengths = strengths
        self.weaknesses = weaknesses

# Load company profiles from config
COMPANIES = [CompanyProfile(**details) for details in COMPANY_PROFILES.values()]


def parse_contract_value(value_text: Optional[str]) -> Optional[float]:
    """
    Rudimentary parsing of contract value string.
    e.g., "£100,000", "€50k - 70k", "$1.2M"
    Returns a single representative value (e.g., midpoint for a range).
    """
    if not value_text:
        return None
    
    value_text = value_text.lower()
    # Remove currency symbols and commas
    value_text = re.sub(r'[£€$\s,]', '', value_text)
    
    # Handle K (thousands) and M (millions)
    multiplier = 1.0
    if 'k' in value_text:
        multiplier = 1000.0
        value_text = value_text.replace('k', '')
    elif 'm' in value_text:
        multiplier = 1000000.0
        value_text = value_text.replace('m', '')

    # Handle ranges (e.g., "50-70") - take midpoint
    if '-' in value_text:
        parts = value_text.split('-')
        try:
            low = float(parts[0]) * multiplier
            high = float(parts[1]) * multiplier
            return (low + high) / 2.0
        except ValueError:
            pass # Fall through to single value parsing
    
    try:
        return float(value_text) * multiplier
    except ValueError:
        logger.debug(f"Could not parse contract value: {value_text}")
        return None

def get_value_tier(value: Optional[float]) -> int:
    """Categorizes contract value into tiers for scoring (0-10)."""
    if value is None: return 3 # Neutral score for unknown value
    if value > 1000000: return 10 # Very High
    if value > 500000: return 8  # High
    if value > 100000: return 6  # Medium-High
    if value > 25000: return 4   # Medium
    if value > 5000: return 2    # Low
    return 1                     # Very Low

def calculate_urgency_score(closing_date_str: Optional[str]) -> int:
    """Calculates an urgency score (0-10) based on closing date."""
    if not closing_date_str:
        return 3 # Neutral if no closing date

    try:
        # Try to parse common date formats. OCDS format is YYYY-MM-DDTHH:MM:SSZ
        closing_date = datetime.datetime.fromisoformat(closing_date_str.replace('Z', '+00:00'))
        # If parsing fails, might need more robust date parsing logic
    except ValueError:
        try: # Try another common format if ISO fails
            closing_date = datetime.datetime.strptime(closing_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"Could not parse closing date: {closing_date_str}")
            return 3 

    days_to_closing = (closing_date - datetime.datetime.now(datetime.timezone.utc)).days
    
    if days_to_closing < 0: return 0 # Expired
    if days_to_closing <= 7: return 10 # Very Urgent
    if days_to_closing <= 14: return 8 # Urgent
    if days_to_closing <= 30: return 6 # Moderately Urgent
    if days_to_closing <= 60: return 4 # Less Urgent
    return 2 # Not Urgent / Far Future

class OpportunityAnalyzer:
    def __init__(self, tender: Tender, company: CompanyProfile):
        self.tender = tender
        self.company = company
        self.analysis_results: Dict[str, Any] = {}

    def score_opportunity(self) -> float:
        """
        Scores the opportunity for the given company based on configured weights.
        Returns a score from 0 to 100.
        """
        full_text = f"{self.tender.title} {self.tender.description}".lower()

        # 1. Keyword Match Score (0-10)
        keyword_hits = 0
        for keyword in self.company.keywords:
            if keyword in full_text:
                keyword_hits += 1
        # Normalize: max 10 points. If >5 keywords hit, score 10.
        keyword_match_score = min((keyword_hits / 5) * 10, 10) if self.company.keywords else 0

        # 2. Value Tier Score (0-10)
        parsed_value = parse_contract_value(self.tender.value_text)
        value_tier_score = get_value_tier(parsed_value)
        self.analysis_results['parsed_value'] = parsed_value # Store for reporting

        # 3. Company Fit Score (0-10) - How well does it align with core services?
        fit_score = 0
        for service_desc in self.company.services:
            # More sophisticated matching could use NLP (e.g., sentence similarity)
            if service_desc in full_text:
                fit_score += 2 # Simple increment, max 10
        company_fit_score = min(fit_score, 10)

        # 4. Urgency Score (0-10)
        urgency_score = calculate_urgency_score(self.tender.closing_date)

        # Weighted total score
        total_score = (
            keyword_match_score * SCORING_WEIGHTS["keyword_match"] +
            value_tier_score * SCORING_WEIGHTS["value_tier"] +
            company_fit_score * SCORING_WEIGHTS["company_fit"] +
            urgency_score * SCORING_WEIGHTS["urgency"]
        )
        # Normalize to 0-100 (max possible weighted sum if all scores are 10)
        # Max possible un-normalized score is 10 (sum of weights * 10).
        # If sum of weights is 1, then total_score is already 0-10. So multiply by 10.
        # Example: if weights sum to 1.0, max score is 10. To scale to 100, multiply by 10.
        # Max raw score for keyword_match etc is 10. Max total score = (10*0.4 + 10*0.3 + 10*0.2 + 10*0.1) = 4+3+2+1 = 10
        # So, scale by 10 to get to 100.
        final_score = total_score * 10 
        
        self.analysis_results['scores'] = {
            "keyword_match": keyword_match_score,
            "value_tier": value_tier_score,
            "company_fit": company_fit_score,
            "urgency": urgency_score,
            "overall": round(final_score, 2)
        }
        return round(final_score, 2)

    def generate_swot_analysis(self) -> Dict[str, List[str]]:
        """Generates a simple SWOT analysis for the tender relative to the company."""
        swot = {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}
        full_text = f"{self.tender.title} {self.tender.description}".lower()

        # Strengths: Company services mentioned or implied
        for service in self.company.services:
            if service in full_text:
                swot["strengths"].append(f"Relevant service: {service.capitalize()}")
        for strength_desc in self.company.strengths:
             # If generic strengths are relevant to common tender types
            if "housing" in full_text and "housing" in strength_desc.lower():
                 swot["strengths"].append(strength_desc)
            if "care" in full_text and "care" in strength_desc.lower():
                 swot["strengths"].append(strength_desc)
        if not swot["strengths"]: swot["strengths"].append("Initial assessment: standard fit.")


        # Weaknesses: Company weaknesses, or if tender requires something outside core services
        # This is harder to automate without more detailed tender requirement parsing.
        # For now, list general company weaknesses.
        swot["weaknesses"].extend(self.company.weaknesses)
        # Could add: "If tender requires X, Y, Z (which are not our strengths)"

        # Opportunities
        swot["opportunities"].append(f"Bid for contract: {self.tender.title}")
        parsed_value = self.analysis_results.get('parsed_value')
        if parsed_value and parsed_value > 100000:
            swot["opportunities"].append("Potential for significant revenue.")
        # Could add: Market entry, strategic partnership (see partnership_suggestion)

        # Threats
        if self.tender.closing_date:
            days_to_closing = calculate_urgency_score(self.tender.closing_date) # Re-using logic, scale is 0-10
            if days_to_closing >= 8 : # Urgent or Very Urgent (score 8 or 10)
                 swot["threats"].append("Tight deadline for submission.")
        swot["threats"].append("Presence of other competitors (assume standard competition).")
        # Could add: Specific difficult requirements if identified.

        self.analysis_results['swot'] = swot
        return swot

    def suggest_partnerships(self, all_companies: List[CompanyProfile]) -> List[str]:
        """Suggests potential partnerships with other configured companies."""
        suggestions = []
        full_text = f"{self.tender.title} {self.tender.description}".lower()

        for other_company in all_companies:
            if other_company.name == self.company.name:
                continue

            # Check for keyword overlap from the other company
            other_company_keyword_hits = 0
            for keyword in other_company.keywords:
                if keyword in full_text:
                    other_company_keyword_hits +=1
            
            # Check if current company might miss some keywords that other company has
            current_company_keyword_misses_covered_by_other = 0
            # This logic is a bit simplistic. A better way: define complementary services.
            # Example: if tender asks for "housing management" (EzziUK) AND "specialist care" (RehabilityUK)
            
            # Simple heuristic: if the tender has keywords relevant to both companies significantly.
            company_keywords_in_tender = sum(1 for kw in self.company.keywords if kw in full_text)
            
            if other_company_keyword_hits > 2 and company_keywords_in_tender > 2:
                # If tender has strong signals for both this company and another
                suggestions.append(
                    f"Consider partnership with {other_company.name} due to synergistic keywords present in the tender."
                )
            
            # More advanced: If tender requires services A (our company) and B (other company)
            # This requires better parsing of tender requirements. For now, use keyword overlap.

        self.analysis_results['partnership_suggestions'] = suggestions
        return suggestions

    def recommend_resource_allocation(self) -> str:
        """Provides a high-level resource allocation recommendation."""
        score = self.analysis_results.get('scores', {}).get('overall', 0)
        parsed_value = self.analysis_results.get('parsed_value')

        if score > 80:
            if parsed_value and parsed_value > 250000:
                rec = "High Priority: Allocate senior bid team, dedicated resources."
            elif parsed_value and parsed_value > 50000:
                rec = "High Priority: Allocate experienced bid writer and subject matter expert."
            else:
                rec = "High Potential: Assign to bid team for detailed review and proposal."
        elif score > 60:
            rec = "Medium Priority: Review by bid manager, consider proposal if capacity allows."
        elif score >= MIN_RELEVANCE_SCORE_TO_REPORT: # Only for those above threshold
            rec = "Low-Medium Priority: Initial review by junior staff, assess bid feasibility."
        else:
            rec = "Low Priority / Monitor: Keep an eye if strategic, otherwise likely pass."
        
        self.analysis_results['resource_recommendation'] = rec
        return rec

    def calculate_bid_timing(self) -> str:
        """Estimates key dates for the bidding process."""
        if not self.tender.closing_date:
            return "Closing date not specified; bid timing cannot be calculated."

        try:
            closing_dt = datetime.datetime.fromisoformat(self.tender.closing_date.replace('Z', '+00:00'))
        except ValueError:
             try:
                closing_dt = datetime.datetime.strptime(self.tender.closing_date, '%Y-%m-%d')
             except ValueError:
                return "Invalid closing date format; bid timing cannot be calculated."

        today = datetime.datetime.now(closing_dt.tzinfo) # Match timezone awareness
        days_left = (closing_dt - today).days

        if days_left < 0:
            return "This tender has already closed."

        # Simplified estimation of preparation time based on value/complexity (heuristic)
        parsed_value = self.analysis_results.get('parsed_value')
        estimated_prep_days = 7 # Default minimum
        if parsed_value:
            if parsed_value > 1000000: estimated_prep_days = 30
            elif parsed_value > 250000: estimated_prep_days = 21
            elif parsed_value > 50000: estimated_prep_days = 14
        
        if days_left < estimated_prep_days:
            prep_time_comment = f"Warning: Only {days_left} days left, estimated {estimated_prep_days} days needed."
        else:
            prep_time_comment = f"Estimated {estimated_prep_days} days for preparation."

        internal_deadline = closing_dt - datetime.timedelta(days=max(2, int(estimated_prep_days * 0.2))) # 2 days or 20% buffer
        
        return (
            f"Closing Date: {closing_dt.strftime('%Y-%m-%d %H:%M')}. "
            f"Days Left: {days_left}. "
            f"{prep_time_comment} "
            f"Suggested Internal Deadline for Final Review: {internal_deadline.strftime('%Y-%m-%d')}."
        )


    def run_full_analysis(self, all_companies: List[CompanyProfile]) -> Dict[str, Any]:
        """Runs all analysis components and stores results."""
        self.score_opportunity() # This populates self.analysis_results['scores'] and 'parsed_value'
        self.generate_swot_analysis()
        self.suggest_partnerships(all_companies)
        self.recommend_resource_allocation()
        self.analysis_results['bid_timing'] = self.calculate_bid_timing()
        
        # Competitive landscape, contract patterns - these are broader and need historical data
        # For now, these are placeholders in the final report structure.
        self.analysis_results['competitive_landscape'] = "Generic: Assume moderate to high competition from established players and SMEs."
        self.analysis_results['contract_patterns'] = "Analysis requires more historical data. Monitor for recurring opportunities from this buyer or of this type."
        
        return {
            "tender_id": self.tender.id,
            "tender_title": self.tender.title,
            "tender_url": self.tender.url,
            "company_name": self.company.name,
            "analysis": self.analysis_results
        }


def analyze_tenders_for_companies(tenders: List[Tender]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Analyzes a list of tenders for all configured companies.
    Returns a dictionary where keys are company names and values are lists of analysis results for relevant tenders.
    """
    company_reports: Dict[str, List[Dict[str, Any]]] = {comp.name: [] for comp in COMPANIES}

    for tender in tenders:
        logger.debug(f"Analyzing tender: {tender.title} ({tender.id})")
        for company_profile in COMPANIES:
            analyzer = OpportunityAnalyzer(tender, company_profile)
            overall_score = analyzer.score_opportunity() # Calculate score first

            if overall_score >= MIN_RELEVANCE_SCORE_TO_REPORT:
                logger.info(f"Tender '{tender.title}' scored {overall_score} for {company_profile.name}. Relevant.")
                full_analysis_results = analyzer.run_full_analysis(COMPANIES)
                company_reports[company_profile.name].append(full_analysis_results)
            else:
                logger.debug(f"Tender '{tender.title}' scored {overall_score} for {company_profile.name}. Below threshold.")
    
    # Sort reports by score for each company
    for company_name in company_reports:
        company_reports[company_name].sort(key=lambda x: x['analysis']['scores']['overall'], reverse=True)
        
    return company_reports


# Functions requiring historical data (conceptual, need DB integration)
def detect_contract_patterns(company: CompanyProfile, historical_tenders_db_path: str = "data/processed_tenders.db") -> str:
    """
    Analyzes historical tender data for patterns relevant to the company.
    This is a conceptual implementation. Needs access to a populated tender database.
    """
    # import sqlite3
    # patterns_found = []
    # conn = sqlite3.connect(historical_tenders_db_path)
    # cursor = conn.cursor()
    #
    # cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=TENDER_HISTORY_DAYS)).isoformat()
    #
    # # Example: Find frequent issuers for keywords relevant to the company
    # for keyword in company.keywords[:3]: # Limit for performance
    #     cursor.execute("""
    #         SELECT source, COUNT(*) as count 
    #         FROM tenders 
    #         WHERE (title LIKE ? OR description LIKE ?) AND first_seen_date >= ?
    #         GROUP BY source 
    #         ORDER BY count DESC 
    #         LIMIT 3
    #     """, (f'%{keyword}%', f'%{keyword}%', cutoff_date))
    #     results = cursor.fetchall()
    #     if results:
    #         for row in results:
    #             patterns_found.append(f"Frequent issuer for '{keyword}': {row[0]} ({row[1]} times)")
    #
    # conn.close()
    # if not patterns_found:
    #     return "No significant contract patterns detected in the recent historical data."
    # return "Contract Patterns: " + "; ".join(patterns_found)
    return "Contract pattern detection module is conceptual and requires historical data analysis."


def map_competitive_landscape(company: CompanyProfile, historical_tenders_db_path: str = "data/processed_tenders.db") -> str:
    """
    Provides a high-level overview of the competitive landscape.
    Conceptual: Would need data on awarded contracts and bidder information.
    """
    # This is very hard with only public tender notices. Award notices sometimes list winners.
    # If we were storing award notices and parsing them:
    # - Identify common winners for tenders matching company profile.
    # - Identify frequent bidders.
    return "Competitive landscape mapping is conceptual and requires awarded contract data."


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    # Create dummy tenders for testing
    dummy_tender1 = Tender(
        id="DUMMY001",
        title="Major Social Housing Management Contract in London",
        url="http://example.com/tender1",
        source="Dummy Portal",
        description="A large contract for managing 500 social housing units in central London. Includes tenant services and maintenance.",
        published_date=datetime.datetime.now().isoformat(),
        closing_date=(datetime.datetime.now() + datetime.timedelta(days=30)).isoformat(),
        value_text="£1,500,000 - £2,000,000 per annum"
    )
    dummy_tender2 = Tender(
        id="DUMMY002",
        title="Supported Living Services for Adults with Learning Disabilities",
        url="http://example.com/tender2",
        source="Dummy NHS Portal",
        description="Provision of supported living and personal care for 20 adults with learning disabilities across multiple sites.",
        published_date=(datetime.datetime.now() - datetime.timedelta(days=5)).isoformat(),
        closing_date=(datetime.datetime.now() + datetime.timedelta(days=10)).isoformat(),
        value_text="Approx. £750k"
    )
    dummy_tender3 = Tender(
        id="DUMMY003",
        title="Office Cleaning Services - Small Contract",
        url="http://example.com/tender3",
        source="Local Council Site",
        description="Basic office cleaning for a small council building.",
        published_date=(datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
        closing_date=(datetime.datetime.now() + datetime.timedelta(days=20)).isoformat(),
        value_text="£15,000"
    )
    
    test_tenders = [dummy_tender1, dummy_tender2, dummy_tender3]
    
    analyzed_data = analyze_tenders_for_companies(test_tenders)
    
    for company_name, reports in analyzed_data.items():
        print(f"\n--- Intelligence Report for {company_name} ---")
        if not reports:
            print("No highly relevant opportunities found.")
            continue
        for report in reports:
            print(f"\nTender: {report['tender_title']} (Score: {report['analysis']['scores']['overall']})")
            print(f"  URL: {report['tender_url']}")
            print(f"  Parsed Value: {report['analysis'].get('parsed_value', 'N/A')}")
            print(f"  Resource Rec: {report['analysis']['resource_recommendation']}")
            print(f"  Bid Timing: {report['analysis']['bid_timing']}")
            print(f"  SWOT (Strengths): {report['analysis']['swot']['strengths']}")
            if report['analysis']['partnership_suggestions']:
                print(f"  Partnerships: {report['analysis']['partnership_suggestions']}")

    # Test pattern detection (will be conceptual)
    # print("\n--- Contract Pattern Test (Conceptual) ---")
    # for company_profile in COMPANIES:
    #     print(f"For {company_profile.name}: {detect_contract_patterns(company_profile)}")
