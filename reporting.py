# reporting.py
"""
Handles professional email reporting with HTML templates and data visualization.
Uses Google OAuth for sending emails.
"""
import logging
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import os.path
import datetime
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from jinja2 import Environment, FileSystemLoader

from config import (
    EMAIL_SENDER, EMAIL_RECIPIENTS, GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH, EMAIL_SUBJECT_PREFIX, GITHUB_WORKSPACE
)
# from intelligence_analyzer import CompanyProfile # If needed for typing

logger = logging.getLogger(__name__)

# --- Google OAuth Setup ---
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    """Authenticates and returns a Gmail API service instance."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    
    # Resolve paths correctly, especially in GitHub Actions
    token_path = os.path.join(GITHUB_WORKSPACE, GOOGLE_TOKEN_PATH)
    creds_path = os.path.join(GITHUB_WORKSPACE, GOOGLE_CREDENTIALS_PATH)

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e: # Handle malformed token file etc.
            logger.error(f"Error loading token from {token_path}: {e}. Will try to re-authenticate.")
            creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Google OAuth token refreshed.")
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}. Need to re-authenticate.")
                # Potentially delete token_path here if refresh fails consistently
                # For GitHub Actions, this means the stored token secret is bad.
                if os.path.exists(token_path):
                    try:
                        os.remove(token_path)
                        logger.info(f"Removed invalid token file: {token_path}")
                    except OSError as ose:
                        logger.error(f"Error removing token file {token_path}: {ose}")
                creds = None # Force re-auth if possible, or fail if not interactive
        
        # Only attempt InstalledAppFlow if credentials.json exists and we are in an environment
        # where user interaction MIGHT be possible (local).
        # In GitHub Actions, this flow will fail. Secrets must provide a valid token.json content.
        if not creds and os.path.exists(creds_path):
            # This flow is for interactive environments.
            # In GitHub Actions, `token.json` content should be provided as a secret.
            # The script should be adapted to load it from an env var if GOOGLE_TOKEN_JSON_CONTENT is set.
            if os.getenv("CI"): # Running in CI environment like GitHub Actions
                 logger.error("Cannot run interactive OAuth flow in CI. Ensure GOOGLE_TOKEN_JSON_CONTENT is set or token.json is valid.")
                 return None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                # Ensure redirect_uri is localhost for desktop app flow
                flow.redirect_uri = 'http://localhost:8080/' 
                creds = flow.run_local_server(port=8080) # Opens browser for auth
                logger.info("Google OAuth flow completed. Credentials obtained.")
            except Exception as e:
                logger.error(f"Error during InstalledAppFlow: {e}. Check credentials.json and ensure Gmail API is enabled.")
                return None
        
        # Save the credentials for the next run
        if creds:
            try:
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                logger.info(f"Google OAuth token saved to {token_path}")
            except IOError as e:
                logger.error(f"Could not save token to {token_path}: {e}")
        else:
            logger.error("Failed to obtain Google OAuth credentials.")
            return None
            
    try:
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail API service built successfully.")
        return service
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        return None

def create_message(sender: str, to: str, subject: str, message_html: str, attachments: Optional[List[Dict[str, Any]]]=None) -> Dict[str, str]:
    """Create a MIME message for sending.
    attachments: List of {'filename': 'chart.png', 'content': bytes, 'content_id': '<chart_cid>'}
    """
    message = MIMEMultipart('related') # Use 'related' for embedded images
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject

    msg_alternative = MIMEMultipart('alternative')
    message.attach(msg_alternative)

    # Plain text version (optional, good practice)
    # For simplicity, not generating a full plain text version from HTML here.
    # msg_text = MIMEText("Please view this email in an HTML-compatible client.", 'plain')
    # msg_alternative.attach(msg_text)

    msg_html = MIMEText(message_html, 'html')
    msg_alternative.attach(msg_html)

    if attachments:
        for attachment_data in attachments:
            try:
                image = MIMEImage(attachment_data['content'])
                image.add_header('Content-ID', attachment_data['content_id']) # e.g., <myimagecid>
                image.add_header('Content-Disposition', 'inline', filename=attachment_data['filename'])
                message.attach(image)
                logger.info(f"Attached image {attachment_data['filename']} with CID {attachment_data['content_id']}")
            except Exception as e:
                logger.error(f"Failed to attach image {attachment_data['filename']}: {e}")


    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

def send_message(service, user_id: str, message: Dict[str, str]) -> Optional[Dict]:
    """Send an email message.
    Args:
        service: Authorized Gmail API service instance.
        user_id: User's email address. The special value 'me' can be used to indicate the authenticated user.
        message: Message to be sent.
    Returns:
        Sent Pessage Parton success, None otherwise.
    """
    try:
        sent_message = service.users().messages().send(userId=user_id, body=message).execute()
        logger.info(f"Message Id: {sent_message['id']} sent successfully.")
        return sent_message
    except HttpError as error:
        logger.error(f'An HTTP error occurred while sending email: {error}')
    except Exception as e:
        logger.error(f'An unexpected error occurred while sending email: {e}')
    return None


# --- HTML Report Generation ---
def generate_html_report(company_name: str, analyzed_tenders: List[Dict[str, Any]]) -> str:
    """Generates an HTML report from analyzed tender data using Jinja2."""
    # Ensure GITHUB_WORKSPACE is used for template path if running in Actions
    template_dir = os.path.join(GITHUB_WORKSPACE, 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    try:
        template = env.get_template('email_report_template.html')
    except Exception as e:
        logger.error(f"Error loading HTML template: {e}. Using basic fallback.")
        # Basic fallback if template loading fails
        html_content = f"<h1>Procurement Opportunities for {company_name}</h1>"
        if not analyzed_tenders:
            html_content += "<p>No new relevant opportunities found in this run.</p>"
        else:
            for tender_report in analyzed_tenders:
                html_content += f"<h2>{tender_report['tender_title']} (Score: {tender_report['analysis']['scores']['overall']})</h2>"
                html_content += f"<p><a href='{tender_report['tender_url']}'>View Tender</a></p>"
                # Add more details
        return html_content


    report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Prepare data for the template
    template_data = {
        "company_name": company_name,
        "report_date": report_date,
        "opportunities": analyzed_tenders, # This is a list of analysis results for the company
        "has_opportunities": bool(analyzed_tenders)
    }
    
    html_output = template.render(template_data)
    return html_output


# --- Data Visualization (Conceptual) ---
def generate_summary_chart(analyzed_tenders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Generates a summary chart (e.g., distribution of scores) as bytes.
    Returns a dict: {'filename': 'summary.png', 'content': bytes, 'content_id': '<chart_cid>'}
    This is conceptual. Matplotlib can be tricky in headless environments (like GitHub Actions).
    It might require `matplotlib.use('Agg')`.
    """
    if not analyzed_tenders:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg') # Use non-interactive backend, crucial for server environments
        import matplotlib.pyplot as plt
        import io

        scores = [opp['analysis']['scores']['overall'] for opp in analyzed_tenders]
        titles = [opp['tender_title'][:30]+"..." for opp in analyzed_tenders] # Shorten titles

        if not scores: return None

        fig, ax = plt.subplots(figsize=(10, max(5, len(scores)*0.5))) # Adjust height based on number of items
        
        # Horizontal bar chart for scores
        y_pos = range(len(titles))
        ax.barh(y_pos, scores, align='center', color='skyblue')
        ax.set_yticks(y_pos)
        ax.set_yticklabels(titles)
        ax.invert_yaxis()  # Highest scores at the top
        ax.set_xlabel('Relevance Score (0-100)')
        ax.set_title('Top Relevant Opportunities')
        
        plt.tight_layout() # Adjust layout to prevent labels from overlapping

        # Save to a bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        chart_bytes = buf.read()
        buf.close()
        plt.close(fig) # Close the figure to free memory

        logger.info("Summary chart generated successfully.")
        return {
            'filename': 'opportunity_summary_chart.png',
            'content': chart_bytes,
            'content_id': '<opportunity_summary_chart_cid>' # CID for embedding in HTML
        }

    except ImportError:
        logger.warning("Matplotlib not installed. Skipping chart generation.")
    except Exception as e:
        logger.error(f"Error generating summary chart: {e}", exc_info=True)
    return None


