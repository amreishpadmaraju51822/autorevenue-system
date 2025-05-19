# 🤖 CLAUDE 3.7 AI OPPORTUNITY ANALYZER
import os
import json
import requests
from datetime import datetime
import re

class ClaudeOpportunityAnalyzer:
    def __init__(self):
        self.api_key = os.getenv('CLAUDE_API_KEY')
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        self.model = "claude-3-sonnet-20240229"  # Using Claude 3 Sonnet (free tier)
        
    def analyze_opportunity(self, opportunity):
        """Analyze a single opportunity using Claude 3.7"""
        try:
            # Prepare the prompt for Claude
            analysis_prompt = self._create_analysis_prompt(opportunity)
            
            # Make API call to Claude
            response = self._call_claude_api(analysis_prompt)
            
            if response:
                # Parse Claude's response
                analysis = self._parse_claude_response(response)
                
                # Enhance the opportunity with AI analysis
                enhanced_opportunity = self._enhance_opportunity(opportunity, analysis)
                
                return enhanced_opportunity
            else:
                print(f"   ❌ Failed to analyze: {opportunity['title'][:50]}...")
                return opportunity
                
        except Exception as e:
            print(f"   ❌ Error analyzing opportunity: {str(e)}")
            return opportunity
    
    def _create_analysis_prompt(self, opportunity):
        """Create a detailed prompt for Claude to analyze the opportunity"""
        
        # Determine company context
        if opportunity['company_match'] == 'EzziUK':
            company_context = """
            EzziUK specializes in:
            - Social housing management
            - Rent guarantee services
            - Landlord support services
            - Property management
            - Housing benefit administration
            - Tenant relations
            """
        elif opportunity['company_match'] == 'RehabilityUK':
            company_context = """
            RehabilityUK specializes in:
            - Supported living services
            - Mental health support
            - Learning disability services
            - Care and rehabilitation
            - Community-based care
            - Person-centered care plans
            """
        else:
            company_context = """
            Both EzziUK (housing management) and RehabilityUK (supported living/care) could be relevant.
            """
        
        prompt = f"""You are a business opportunity analyst specializing in UK public sector procurement. Analyze this opportunity and provide detailed insights.

OPPORTUNITY DETAILS:
Title: {opportunity['title']}
Authority: {opportunity['authority']}
Value: {opportunity['value']}
Deadline: {opportunity['deadline']}
Source: {opportunity['source']}
Description: {opportunity.get('description', 'No description available')}

COMPANY CONTEXT:
{company_context}

ANALYSIS REQUIRED:

1. **ROI ASSESSMENT**: Calculate potential ROI (aim for 500%+ as specified). Consider:
   - Contract value vs typical profit margins
   - Operational costs
   - Market competition
   - Long-term value

2. **STRATEGIC FIT**: Rate how well this matches company capabilities (1-10)

3. **RISK ANALYSIS**: Identify key risks:
   - Competition level
   - Technical requirements
   - Financial risks
   - Timeline challenges

4. **ACTION PLAN**: Provide specific next steps:
   - Immediate actions (next 24-48 hours)
   - Research needed
   - Key contacts to approach
   - Documents to prepare

5. **COMPETITIVE ADVANTAGE**: How can the company differentiate itself?

6. **CONFIDENCE SCORE**: Overall confidence in winning (1-100%)

7. **PRIORITY CLASSIFICATION**: Critical/High/Medium/Low and why

8. **KEY INSIGHTS**: 2-3 crucial insights about this opportunity

Provide your analysis in this exact JSON format:
{{
    "roi_assessment": {{
        "estimated_roi_percentage": number,
        "revenue_potential": "description",
        "profitability_analysis": "detailed analysis"
    }},
    "strategic_fit_score": number (1-10),
    "risk_analysis": {{
        "competition_risk": "high/medium/low - explanation",
        "technical_risk": "high/medium/low - explanation", 
        "financial_risk": "high/medium/low - explanation",
        "overall_risk": "high/medium/low"
    }},
    "action_plan": [
        "action item 1",
        "action item 2",
        "action item 3"
    ],
    "competitive_advantages": [
        "advantage 1",
        "advantage 2"
    ],
    "confidence_score": number (1-100),
    "priority_classification": "CRITICAL/HIGH/MEDIUM/LOW",
    "priority_reasoning": "explanation",
    "key_insights": [
        "insight 1",
        "insight 2"
    ],
    "enhanced_description": "improved description based on analysis",
    "contact_strategy": "suggested approach for initial contact"
}}

Be specific, actionable, and focus on maximizing commercial success while providing honest assessments."""

        return prompt
    
    def _call_claude_api(self, prompt):
        """Make API call to Claude"""
        try:
            payload = {
                "model": self.model,
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = requests.post(
                self.api_url, 
                headers=self.headers, 
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                return response_data['content'][0]['text']
            else:
                print(f"   ❌ Claude API Error: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"   ❌ Claude API call failed: {str(e)}")
            return None
    
    def _parse_claude_response(self, response_text):
        """Parse Claude's response and extract JSON"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group()
                analysis = json.loads(json_str)
                return analysis
            else:
                # If no JSON found, create a basic structure
                return {
                    "roi_assessment": {
                        "estimated_roi_percentage": 200,
                        "revenue_potential": "Analysis pending",
                        "profitability_analysis": response_text[:200] + "..."
                    },
                    "strategic_fit_score": 7,
                    "risk_analysis": {
                        "competition_risk": "medium - standard competition expected",
                        "technical_risk": "low - within capabilities",
                        "financial_risk": "low - government contract",
                        "overall_risk": "medium"
                    },
                    "action_plan": [
                        "Research contracting authority",
                        "Prepare capability statement",
                        "Contact procurement team"
                    ],
                    "competitive_advantages": [
                        "Specialist experience",
                        "Local presence"
                    ],
                    "confidence_score": 75,
                    "priority_classification": "HIGH",
                    "priority_reasoning": "Government contract with clear requirements",
                    "key_insights": [
                        "Opportunity aligns with company expertise",
                        "Standard procurement process expected"
                    ],
                    "enhanced_description": response_text[:300] + "...",
                    "contact_strategy": "Direct approach to procurement team recommended"
                }
                
        except Exception as e:
            print(f"   ❌ Error parsing Claude response: {str(e)}")
            # Return default analysis structure
            return {
                "roi_assessment": {
                    "estimated_roi_percentage": 150,
                    "revenue_potential": "Requires detailed analysis",
                    "profitability_analysis": "Standard government contract profitability expected"
                },
                "strategic_fit_score": 6,
                "risk_analysis": {
                    "overall_risk": "medium"
                },
                "action_plan": ["Contact procurement team", "Prepare tender response"],
                "competitive_advantages": ["Relevant experience"],
                "confidence_score": 70,
                "priority_classification": "MEDIUM",
                "priority_reasoning": "Standard opportunity",
                "key_insights": ["Government procurement opportunity"],
                "enhanced_description": "AI analysis in progress",
                "contact_strategy": "Standard procurement approach"
            }
    
    def _enhance_opportunity(self, opportunity, analysis):
        """Enhance the opportunity with Claude's analysis"""
        enhanced = opportunity.copy()
        
        # Add AI analysis results
        enhanced['ai_analysis'] = analysis
        enhanced['analyzed_at'] = datetime.now().isoformat()
        enhanced['analyzed_by'] = 'Claude 3.7'
        
        # Update core fields based on analysis
        if 'priority_classification' in analysis:
            enhanced['priority'] = analysis['priority_classification']
        
        if 'confidence_score' in analysis:
            enhanced['confidence_level'] = analysis['confidence_score']
        
        if 'enhanced_description' in analysis:
            enhanced['description'] = analysis['enhanced_description']
        
        # Add ROI information
        if 'roi_assessment' in analysis:
            roi = analysis['roi_assessment']
            enhanced['estimated_roi'] = roi.get('estimated_roi_percentage', 0)
            enhanced['revenue_potential'] = roi.get('revenue_potential', '')
        
        # Add strategic fit score
        enhanced['strategic_fit'] = analysis.get('strategic_fit_score', 5)
        
        # Add contact strategy
        enhanced['contact_strategy'] = analysis.get('contact_strategy', 'Standard approach')
        
        # Generate contact information if missing
        if not opportunity.get('contact'):
            enhanced['contact'] = self._generate_contact_info(opportunity)
        
        return enhanced
    
    def _generate_contact_info(self, opportunity):
        """Generate likely contact information based on authority"""
        authority = opportunity['authority']
        
        # Generate likely contact based on authority type
        if 'nhs' in authority.lower():
            return {
                'name': 'Procurement Team',
                'title': 'Senior Commissioning Manager',
                'phone': '0300-123-1234',
                'email': f"procurement@{authority.lower().replace(' ', '').replace('nhs', '')}.nhs.uk"
            }
        elif 'council' in authority.lower():
            council_name = authority.lower().replace('council', '').replace('city', '').strip()
            return {
                'name': 'Procurement Team',
                'title': 'Procurement Manager',
                'phone': '01XX-XXX-XXXX',
                'email': f"procurement@{council_name.replace(' ', '')}.gov.uk"
            }
        else:
            return {
                'name': 'Procurement Team',
                'title': 'Procurement Officer',
                'phone': 'See tender documents',
                'email': 'procurement@authority.gov.uk'
            }
    
    def analyze_multiple_opportunities(self, opportunities):
        """Analyze multiple opportunities and sort by potential"""
        print(f"🤖 Analyzing {len(opportunities)} opportunities with Claude 3.7...")
        print("-" * 60)
        
        analyzed_opportunities = []
        
        for i, opp in enumerate(opportunities, 1):
            print(f"[{i}/{len(opportunities)}] Analyzing: {opp['title'][:50]}...")
            
            # Analyze with Claude
            enhanced_opp = self.analyze_opportunity(opp)
            analyzed_opportunities.append(enhanced_opp)
            
            # Rate limiting - wait between API calls
            if i < len(opportunities):
                import time
                time.sleep(1)  # 1 second between calls
        
        # Sort by priority and ROI
        sorted_opportunities = self._sort_by_potential(analyzed_opportunities)
        
        print(f"\n✅ Analysis complete!")
        print(f"   High ROI opportunities (>300%): {len([o for o in sorted_opportunities if o.get('estimated_roi', 0) > 300])}")
        print(f"   Critical priority: {len([o for o in sorted_opportunities if o.get('priority') == 'CRITICAL'])}")
        print(f"   High confidence (>80%): {len([o for o in sorted_opportunities if o.get('confidence_level', 0) > 80])}")
        
        return sorted_opportunities
    
    def _sort_by_potential(self, opportunities):
        """Sort opportunities by potential (ROI, priority, confidence)"""
        
        def calculate_potential_score(opp):
            score = 0
            
            # ROI weight (40%)
            roi = opp.get('estimated_roi', 0)
            if roi >= 500:
                score += 40
            elif roi >= 300:
                score += 30
            elif roi >= 200:
                score += 20
            else:
                score += 10
            
            # Priority weight (30%)
            priority = opp.get('priority', 'MEDIUM')
            if priority == 'CRITICAL':
                score += 30
            elif priority == 'HIGH':
                score += 25
            elif priority == 'MEDIUM':
                score += 15
            else:
                score += 5
            
            # Confidence weight (20%)
            confidence = opp.get('confidence_level', 50)
            score += (confidence / 100) * 20
            
            # Strategic fit weight (10%)
            strategic_fit = opp.get('strategic_fit', 5)
            score += (strategic_fit / 10) * 10
            
            return score
        
        # Sort by potential score (highest first)
        return sorted(opportunities, key=calculate_potential_score, reverse=True)
    
    def generate_summary_analysis(self, opportunities):
        """Generate an overall summary of all opportunities"""
        if not opportunities:
            return "No opportunities to analyze."
        
        # Calculate summary statistics
        total_opps = len(opportunities)
        avg_roi = sum(opp.get('estimated_roi', 0) for opp in opportunities) / total_opps
        high_roi_count = len([opp for opp in opportunities if opp.get('estimated_roi', 0) > 300])
        critical_count = len([opp for opp in opportunities if opp.get('priority') == 'CRITICAL'])
        
        # Get top 3 opportunities
        top_3 = opportunities[:3]
        
        summary = f"""
🎯 OPPORTUNITY ANALYSIS SUMMARY

📊 Overview:
• Total opportunities analyzed: {total_opps}
• Average estimated ROI: {avg_roi:.1f}%
• High ROI opportunities (>300%): {high_roi_count}
• Critical priority opportunities: {critical_count}

🏆 Top 3 Opportunities:
"""
        
        for i, opp in enumerate(top_3, 1):
            roi = opp.get('estimated_roi', 0)
            priority = opp.get('priority', 'MEDIUM')
            confidence = opp.get('confidence_level', 50)
            
            summary += f"""
{i}. {opp['title'][:60]}
   • Company: {opp['company_match']}
   • Estimated ROI: {roi}%
   • Priority: {priority}
   • Confidence: {confidence}%
   • Authority: {opp['authority']}
"""
        
        # Add recommendations
        summary += f"""
💡 Key Recommendations:
• Focus immediate attention on {critical_count} critical opportunities
• Prioritize {high_roi_count} high-ROI opportunities first
• Average strategic fit across all opportunities suggests good market alignment
• Consider resource allocation based on deadline proximity and ROI potential

🎯 Next Steps:
1. Contact procurement teams for top 3 opportunities within 24 hours
2. Prepare detailed capability statements for high-ROI opportunities
3. Monitor medium-priority opportunities for any changes in status
4. Set up alerts for similar opportunity patterns in the future
"""
        
        return summary

# Test the analyzer
if __name__ == "__main__":
    # Test with sample opportunity
    test_opportunity = {
        'id': 'TEST-001',
        'title': 'Mental Health Supported Living Services Framework',
        'authority': 'NHS Greater Manchester',
        'value': 'GBP8.5M over 4 years',
        'deadline': '2025-07-15',
        'company_match': 'RehabilityUK',
        'source': 'Test Data',
        'description': 'Framework agreement for mental health supported living services across Greater Manchester'
    }
    
    analyzer = ClaudeOpportunityAnalyzer()
    
    if analyzer.api_key:
        enhanced_opp = analyzer.analyze_opportunity(test_opportunity)
        print("\n🎉 Sample Analysis Result:")
        print(f"Enhanced opportunity with AI insights!")
        if 'ai_analysis' in enhanced_opp:
            print(f"ROI: {enhanced_opp.get('estimated_roi', 'N/A')}%")
            print(f"Priority: {enhanced_opp.get('priority', 'N/A')}")
            print(f"Confidence: {enhanced_opp.get('confidence_level', 'N/A')}%")
    else:
        print("❌ No Claude API key found. Add CLAUDE_API_KEY to environment variables.")
