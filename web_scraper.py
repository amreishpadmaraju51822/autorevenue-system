# 🔍 REAL WEB SCRAPER FOR UK PROCUREMENT AND BUSINESS OPPORTUNITIES
import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta
import time
import random

class RealOpportunityScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def scrape_contracts_finder(self, max_pages=2):
        """Scrape UK Government Contracts Finder"""
        print("🔍 Scraping Contracts Finder...")
        opportunities = []
        
        base_url = "https://www.contractsfinder.service.gov.uk"
        search_terms = [
            "housing management",
            "social housing", 
            "supported living",
            "care services",
            "mental health services",
            "property management"
        ]
        
        try:
            for term in search_terms:
                # Search for recent opportunities
                search_url = f"{base_url}/Search?&keywords={term.replace(' ', '+')}&sort_order=desc&sort_by=published"
                
                print(f"   Searching: {term}")
                response = self.session.get(search_url, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Find opportunity listings
                    listings = soup.find_all('div', class_='search-result')
                    
                    for listing in listings[:5]:  # Limit to top 5 per search
                        try:
                            # Extract basic info
                            title_elem = listing.find('h2', class_='search-result-title')
                            title = title_elem.get_text(strip=True) if title_elem else "Title not found"
                            
                            # Extract link
                            link_elem = title_elem.find('a') if title_elem else None
                            detail_link = base_url + link_elem['href'] if link_elem and 'href' in link_elem.attrs else None
                            
                            # Extract authority
                            authority_elem = listing.find('p', string=re.compile('Authority:', re.I))
                            authority = authority_elem.get_text(strip=True).replace('Authority:', '').strip() if authority_elem else "Authority not found"
                            
                            # Extract value if available
                            value_text = listing.get_text()
                            value_match = re.search(r'£[\d,.]+(M|K|million|thousand)?', value_text, re.I)
                            value = value_match.group() if value_match else "Value not disclosed"
                            
                            # Extract deadline
                            deadline_match = re.search(r'Closing date:.*?(\d{1,2}/\d{1,2}/\d{4})', value_text)
                            deadline = deadline_match.group(1) if deadline_match else None
                            
                            # Convert deadline to proper format
                            if deadline:
                                try:
                                    deadline_obj = datetime.strptime(deadline, '%d/%m/%Y')
                                    deadline = deadline_obj.strftime('%Y-%m-%d')
                                except:
                                    deadline = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                            else:
                                deadline = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                            
                            # Generate opportunity ID
                            opp_id = f"CF-{hash(title + authority) % 10000}"
                            
                            # Determine company match
                            title_lower = title.lower()
                            if any(keyword in title_lower for keyword in ['housing', 'property', 'accommodation']):
                                company_match = 'EzziUK'
                            elif any(keyword in title_lower for keyword in ['care', 'health', 'support', 'mental', 'rehabilitation']):
                                company_match = 'RehabilityUK'
                            else:
                                company_match = 'Both Companies'
                            
                            opportunity = {
                                'id': opp_id,
                                'title': title,
                                'authority': authority,
                                'value': value,
                                'deadline': deadline,
                                'company_match': company_match,
                                'source': 'Contracts Finder',
                                'detail_link': detail_link,
                                'search_term': term,
                                'scraped_at': datetime.now().isoformat(),
                                'description': f"Opportunity found via search term: {term}",
                                'priority': self.calculate_priority(title, value, deadline),
                                'confidence_level': self.calculate_confidence(title, value, authority)
                            }
                            
                            opportunities.append(opportunity)
                            
                        except Exception as e:
                            print(f"   Error processing listing: {str(e)}")
                            continue
                
                # Rate limiting
                time.sleep(random.uniform(1, 3))
                
        except Exception as e:
            print(f"   Error scraping Contracts Finder: {str(e)}")
        
        print(f"   Found {len(opportunities)} opportunities on Contracts Finder")
        return opportunities
    
    def scrape_gov_uk_news(self):
        """Scrape gov.uk news for procurement announcements"""
        print("🔍 Scraping gov.uk news...")
        opportunities = []
        
        try:
            # Search gov.uk news for procurement-related content
            news_urls = [
                "https://www.gov.uk/search/news-and-communications?keywords=procurement+housing",
                "https://www.gov.uk/search/news-and-communications?keywords=tender+healthcare",
                "https://www.gov.uk/search/news-and-communications?keywords=framework+social+care"
            ]
            
            for url in news_urls:
                print(f"   Scraping: {url.split('=')[-1].replace('+', ' ')}")
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    articles = soup.find_all('li', class_='gem-c-document-list__item')
                    
                    for article in articles[:3]:  # Top 3 articles per search
                        try:
                            title_elem = article.find('a')
                            title = title_elem.get_text(strip=True) if title_elem else "No title"
                            
                            # Check if it's procurement-related
                            if any(keyword in title.lower() for keyword in ['tender', 'procurement', 'framework', 'contract', 'opportunity']):
                                link = "https://www.gov.uk" + title_elem['href'] if title_elem and 'href' in title_elem.attrs else None
                                
                                # Extract date
                                date_elem = article.find('time')
                                pub_date = date_elem['datetime'] if date_elem and 'datetime' in date_elem.attrs else datetime.now().isoformat()
                                
                                opportunity = {
                                    'id': f"GOV-NEWS-{hash(title) % 10000}",
                                    'title': f"Government Announcement: {title}",
                                    'authority': 'UK Government',
                                    'value': 'To be announced',
                                    'deadline': (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d'),
                                    'company_match': 'Both Companies',
                                    'source': 'gov.uk News',
                                    'detail_link': link,
                                    'published_date': pub_date,
                                    'scraped_at': datetime.now().isoformat(),
                                    'description': f"Government announcement that may indicate upcoming procurement opportunities",
                                    'priority': 'MEDIUM',
                                    'confidence_level': 75.0
                                }
                                
                                opportunities.append(opportunity)
                                
                        except Exception as e:
                            print(f"   Error processing article: {str(e)}")
                            continue
                
                time.sleep(random.uniform(2, 4))
                
        except Exception as e:
            print(f"   Error scraping gov.uk news: {str(e)}")
        
        print(f"   Found {len(opportunities)} potential opportunities in gov.uk news")
        return opportunities
    
    def scrape_find_tender(self):
        """Scrape Find a Tender (UK's official tender portal)"""
        print("🔍 Scraping Find a Tender...")
        opportunities = []
        
        try:
            # Find a Tender search URLs
            search_url = "https://www.find-tender.service.gov.uk/Search"
            
            # Search parameters for relevant tenders
            search_params = [
                {'keywords': 'housing services'},
                {'keywords': 'care services'},
                {'keywords': 'social housing'},
                {'keywords': 'supported living'}
            ]
            
            for params in search_params:
                response = self.session.get(search_url, params=params, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Find tender listings
                    tender_cards = soup.find_all('div', class_='search-result-header')
                    
                    for card in tender_cards[:3]:  # Top 3 per search
                        try:
                            title_elem = card.find('h2')
                            title = title_elem.get_text(strip=True) if title_elem else "Title not found"
                            
                            # Extract link
                            link_elem = title_elem.find('a') if title_elem else None
                            detail_link = "https://www.find-tender.service.gov.uk" + link_elem['href'] if link_elem and 'href' in link_elem.attrs else None
                            
                            # Extract basic tender info
                            info_text = card.get_text()
                            
                            # Extract authority
                            authority_match = re.search(r'Contracting authority:\s*([^\\n]+)', info_text)
                            authority = authority_match.group(1).strip() if authority_match else "Authority not specified"
                            
                            # Extract value
                            value_match = re.search(r'Contract value:\s*([^\\n]+)', info_text)
                            value = value_match.group(1).strip() if value_match else "Value not disclosed"
                            
                            # Extract deadline
                            deadline_match = re.search(r'Closing date:\s*(\d{1,2}/\d{1,2}/\d{4})', info_text)
                            if deadline_match:
                                try:
                                    deadline_obj = datetime.strptime(deadline_match.group(1), '%d/%m/%Y')
                                    deadline = deadline_obj.strftime('%Y-%m-%d')
                                except:
                                    deadline = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                            else:
                                deadline = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                            
                            # Determine company match
                            title_lower = title.lower()
                            if any(keyword in title_lower for keyword in ['housing', 'property', 'accommodation']):
                                company_match = 'EzziUK'
                            elif any(keyword in title_lower for keyword in ['care', 'health', 'support', 'mental', 'rehabilitation']):
                                company_match = 'RehabilityUK'
                            else:
                                company_match = 'Both Companies'
                            
                            opportunity = {
                                'id': f"FT-{hash(title + authority) % 10000}",
                                'title': title,
                                'authority': authority,
                                'value': value,
                                'deadline': deadline,
                                'company_match': company_match,
                                'source': 'Find a Tender',
                                'detail_link': detail_link,
                                'search_term': params['keywords'],
                                'scraped_at': datetime.now().isoformat(),
                                'description': f"Live tender found via search: {params['keywords']}",
                                'priority': self.calculate_priority(title, value, deadline),
                                'confidence_level': self.calculate_confidence(title, value, authority)
                            }
                            
                            opportunities.append(opportunity)
                            
                        except Exception as e:
                            print(f"   Error processing tender: {str(e)}")
                            continue
                
                time.sleep(random.uniform(2, 4))
                
        except Exception as e:
            print(f"   Error scraping Find a Tender: {str(e)}")
        
        print(f"   Found {len(opportunities)} live tenders")
        return opportunities
    
    def calculate_priority(self, title, value, deadline):
        """Calculate priority based on title keywords, value, and deadline"""
        priority_score = 0
        
        # Title-based scoring
        title_lower = title.lower()
        high_priority_keywords = ['urgent', 'immediate', 'asap', 'critical', 'emergency']
        medium_priority_keywords = ['framework', 'major', 'strategic', 'significant']
        
        if any(keyword in title_lower for keyword in high_priority_keywords):
            priority_score += 3
        elif any(keyword in title_lower for keyword in medium_priority_keywords):
            priority_score += 2
        else:
            priority_score += 1
        
        # Value-based scoring
        if 'million' in value.lower() or 'M' in value:
            priority_score += 2
        elif 'thousand' in value.lower() or 'K' in value:
            priority_score += 1
        
        # Deadline-based scoring
        try:
            deadline_obj = datetime.strptime(deadline, '%Y-%m-%d')
            days_until = (deadline_obj - datetime.now()).days
            if days_until <= 7:
                priority_score += 3
            elif days_until <= 30:
                priority_score += 2
            else:
                priority_score += 1
        except:
            priority_score += 1
        
        # Determine final priority
        if priority_score >= 7:
            return 'CRITICAL'
        elif priority_score >= 5:
            return 'HIGH'
        elif priority_score >= 3:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def calculate_confidence(self, title, value, authority):
        """Calculate confidence level based on data completeness and source"""
        confidence = 60.0  # Base confidence
        
        # Title quality
        if len(title) > 10 and title != "Title not found":
            confidence += 10
        
        # Value information
        if value and value != "Value not disclosed" and value != "Value not found":
            confidence += 15
        
        # Authority information
        if authority and authority != "Authority not found" and authority != "Authority not specified":
            confidence += 10
        
        # Source reliability
        confidence += 5  # All sources are official government portals
        
        return min(confidence, 98.0)  # Cap at 98%
    
    def get_all_opportunities(self):
        """Get opportunities from all sources"""
        print("🚀 Starting comprehensive opportunity scan...")
        print("=" * 60)
        
        all_opportunities = []
        
        # Scrape all sources
        sources = [
            ("Contracts Finder", self.scrape_contracts_finder),
            ("gov.uk News", self.scrape_gov_uk_news),
            ("Find a Tender", self.scrape_find_tender)
        ]
        
        for source_name, scrape_func in sources:
            print(f"\n📡 Scraping {source_name}...")
            try:
                opportunities = scrape_func()
                all_opportunities.extend(opportunities)
                print(f"✅ {source_name}: {len(opportunities)} opportunities found")
            except Exception as e:
                print(f"❌ {source_name}: Error - {str(e)}")
        
        # Remove duplicates based on title similarity
        unique_opportunities = self.remove_duplicates(all_opportunities)
        
        print(f"\n📊 Summary:")
        print(f"   Total scraped: {len(all_opportunities)}")
        print(f"   After deduplication: {len(unique_opportunities)}")
        print(f"   EzziUK opportunities: {len([o for o in unique_opportunities if o['company_match'] == 'EzziUK'])}")
        print(f"   RehabilityUK opportunities: {len([o for o in unique_opportunities if o['company_match'] == 'RehabilityUK'])}")
        print("=" * 60)
        
        return unique_opportunities
    
    def remove_duplicates(self, opportunities):
        """Remove duplicate opportunities based on title similarity"""
        unique_opps = []
        seen_titles = set()
        
        for opp in opportunities:
            # Create a normalized title for comparison
            normalized_title = re.sub(r'[^a-zA-Z0-9\s]', '', opp['title'].lower()).strip()
            
            # Check if we've seen a similar title
            is_duplicate = False
            for seen_title in seen_titles:
                # Simple similarity check - if 80% of words match
                title_words = set(normalized_title.split())
                seen_words = set(seen_title.split())
                
                if len(title_words) > 0 and len(seen_words) > 0:
                    intersection = len(title_words.intersection(seen_words))
                    union = len(title_words.union(seen_words))
                    similarity = intersection / union
                    
                    if similarity > 0.8:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_opps.append(opp)
                seen_titles.add(normalized_title)
        
        return unique_opps

# Test the scraper
if __name__ == "__main__":
    scraper = RealOpportunityScraper()
    opportunities = scraper.get_all_opportunities()
    
    if opportunities:
        print(f"\n🎉 Found {len(opportunities)} unique opportunities!")
        for i, opp in enumerate(opportunities[:3], 1):
            print(f"\n{i}. {opp['title']}")
            print(f"   Authority: {opp['authority']}")
            print(f"   Value: {opp['value']}")
            print(f"   Company: {opp['company_match']}")
            print(f"   Priority: {opp['priority']}")
    else:
        print("\n⚠️ No opportunities found in this scan")
