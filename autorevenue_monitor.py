# 🤖 AUTOREVENUE PROFESSIONAL SYSTEM WITH REAL INTELLIGENCE
# Complete system with web scraping, Claude AI analysis, and ML scoring

import os
import time
import random
from datetime import datetime, timedelta
import json

# Import all our intelligence modules
from web_scraper import RealOpportunityScraper
from reddit_scraper import RedditBusinessScraper
from ai_analyzer import ClaudeOpportunityAnalyzer
from email_sender import AutoRevenueEmailSender

class IntelligentAutoRevenue:
    def __init__(self):
        self.version = "9.0 - Intelligent Real Data Edition"
        self.monitoring_interval = 600  # 10 minutes
        
        # Initialize all intelligence systems
        print("🚀 Initializing AutoRevenue Intelligence Systems...")
        self.web_scraper = RealOpportunityScraper()
        self.reddit_scraper = RedditBusinessScraper()
        self.ai_analyzer = ClaudeOpportunityAnalyzer()
        self.email_sender = AutoRevenueEmailSender()
        
        # Tracking
        self.known_opportunities = set()
        self.alerts_sent_today = 0
        self.system_start_time = datetime.now()
        self.last_scan_time = None
        
        print(f"✅ AutoRevenue Intelligent System v{self.version} Ready")
        print(f"📧 Email alerts: {self.email_sender.recipient_email}")
        print(f"🤖 Claude AI: {'✅ Connected' if self.ai_analyzer.api_key else '❌ No API key'}")
    
    def comprehensive_opportunity_scan(self):
        """Perform comprehensive scan across all intelligence sources"""
        print(f"\n🔍 COMPREHENSIVE INTELLIGENCE SCAN - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)
        
        all_opportunities = []
        scan_sources = [
            ("Government Portals", self.scan_government_sources),
            ("Reddit Intelligence", self.scan_reddit_intelligence),
        ]
        
        # Collect opportunities from all sources
        for source_name, scanner_func in scan_sources:
            print(f"\n📡 {source_name}...")
            try:
                opportunities = scanner_func()
                if opportunities:
                    all_opportunities.extend(opportunities)
                    print(f"✅ {source_name}: {len(opportunities)} opportunities")
                else:
                    print(f"ℹ️ {source_name}: No new opportunities")
            except Exception as e:
                print(f"❌ {source_name} error: {str(e)}")
        
        # Remove duplicates
        unique_opportunities = self.remove_duplicates(all_opportunities)
        
        # AI Analysis with Claude
        if unique_opportunities and self.ai_analyzer.api_key:
            print(f"\n🤖 Claude AI Analysis...")
            analyzed_opportunities = self.ai_analyzer.analyze_multiple_opportunities(unique_opportunities)
        else:
            print(f"\n⚠️ Skipping AI analysis (no API key or opportunities)")
            analyzed_opportunities = unique_opportunities
        
        # ML Opportunity Scoring
        scored_opportunities = self.apply_ml_scoring(analyzed_opportunities)
        
        # Filter new opportunities
        new_opportunities = self.filter_new_opportunities(scored_opportunities)
        
        # Send alerts for high-value opportunities
        if new_opportunities:
            self.send_intelligence_alerts(new_opportunities)
        
        # Update tracking
        self.last_scan_time = datetime.now()
        
        print(f"\n📊 SCAN SUMMARY:")
        print(f"   • Total collected: {len(all_opportunities)}")
        print(f"   • After deduplication: {len(unique_opportunities)}")
        print(f"   • New opportunities: {len(new_opportunities)}")
        print(f"   • High-value (>300% ROI): {len([o for o in new_opportunities if o.get('estimated_roi', 0) > 300])}")
        print("=" * 80)
        
        return len(new_opportunities)
    
    def scan_government_sources(self):
        """Scan government procurement sources"""
        try:
            return self.web_scraper.get_all_opportunities()
        except Exception as e:
            print(f"❌ Government scan error: {str(e)}")
            return []
    
    def scan_reddit_intelligence(self):
        """Scan Reddit for business intelligence"""
        try:
            return self.reddit_scraper.scrape_business_intelligence()
        except Exception as e:
            print(f"❌ Reddit scan error: {str(e)}")
            return []
    
    def remove_duplicates(self, opportunities):
        """Remove duplicate opportunities using intelligent matching"""
        unique_opps = []
        seen_signatures = set()
        
        for opp in opportunities:
            # Create content signature for duplicate detection
            title_words = set(opp['title'].lower().split())
            authority_words = set(opp['authority'].lower().split())
            
            # Create a content signature
            signature_content = ' '.join(sorted(title_words.union(authority_words)))
            
            # Simple hash for signatures
            content_hash = hash(signature_content)
            
            # Check for similar content
            is_duplicate = False
            for seen_hash in seen_signatures:
                # Very basic similarity check
                if abs(content_hash - seen_hash) < 1000:  # Arbitrary threshold
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_opps.append(opp)
                seen_signatures.add(content_hash)
        
        return unique_opps
    
    def apply_ml_scoring(self, opportunities):
        """Apply machine learning-based opportunity scoring"""
        print(f"⚡ Applying ML scoring to {len(opportunities)} opportunities...")
        
        for opp in opportunities:
            try:
                # Multi-factor scoring algorithm
                ml_score = self.calculate_ml_score(opp)
                
                # Update opportunity with ML insights
                opp['ml_score'] = ml_score
                opp['scored_at'] = datetime.now().isoformat()
                
                # Enhanced priority based on ML + AI analysis
                opp['final_priority'] = self.determine_final_priority(opp)
                
            except Exception as e:
                print(f"   ⚠️ ML scoring error for {opp['id']}: {str(e)}")
                opp['ml_score'] = 50.0  # Default score
                opp['final_priority'] = opp.get('priority', 'MEDIUM')
        
        # Sort by ML score (highest first)
        return sorted(opportunities, key=lambda x: x.get('ml_score', 0), reverse=True)
    
    def calculate_ml_score(self, opportunity):
        """Calculate ML-based opportunity score (0-100)"""
        score = 0.0
        
        # 1. Source credibility (25%)
        source_scores = {
            'Contracts Finder': 25,
            'Find a Tender': 25,
            'gov.uk News': 20,
            'Reddit': 15
        }
        source = opportunity.get('source', '').split(' - ')[0]
        score += source_scores.get(source, 10)
        
        # 2. Financial indicators (25%)
        value_text = opportunity.get('value', '').lower()
        if 'million' in value_text or 'm' in value_text:
            score += 25
        elif 'thousand' in value_text or 'k' in value_text:
            score += 15
        elif any(word in value_text for word in ['gbp', '£', 'value', 'contract']):
            score += 10
        else:
            score += 5
        
        # 3. Deadline urgency (20%)
        try:
            deadline_str = opportunity.get('deadline', '')
            if deadline_str and deadline_str != 'Monitor for developments':
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
                days_remaining = (deadline - datetime.now()).days
                
                if days_remaining <= 14:
                    score += 20  # Very urgent
                elif days_remaining <= 30:
                    score += 15
                elif days_remaining <= 60:
                    score += 10
                else:
                    score += 5
            else:
                score += 8  # Ongoing opportunity
        except:
            score += 8  # Default for parsing errors
        
        # 4. Company alignment (15%)
        company_match = opportunity.get('company_match', 'Unknown')
        if company_match in ['EzziUK', 'RehabilityUK']:
            score += 15
        elif company_match == 'Both Companies':
            score += 12
        else:
            score += 5
        
        # 5. AI analysis integration (15%)
        if 'ai_analysis' in opportunity:
            roi = opportunity.get('estimated_roi', 0)
            confidence = opportunity.get('confidence_level', 50)
            strategic_fit = opportunity.get('strategic_fit', 5)
            
            # ROI component (60% of AI portion)
            if roi >= 500:
                score += 9
            elif roi >= 300:
                score += 7
            elif roi >= 200:
                score += 5
            else:
                score += 3
            
            # Confidence component (40% of AI portion)
            score += (confidence / 100) * 6
        else:
            score += 7  # Default for non-AI analyzed opportunities
        
        return min(score, 100.0)  # Cap at 100
    
    def determine_final_priority(self, opportunity):
        """Determine final priority combining ML and AI insights"""
        ml_score = opportunity.get('ml_score', 50)
        ai_priority = opportunity.get('priority', 'MEDIUM')
        estimated_roi = opportunity.get('estimated_roi', 0)
        
        # Priority scoring
        priority_scores = {
            'CRITICAL': 4,
            'HIGH': 3,
            'MEDIUM': 2,
            'LOW': 1
        }
        
        ai_score = priority_scores.get(ai_priority, 2)
        
        # Combined scoring
        if ml_score >= 80 and estimated_roi >= 400:
            return 'CRITICAL'
        elif ml_score >= 70 and ai_score >= 3:
            return 'CRITICAL'
        elif ml_score >= 60 or ai_score >= 3:
            return 'HIGH'
        elif ml_score >= 40 or ai_score >= 2:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def filter_new_opportunities(self, opportunities):
        """Filter out previously seen opportunities"""
        new_opportunities = []
        
        for opp in opportunities:
            opp_id = opp['id']
            if opp_id not in self.known_opportunities:
                new_opportunities.append(opp)
                self.known_opportunities.add(opp_id)
        
        return new_opportunities
    
    def send_intelligence_alerts(self, opportunities):
        """Send intelligent email alerts for high-value opportunities"""
        print(f"📧 Sending alerts for {len(opportunities)} opportunities...")
        
        # Sort by final priority and ML score
        priority_order = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
        sorted_opps = sorted(
            opportunities, 
            key=lambda x: (priority_order.get(x.get('final_priority', 'MEDIUM'), 1), x.get('ml_score', 0)), 
            reverse=True
        )
        
        # Send alerts for top opportunities (limit to avoid email overload)
        max_alerts = 5  # Maximum alerts per scan
        sent_count = 0
        
        for opp in sorted_opps[:max_alerts]:
            try:
                # Enhance opportunity data for email
                enhanced_opp = self.enhance_opportunity_for_email(opp)
                
                # Send email alert
                success = self.email_sender.send_opportunity_email(enhanced_opp)
                
                if success:
                    self.alerts_sent_today += 1
                    sent_count += 1
                    print(f"   ✅ Alert sent: {opp['title'][:50]}...")
                else:
                    print(f"   ❌ Failed to send: {opp['title'][:50]}...")
                
                # Rate limiting between emails
                time.sleep(2)
                
            except Exception as e:
                print(f"   ❌ Error sending alert: {str(e)}")
        
        print(f"📊 Alert Summary: {sent_count}/{len(opportunities)} alerts sent")
    
    def enhance_opportunity_for_email(self, opportunity):
        """Enhance opportunity data for professional email"""
        enhanced = opportunity.copy()
        
        # Add intelligence summary
        if 'ai_analysis' in opportunity:
            # Extract key insights from AI analysis
            ai_analysis = opportunity['ai_analysis']
            
            # Create executive summary
            executive_summary = f"""
🤖 AI Analysis Summary:
• Estimated ROI: {opportunity.get('estimated_roi', 'Analyzing')}%
• Strategic Fit: {opportunity.get('strategic_fit', 'Evaluating')}/10
• Overall Risk: {ai_analysis.get('risk_analysis', {}).get('overall_risk', 'Medium')}
• Confidence Level: {opportunity.get('confidence_level', 'Calculating')}%

💡 Key Insights:
{' • '.join(ai_analysis.get('key_insights', ['Professional analysis available']))}

🎯 Recommended Actions:
{' • '.join(ai_analysis.get('action_plan', ['Contact procurement team', 'Prepare proposal']))}
"""
            enhanced['executive_summary'] = executive_summary
        
        # Add ML scoring information
        if 'ml_score' in opportunity:
            ml_summary = f"""
⚡ ML Intelligence Score: {opportunity['ml_score']:.1f}/100
🏆 Final Priority: {opportunity.get('final_priority', 'Evaluated')}
📊 Data Source Quality: {opportunity.get('source', 'Multiple sources')}
"""
            enhanced['ml_summary'] = ml_summary
        
        # Ensure contact information is available
        if not enhanced.get('contact'):
            enhanced['contact'] = self.generate_fallback_contact(opportunity)
        
        return enhanced
    
    def generate_fallback_contact(self, opportunity):
        """Generate fallback contact information"""
        authority = opportunity.get('authority', 'Unknown Authority')
        
        return {
            'name': 'Procurement Team',
            'title': 'Procurement Officer',
            'phone': 'See tender documentation',
            'email': f"procurement@{authority.lower().replace(' ', '').replace('council', '').replace('authority', '')}.gov.uk"
        }
    
    def send_daily_intelligence_report(self):
        """Send comprehensive daily intelligence report"""
        print("📊 Generating daily intelligence report...")
        
        report_data = {
            'scan_date': datetime.now().strftime('%d %B %Y'),
            'total_opportunities': len(self.known_opportunities),
            'alerts_sent': self.alerts_sent_today,
            'system_uptime': str(datetime.now() - self.system_start_time).split('.')[0],
            'last_scan': self.last_scan_time.strftime('%H:%M') if self.last_scan_time else 'Initializing',
            'ai_status': 'Connected' if self.ai_analyzer.api_key else 'Limited',
            'sources_active': ['Government Portals', 'Reddit Intelligence', 'AI Analysis', 'ML Scoring']
        }
        
        try:
            return self.email_sender.send_daily_summary_email(report_data)
        except Exception as e:
            print(f"❌ Error sending daily report: {str(e)}")
            return False
    
    def run_intelligent_monitoring(self):
        """Run the complete intelligent monitoring system"""
        print("🚀 AUTOREVENUE INTELLIGENT MONITORING SYSTEM")
        print("=" * 80)
        print(f"🤖 Version: {self.version}")
        print(f"📡 Data Sources: Government, Reddit, AI Analysis, ML Scoring")
        print(f"📧 Professional email alerts enabled")
        print(f"⏰ Scan frequency: Every {self.monitoring_interval//60} minutes")
        print("=" * 80)
        
        # Send startup notification
        print("📧 Sending system startup notification...")
        startup_opp = {
            'id': 'SYSTEM-STARTUP-INTELLIGENT',
            'title': 'AutoRevenue Intelligent System Activated',
            'authority': 'AutoRevenue AI',
            'value': 'Intelligent monitoring active',
            'deadline': 'Continuous operation',
            'company_match': 'System Status',
            'confidence_level': 100.0,
            'priority': 'INFO',
            'final_priority': 'INFO',
            'source': 'System Notification',
            'description': f'''AutoRevenue Intelligent System v{self.version} is now active with:
• Real-time government procurement scanning
• Reddit business intelligence monitoring  
• Claude AI opportunity analysis
• Machine learning opportunity scoring
• Professional email alerts to {self.email_sender.recipient_email}

The system will continuously monitor and alert you to high-value opportunities automatically.''',
            'contact': {
                'name': 'AutoRevenue Intelligence',
                'title': 'AI System',
                'phone': 'N/A',
                'email': 'system@autorevenue.ai'
            },
            'ml_score': 100.0,
            'executive_summary': 'System fully operational with all intelligence modules active.'
        }
        
        self.email_sender.send_opportunity_email(startup_opp)
        
        # For GitHub Actions, run single scan
        if os.getenv('GITHUB_ACTIONS'):
            print("\n🔄 Running GitHub Actions scan...")
            new_opportunities = self.comprehensive_opportunity_scan()
            print(f"✅ Scan complete - {new_opportunities} new opportunities processed")
        else:
            # For local/continuous running
            print("\n🔄 Starting continuous monitoring loop...")
            
            cycle_count = 0
            last_daily_report = datetime.now().date()
            
            try:
                while True:
                    cycle_count += 1
                    current_time = datetime.now()
                    
                    print(f"\n🔄 INTELLIGENCE CYCLE #{cycle_count}")
                    print(f"⏰ {current_time.strftime('%d/%m/%Y %H:%M:%S')}")
                    
                    # Run comprehensive scan
                    new_opportunities = self.comprehensive_opportunity_scan()
                    
                    # Send daily report at 9 AM
                    if (current_time.time().hour == 9 and 
                        current_time.time().minute < 30 and 
                        current_time.date() > last_daily_report):
                        
                        self.send_daily_intelligence_report()
                        last_daily_report = current_time.date()
                        self.alerts_sent_today = 0
                    
                    # Wait for next cycle
                    print(f"⏳ Next scan in {self.monitoring_interval//60} minutes...")
                    time.sleep(self.monitoring_interval)
                    
            except KeyboardInterrupt:
                print("\n🛑 Intelligent monitoring stopped")
            except Exception as e:
                print(f"\n❌ System error: {str(e)}")

# Main execution
if __name__ == "__main__":
    # Initialize and run the intelligent system
    system = IntelligentAutoRevenue()
    system.run_intelligent_monitoring()