def send_reports(analyzed_data_by_company: Dict[str, List[Dict[str, Any]]]):
    """
    Generates and sends email reports for each company.
    analyzed_data_by_company: Dict where key is company name, value is list of their analyzed tenders.
    """
    gmail_service = get_gmail_service()
    if not gmail_service:
        logger.error("Failed to get Gmail service. Cannot send reports.")
        return

    if not EMAIL_SENDER:
        logger.error("EMAIL_SENDER not configured. Cannot send reports.")
        return

    for company_name, company_tender_analyses in analyzed_data_by_company.items():
        recipient_email = EMAIL_RECIPIENTS.get(company_name)
        if not recipient_email:
            logger.warning(f"No recipient email configured for {company_name}. Skipping report.")
            continue

        logger.info(f"Preparing report for {company_name} to be sent to {recipient_email}...")
        
        # Generate chart (optional)
        chart_attachment_data = None
        if company_tender_analyses: # Only generate chart if there are opportunities
            chart_attachment_data = generate_summary_chart(company_tender_analyses)
        
        attachments = []
        if chart_attachment_data:
            attachments.append(chart_attachment_data)

        # Generate HTML content
        html_content = generate_html_report(company_name, company_tender_analyses)
        
        subject = f"{EMAIL_SUBJECT_PREFIX} {company_name} - {len(company_tender_analyses)} Relevant Opportunities Found"
        if not company_tender_analyses:
            subject = f"{EMAIL_SUBJECT_PREFIX} {company_name} - No New High-Priority Opportunities"

        message_mime = create_message(EMAIL_SENDER, recipient_email, subject, html_content, attachments=attachments)
        
        send_message(gmail_service, 'me', message_mime)
        logger.info(f"Report for {company_name} sent to {recipient_email}.")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Reporting module test run...")

    # Create dummy data for testing reporting
    dummy_ezzi_uk_analysis = [
        {
            "tender_id": "DUMMY001", "tender_title": "Major Social Housing Contract", "tender_url": "http://example.com/tender1",
            "analysis": {
                "scores": {"overall": 85.0, "keyword_match": 9, "value_tier": 10, "company_fit": 8, "urgency": 7},
                "parsed_value": 1750000.0,
                "swot": {"strengths": ["Relevant service: Social housing management"], "weaknesses": [], "opportunities": ["Bid for contract"], "threats": ["Tight deadline"]},
                "partnership_suggestions": [],
                "resource_recommendation": "High Priority: Allocate senior bid team.",
                "bid_timing": "Closing Date: XYZ. Days Left: 25.",
                "competitive_landscape": "Standard competition expected.",
                "contract_patterns": "Monitor for more from this buyer."
            }
        }
    ]
    dummy_rehability_uk_analysis = [
         {
            "tender_id": "DUMMY002", "tender_title": "Supported Living Services", "tender_url": "http://example.com/tender2",
            "analysis": {
                "scores": {"overall": 92.0, "keyword_match": 10, "value_tier": 8, "company_fit": 9, "urgency": 9},
                "parsed_value": 750000.0,
                "swot": {"strengths": ["Relevant service: Supported living"], "weaknesses": [], "opportunities": ["Bid for contract"], "threats": ["Very Urgent"]},
                "partnership_suggestions": ["Consider EzziUK if housing component is large."],
                "resource_recommendation": "High Priority: Allocate senior bid team.",
                "bid_timing": "Closing Date: ABC. Days Left: 8.",
                "competitive_landscape": "Specialist providers likely.",
                "contract_patterns": "Check NHS portal history."
            }
        }
    ]
    
    test_analyzed_data = {
        "EzziUK": dummy_ezzi_uk_analysis,
        "RehabilityUK": dummy_rehability_uk_analysis
        # "NonExistentCompany": [] # To test no recipient case
    }

    # Set up dummy environment variables for local testing of email sending
    # In a real scenario, these would be in .env or system environment
    # Ensure you have credentials.json and a valid token.json (after first auth run)
    # Or provide their content as GitHub Secrets in Actions.
    if not os.getenv("GMAIL_SENDER_ADDRESS"):
        print("Warning: GMAIL_SENDER_ADDRESS not set. Email sending might fail or use placeholders.")
        # os.environ["GMAIL_SENDER_ADDRESS"] = "your_email@gmail.com" # For local test
    if not os.getenv("EZZIUK_RECIPIENT_EMAIL"):
         print("Warning: EZZIUK_RECIPIENT_EMAIL not set.")
        # os.environ["EZZIUK_RECIPIENT_EMAIL"] = "recipient1@example.com"
    if not os.getenv("REHABILITYUK_RECIPIENT_EMAIL"):
         print("Warning: REHABILITYUK_RECIPIENT_EMAIL not set.")
        # os.environ["REHABILITYUK_RECIPIENT_EMAIL"] = "recipient2@example.com"

    # Create dummy templates folder and file
    if not os.path.exists("templates"):
        os.makedirs("templates")
    if not os.path.exists("templates/email_report_template.html"):
        with open("templates/email_report_template.html", "w") as f:
            f.write("""<!DOCTYPE html>
<html>
<head><title>Procurement Report for {{ company_name }}</title></head>
<body>
    <h1>Procurement Opportunities for {{ company_name }}</h1>
    <p>Report generated on: {{ report_date }}</p>
    {% if not has_opportunities %}
        <p>No new high-priority opportunities found in this run that match your profile above the threshold.</p>
    {% else %}
        {% if opportunities[0].analysis.scores.overall > 0 %} {# Check if chart data might exist #}
            <p>Summary Chart:</p>
            <img src="cid:opportunity_summary_chart_cid" alt="Opportunity Summary Chart" />
            <hr>
        {% endif %}
        {% for opp in opportunities %}
            <h2>{{ opp.tender_title }} (Score: {{ opp.analysis.scores.overall }})</h2>
            <p><strong>URL:</strong> <a href="{{ opp.tender_url }}">{{ opp.tender_url }}</a></p>
            <p><strong>Source:</strong> {{ opp.tender_source if opp.tender_source else "N/A" }}</p>
            <p><strong>Parsed Value:</strong> {{ opp.analysis.parsed_value if opp.analysis.parsed_value else "N/A" }}</p>
            <p><strong>Closing Date:</strong> {{ opp.tender_closing_date if opp.tender_closing_date else "N/A" }}</p>
            
            <h3>Analysis Highlights:</h3>
            <ul>
                <li><strong>Overall Score:</strong> {{ opp.analysis.scores.overall }}/100
                    (Keyword: {{ opp.analysis.scores.keyword_match }}/10,
                     Value: {{ opp.analysis.scores.value_tier }}/10,
                     Fit: {{ opp.analysis.scores.company_fit }}/10,
                     Urgency: {{ opp.analysis.scores.urgency }}/10)
                </li>
                <li><strong>Resource Recommendation:</strong> {{ opp.analysis.resource_recommendation }}</li>
                <li><strong>Bid Timing Advice:</strong> {{ opp.analysis.bid_timing }}</li>
                {% if opp.analysis.swot %}
                <li><strong>SWOT (Strengths):</strong> {{ opp.analysis.swot.strengths|join(', ') }}</li>
                <li><strong>SWOT (Weaknesses):</strong> {{ opp.analysis.swot.weaknesses|join(', ') }}</li>
                <li><strong>SWOT (Opportunities):</strong> {{ opp.analysis.swot.opportunities|join(', ') }}</li>
                <li><strong>SWOT (Threats):</strong> {{ opp.analysis.swot.threats|join(', ') }}</li>
                {% endif %}
                {% if opp.analysis.partnership_suggestions %}
                <li><strong>Partnership Suggestions:</strong> {{ opp.analysis.partnership_suggestions|join('; ') }}</li>
                {% endif %}
            </ul>
            <hr>
        {% endfor %}
    {% endif %}
    <p><em>This is an automated report from AutoRevenue Enterprise Intelligence v10.0.</em></p>
</body>
</html>""")
    # This command may require GOOGLE_APPLICATION_CREDENTIALS or similar for auth in some cases.
    # For user auth (OAuth2), it relies on credentials.json and token.json.
    # For GitHub Actions, these files' contents must be passed as secrets.
    send_reports(test_analyzed_data)

    logger.info("Reporting module test run finished.")
