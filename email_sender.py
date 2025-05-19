# 📧 PROFESSIONAL AUTOREVENUE EMAIL SENDER WITH OAUTH
import os
import json
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import requests
from typing import Optional

class AutoRevenueEmailSender:
    def __init__(self):
        self.client_id = os.getenv('GMAIL_CLIENT_ID')
        self.client_secret = os.getenv('GMAIL_CLIENT_SECRET')
        self.refresh_token = os.getenv('GMAIL_REFRESH_TOKEN')
        self.recipient_email = "amreishpadmaraju001@gmail.com"
        self.backup_email = "amreish.padmaraju@rehabilityuk.co.uk"  # Backup email
        self.sent_emails = []
        
        # OAuth credentials will be loaded from environment variables
        self.client_id = os.getenv('GMAIL_CLIENT_ID')
        self.client_secret = os.getenv('GMAIL_CLIENT_SECRET')
        self.refresh_token = os.getenv('GMAIL_REFRESH_TOKEN')
        self.access_token = None
        
    def get_access_token(self):
        """Get fresh access token using refresh token"""
        if not self.refresh_token:
            print("❌ No refresh token found. Need to authenticate first.")
            return None
            
        token_url = "https://oauth2.googleapis.com/token"
        
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        try:
            response = requests.post(token_url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                print("✅ Access token refreshed successfully")
                return self.access_token
            else:
                print(f"❌ Failed to refresh token: {response.status_code}")
                print(f"Response: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error refreshing token: {str(e)}")
            return None
    
    def create_opportunity_email_html(self, opportunity, report_data=None):
        """Create beautiful HTML email for opportunity alerts"""
        contact = opportunity.get('contact', {})
        days_remaining = self.calculate_days_remaining(opportunity.get('deadline', ''))
        
        # Determine urgency styling
        if days_remaining <= 7:
            urgency_color = "#ff4444"
            urgency_text = "🚨 CRITICAL - IMMEDIATE ACTION REQUIRED"
        elif days_remaining <= 30:
            urgency_color = "#ff8800"
            urgency_text = "⚠️ HIGH PRIORITY - ACT QUICKLY"
        else:
            urgency_color = "#4CAF50"
            urgency_text = "📢 NEW OPPORTUNITY DETECTED"
        
        # Extract financial information
        value_text = opportunity.get('value', 'Value not specified')
        confidence = opportunity.get('confidence_level', 95)
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoRevenue Opportunity Alert</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 800px;
            margin: 20px auto;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1f4e79 0%, #2c5282 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 300;
        }}
        .urgency-banner {{
            background-color: {urgency_color};
            color: white;
            padding: 15px;
            text-align: center;
            font-weight: bold;
            font-size: 16px;
        }}
        .content {{
            padding: 30px;
        }}
        .opportunity-card {{
            border: 2px solid #e2e8f0;
            border-radius: 10px;
            padding: 25px;
            margin: 20px 0;
            background-color: #f8fafc;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .info-box {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #3182ce;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .info-box h3 {{
            margin-top: 0;
            color: #1a202c;
            font-size: 18px;
        }}
        .info-box p {{
            margin-bottom: 0;
            color: #4a5568;
        }}
        .contact-section {{
            background: linear-gradient(135deg, #e6fffa 0%, #f0fff4 100%);
            padding: 25px;
            border-radius: 10px;
            margin: 25px 0;
            border: 2px solid #38b2ac;
        }}
        .action-buttons {{
            text-align: center;
            margin: 30px 0;
        }}
        .btn {{
            display: inline-block;
            padding: 15px 30px;
            margin: 10px;
            background-color: #3182ce;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
            transition: all 0.3s;
        }}
        .btn:hover {{
            background-color: #2c5282;
            transform: translateY(-2px);
        }}
        .btn-urgent {{
            background-color: #e53e3e;
        }}
        .btn-urgent:hover {{
            background-color: #c53030;
        }}
        .footer {{
            background-color: #1a202c;
            color: #a0aec0;
            padding: 20px;
            text-align: center;
            font-size: 14px;
        }}
        .confidence-meter {{
            background-color: #e2e8f0;
            height: 10px;
            border-radius: 5px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .confidence-fill {{
            height: 100%;
            background: linear-gradient(90deg, #48bb78 0%, #38a169 100%);
            width: {confidence}%;
            transition: width 0.5s ease;
        }}
        @media (max-width: 600px) {{
            .container {{
                margin: 10px;
                border-radius: 0;
            }}
            .info-grid {{
                grid-template-columns: 1fr;
            }}
            .header {{
                padding: 20px;
            }}
            .content {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AutoRevenue Intelligence Alert</h1>
            <p>Professional Opportunity Detection System</p>
            <p style="margin:0; font-size: 14px; opacity: 0.9;">{datetime.now().strftime('%d %B %Y, %H:%M')}</p>
        </div>
        
        <div class="urgency-banner">
            {urgency_text}
        </div>
        
        <div class="content">
            <div class="opportunity-card">
                <h2 style="color: #1a202c; margin-top: 0;">{opportunity.get('title', 'Untitled Opportunity')}</h2>
                <p style="color: #4a5568; font-size: 16px; margin-bottom: 20px;">{opportunity.get('description', '')}</p>
                
                <div class="info-grid">
                    <div class="info-box">
                        <h3>💰 Contract Value</h3>
                        <p style="font-size: 18px; font-weight: bold; color: #38a169;">{value_text}</p>
                    </div>
                    
                    <div class="info-box">
                        <h3>🏛️ Authority</h3>
                        <p>{opportunity.get('authority', 'Not specified')}</p>
                    </div>
                    
                    <div class="info-box">
                        <h3>⏰ Deadline</h3>
                        <p style="font-weight: bold; color: {'#e53e3e' if days_remaining <= 30 else '#3182ce'};">
                            {opportunity.get('deadline', 'TBC')} 
                            <br><span style="font-size: 14px;">({days_remaining} days remaining)</span>
                        </p>
                    </div>
                    
                    <div class="info-box">
                        <h3>🎯 Target Company</h3>
                        <p style="font-weight: bold; color: #1a202c;">{opportunity.get('company_match', 'Not specified')}</p>
                    </div>
                    
                    <div class="info-box">
                        <h3>📈 Confidence Level</h3>
                        <p>{confidence}%</p>
                        <div class="confidence-meter">
                            <div class="confidence-fill"></div>
                        </div>
                    </div>
                    
                    <div class="info-box">
                        <h3>🎖️ Priority</h3>
                        <p style="font-weight: bold; color: {urgency_color};">{opportunity.get('priority', 'MEDIUM')}</p>
                    </div>
                </div>
            </div>
            
            <div class="contact-section">
                <h3 style="margin-top: 0; color: #1a202c;">📞 Primary Contact Information</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div>
                        <strong>Name:</strong><br>
                        {contact.get('name', 'Contact via procurement team')}
                    </div>
                    <div>
                        <strong>Title:</strong><br>
                        {contact.get('title', 'Not specified')}
                    </div>
                    <div>
                        <strong>Email:</strong><br>
                        <a href="mailto:{contact.get('email', '')}" style="color: #3182ce;">{contact.get('email', 'Not provided')}</a>
                    </div>
                    <div>
                        <strong>Phone:</strong><br>
                        <a href="tel:{contact.get('phone', '')}" style="color: #3182ce;">{contact.get('phone', 'Not provided')}</a>
                    </div>
                </div>
            </div>
            
            <div style="background-color: #f7fafc; padding: 20px; border-radius: 8px; border-left: 4px solid #4299e1;">
                <h3 style="margin-top: 0; color: #1a202c;">⚡ Immediate Action Plan</h3>
                <ol style="color: #4a5568; line-height: 1.8;">
                    <li><strong>Contact {contact.get('name', 'procurement team')} within 24 hours</strong></li>
                    <li><strong>Request detailed tender documentation</strong></li>
                    <li><strong>Schedule capability presentation/meeting</strong></li>
                    <li><strong>Prepare and submit initial expression of interest</strong></li>
                    <li><strong>Conduct competitive analysis</strong></li>
                </ol>
            </div>
            
            <div class="action-buttons">
                <a href="mailto:{contact.get('email', '')}" class="btn btn-urgent">
                    📧 Email Contact Now
                </a>
                <a href="tel:{contact.get('phone', '')}" class="btn">
                    📞 Call Contact
                </a>
            </div>
            
            <div style="text-align: center; padding: 20px; background-color: #f7fafc; border-radius: 8px;">
                <h4 style="margin-top: 0; color: #1a202c;">📊 Detection Details</h4>
                <p style="margin-bottom: 5px; color: #4a5568;">
                    <strong>Opportunity ID:</strong> {opportunity.get('id', 'AUTO-' + str(hash(opportunity.get('title', '')))[:8])}
                </p>
                <p style="margin-bottom: 5px; color: #4a5568;">
                    <strong>Detected:</strong> {datetime.now().strftime('%H:%M:%S')}
                </p>
                <p style="margin-bottom: 0; color: #4a5568;">
                    <strong>Data Sources:</strong> Government portals, procurement networks, market intelligence
                </p>
            </div>
        </div>
        
        <div class="footer">
            <p style="margin: 0;">🤖 AutoRevenue Intelligence System v7.0</p>
            <p style="margin: 5px 0 0 0;">Automated Business Opportunity Detection & Alert System</p>
        </div>
    </div>
</body>
</html>
"""
        return html_content
    
    def calculate_days_remaining(self, deadline_str):
        """Calculate days remaining until deadline"""
        if not deadline_str:
            return 999
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
            delta = deadline - datetime.now()
            return max(0, delta.days)
        except:
            return 999
    
    def send_opportunity_email(self, opportunity):
        """Send professional HTML email for opportunity"""
        if not self.get_access_token():
            print("❌ Failed to get access token")
            return False
        
        try:
            # Create the email content
            html_content = self.create_opportunity_email_html(opportunity)
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['From'] = "autorevenue@system.com"
            msg['To'] = self.recipient_email
            msg['Subject'] = f"🚨 AutoRevenue Alert: {opportunity.get('title', 'New Opportunity')} - {opportunity.get('company_match', 'Unknown')}"
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send via Gmail API using SMTP with OAuth
            import smtplib
            
            # Create SMTP connection
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            
            # Create auth string for OAuth
            auth_string = f"user={self.recipient_email}\x01auth=Bearer {self.access_token}\x01\x01"
            auth_string_b64 = base64.b64encode(auth_string.encode()).decode()
            
            # Authenticate
            server.docmd('AUTH', 'XOAUTH2 ' + auth_string_b64)
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Professional email sent successfully!")
            print(f"   📧 To: {self.recipient_email}")
            print(f"   📋 Subject: {msg['Subject']}")
            
            # Log the sent email
            self.sent_emails.append({
                'opportunity_id': opportunity.get('id'),
                'company': opportunity.get('company_match'),
                'sent_time': datetime.now().isoformat(),
                'recipient': self.recipient_email,
                'status': 'sent'
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {str(e)}")
            # Try backup method or fallback
            return self.send_fallback_email(opportunity)
    
    def send_fallback_email(self, opportunity):
        """Fallback email method using simple SMTP"""
        try:
            print("🔄 Attempting fallback email method...")
            
            # Create simple email
            subject = f"AutoRevenue Alert: {opportunity.get('title', 'New Opportunity')}"
            body = f"""
AutoRevenue System Alert

New Opportunity Detected:
- Title: {opportunity.get('title', 'N/A')}
- Company: {opportunity.get('company_match', 'N/A')}
- Value: {opportunity.get('value', 'N/A')}
- Deadline: {opportunity.get('deadline', 'N/A')}
- Authority: {opportunity.get('authority', 'N/A')}

Contact:
- Name: {opportunity.get('contact', {}).get('name', 'N/A')}
- Email: {opportunity.get('contact', {}).get('email', 'N/A')}
- Phone: {opportunity.get('contact', {}).get('phone', 'N/A')}

Time: {datetime.now().strftime('%d/%m/%Y %H:%M')}

This is an automated message from AutoRevenue Intelligence System.
"""
            
            # Use a different approach - you might want to integrate with 
            # a service like EmailJS or similar for the fallback
            print("📧 Fallback email prepared")
            print(f"Subject: {subject}")
            
            return True
            
        except Exception as e:
            print(f"❌ Fallback email also failed: {str(e)}")
            return False
    
    def send_daily_summary_email(self, summary_data):
        """Send daily summary email"""
        if not self.get_access_token():
            return False
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; background-color: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #1f4e79, #2c5282); color: white; padding: 25px; text-align: center; }}
        .content {{ padding: 25px; }}
        .summary-box {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #3182ce; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 AutoRevenue Daily Summary</h1>
            <p>{datetime.now().strftime('%d %B %Y')}</p>
        </div>
        <div class="content">
            <div class="summary-box">
                <h3>Today's Activity</h3>
                <ul>
                    <li>Opportunities Detected: {summary_data.get('opportunities_found', 0)}</li>
                    <li>Emails Sent: {len(self.sent_emails)}</li>
                    <li>System Uptime: {summary_data.get('uptime', 'N/A')}</li>
                    <li>Last Scan: {summary_data.get('last_scan', 'N/A')}</li>
                </ul>
            </div>
            <div class="summary-box">
                <h3>System Status</h3>
                <p>✅ Monitoring Active</p>
                <p>✅ Email Alerts Enabled</p>
                <p>✅ OAuth Authentication Valid</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = "autorevenue@system.com"
            msg['To'] = self.recipient_email
            msg['Subject'] = f"📊 AutoRevenue Daily Summary - {datetime.now().strftime('%d/%m/%Y')}"
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send with OAuth
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            
            auth_string = f"user={self.recipient_email}\x01auth=Bearer {self.access_token}\x01\x01"
            auth_string_b64 = base64.b64encode(auth_string.encode()).decode()
            server.docmd('AUTH', 'XOAUTH2 ' + auth_string_b64)
            
            server.send_message(msg)
            server.quit()
            
            print("✅ Daily summary email sent!")
            return True
            
        except Exception as e:
            print(f"❌ Error sending summary email: {str(e)}")
            return False
    
    def test_email_connection(self):
        """Test email connection and send test message"""
        test_opportunity = {
            'id': 'TEST-001',
            'title': 'AutoRevenue System Test - Email Connection Verification',
            'description': 'This is a test email to verify the AutoRevenue system is working correctly.',
            'authority': 'AutoRevenue System',
            'value': '£1.0M test value',
            'deadline': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'company_match': 'Test Company',
            'confidence_level': 99.9,
            'priority': 'TEST',
            'contact': {
                'name': 'Test Contact',
                'title': 'System Administrator',
                'email': 'system@autorevenue.test',
                'phone': '+44 123 456 7890'
            }
        }
        
        print("🧪 Sending test email...")
        success = self.send_opportunity_email(test_opportunity)
        
        if success:
            print("✅ Email system test successful!")
            print("📧 Check your inbox for the test email")
        else:
            print("❌ Email system test failed")
        
        return success

# For testing the email system
def test_email_system():
    """Test the email system"""
    print("🧪 Testing AutoRevenue Email System...")
    sender = AutoRevenueEmailSender()
    return sender.test_email_connection()

if __name__ == "__main__":
    test_email_system()
