# discord_sender.py
"""
Simple Discord webhook integration for AutoRevenue alerts
100% free alternative to email notifications
"""
import os
import requests
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

def send_discord_message(webhook_url: str, title: str, message: str, 
                         color: int = 0x3498db, fields: Optional[List[Dict[str, str]]] = None) -> bool:
    """
    Send a message to Discord using a webhook.
    
    Args:
        webhook_url: Discord webhook URL
        title: Message title
        message: Message body
        color: Embed color (in hex)
        fields: Optional list of field dictionaries with name and value keys
    
    Returns:
        True if message was sent successfully, False otherwise
    """
    if not webhook_url:
        logger.error("No Discord webhook URL provided")
        return False
    
    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": datetime.now().isoformat(),
        "footer": {
            "text": f"AutoRevenue Enterprise v10.0"
        }
    }
    
    # Add fields if provided
    if fields:
        embed["fields"] = fields
    
    data = {
        "embeds": [embed]
    }
    
    try:
        response = requests.post(
            webhook_url, 
            data=json.dumps(data),
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 204:
            logger.info(f"Discord message sent successfully: {title}")
            return True
        else:
            logger.error(f"Failed to send Discord message: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Discord message: {str(e)}")
        return False

def send_opportunity_alerts(webhook_url: str, company_name: str, opportunities: List[Dict[str, Any]]) -> bool:
    """
    Send opportunity alerts for a specific company.
    
    Args:
        webhook_url: Discord webhook URL
        company_name: Name of the company
        opportunities: List of opportunity dictionaries
    
    Returns:
        True if message was sent successfully, False otherwise
    """
    if not opportunities:
        title = f"No New Opportunities - {company_name}"
        message = f"No new relevant opportunities found for {company_name} in the latest scan."
        return send_discord_message(webhook_url, title, message, 0x95a5a6)  # Grey color
    
    title = f"🚨 {len(opportunities)} New Opportunities Found - {company_name}"
    message = f"**Scan Time:** {datetime.now().strftime('%d %B %Y, %H:%M')}\n\n"
    
    # Create fields for each opportunity
    fields = []
    for i, opp in enumerate(opportunities[:10]):  # Limit to 10 opportunities to avoid Discord limits
        fields.append({
            "name": f"{i+1}. {opp['tender_title']}",
            "value": (
                f"**Score:** {opp['analysis']['scores']['overall']:.1f}/100\n"
                f"**Value:** {opp.get('analysis', {}).get('parsed_value', 'N/A')}\n"
                f"**Priority:** {opp['analysis'].get('resource_recommendation', 'N/A')}\n"
                f"**URL:** [View Tender]({opp['tender_url']})"
            )
        })
    
    if len(opportunities) > 10:
        message += f"*Showing top 10 of {len(opportunities)} opportunities*\n\n"
    
    # Color code based on highest opportunity score
    best_score = max([opp['analysis']['scores']['overall'] for opp in opportunities])
    if best_score >= 80:
        color = 0x2ecc71  # Green
    elif best_score >= 60:
        color = 0xf39c12  # Orange
    else:
        color = 0x3498db  # Blue
        
    return send_discord_message(webhook_url, title, message, color, fields)

def send_system_startup(webhook_url: str) -> bool:
    """Send system startup notification."""
    title = "🚀 AutoRevenue System Started"
    message = (
        f"**System Version:** Enterprise Intelligence v10.0\n"
        f"**Start Time:** {datetime.now().strftime('%d %B %Y, %H:%M')}\n"
        f"**Mode:** Automated Monitoring\n\n"
        f"System will scan for opportunities every 10 minutes and send alerts automatically."
    )
    return send_discord_message(webhook_url, title, message, 0x3498db)

def send_error_alert(webhook_url: str, error_message: str) -> bool:
    """Send error notification."""
    title = "⚠️ AutoRevenue System Error"
    message = (
        f"**Error Time:** {datetime.now().strftime('%d %B %Y, %H:%M')}\n"
        f"**Error Details:** {error_message}\n\n"
        f"System will attempt to continue monitoring. Check GitHub Actions for details."
    )
    return send_discord_message(webhook_url, title, message, 0xe74c3c)  # Red color

if __name__ == "__main__":
    # Test the Discord sender if run directly
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        send_system_startup(webhook_url)
        print("Test message sent to Discord. Check your channel!")
    else:
        print("DISCORD_WEBHOOK_URL environment variable not set.")
