# core_engine.py
"""
Main system architecture for AutoRevenue Enterprise Intelligence v10.0.
Orchestrates data acquisition, analysis, and reporting.
"""
import logging
import time
import os
from data_acquisition import run_all_scanners
from intelligence_analyzer import analyze_tenders_for_companies
from reporting import send_reports
from config import LOG_LEVEL
from discord_sender import send_opportunity_alerts, send_system_startup, send_error_alert

logger = logging.getLogger(__name__)

class SystemOrchestrator:
    def __init__(self):
        self.configure_logging()
        logger.info("AutoRevenue Enterprise Intelligence v10.0 - System Orchestrator Initialized.")

    def configure_logging(self):
        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
            format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        # Silence excessively verbose loggers from libraries if necessary
        logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
        logging.getLogger("google.auth.transport.requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        
    def run_cycle(self):
        """Executes one full cycle of the system: scan, analyze, report."""
        logger.info("Starting new intelligence cycle...")
        start_time = time.time()

        # 1. Data Acquisition
        logger.info("Phase 1: Acquiring new tender data...")
        try:
            new_tenders = run_all_scanners()
            if not new_tenders:
                logger.info("No new tenders found in this cycle.")
                # Optionally, still send a "no updates" report or handle as needed
            else:
                logger.info(f"Acquired {len(new_tenders)} new tenders.")
        except Exception as e:
            logger.error(f"Critical error during data acquisition phase: {e}", exc_info=True)
            # Depending on severity, might halt or try to proceed if some data was acquired.
            # For now, we'll assume if this fails, we can't proceed.
            return 

        # 2. Intelligence Analysis
        # This step is only meaningful if new_tenders were found.
        analyzed_data_by_company = {} # Initialize to ensure it's defined
        if new_tenders:
            logger.info("Phase 2: Analyzing acquired tenders...")
            try:
                analyzed_data_by_company = analyze_tenders_for_companies(new_tenders)
                logger.info("Tender analysis complete.")
                for company, reports in analyzed_data_by_company.items():
                    logger.info(f"Found {len(reports)} relevant opportunities for {company}.")
            except Exception as e:
                logger.error(f"Critical error during intelligence analysis phase: {e}", exc_info=True)
                # If analysis fails, we might not be able to report.
                return
        else:
            logger.info("Skipping analysis phase as no new tenders were acquired.")
            # Initialize empty reports for companies so they get a "no updates" email if desired
            from config import COMPANY_PROFILES
            for company_name in COMPANY_PROFILES.keys():
                analyzed_data_by_company[company_name] = []

        # 3. Reporting
        logger.info("Phase 3: Generating and sending Discord alerts...")
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set. Cannot send alerts.")
        else:
            try:
        # First check if this is the first run (no alerts sent before)
                if not hasattr(self, '_discord_startup_sent'):
                    send_system_startup(webhook_url)
                    self._discord_startup_sent = True
            
        # Send alerts for each company
                alerts_sent = 0
                for company_name, opportunities in analyzed_data_by_company.items():
                    if send_opportunity_alerts(webhook_url, company_name, opportunities):
                        alerts_sent += 1
                
                logger.info(f"Discord alerts sent: {alerts_sent}")
                logger.info("Reporting phase complete.")
            except Exception as e:
                logger.error(f"Critical error during reporting phase: {e}", exc_info=True)
        # Try to send error alert
                try:
                    send_error_alert(webhook_url, str(e))
                except:
                    pass
            # Log error, but cycle is considered complete.

        end_time = time.time()
        logger.info(f"Intelligence cycle completed in {end_time - start_time:.2f} seconds.")

def run_system():
    """Initializes and runs the system orchestrator."""
    orchestrator = SystemOrchestrator()
    orchestrator.run_cycle()

if __name__ == "__main__":
    # This allows running the core engine directly for testing.
    # In a scheduled environment (like GitHub Actions), `main.py` would call `run_system()`.
    print("Running AutoRevenue Enterprise Intelligence v10.0 (Core Engine Test)...")
    # Ensure data directory exists for local tests
    import os
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists("templates"): # Also for reporting
        os.makedirs("templates")
        # Create a dummy template if it doesn't exist for local test
        if not os.path.exists("templates/email_report_template.html"):
            with open("templates/email_report_template.html", "w") as f:
                f.write("<h1>Test Report: {{ company_name }}</h1><p>{{ report_date }}</p>{% for opp in opportunities %}<p>{{ opp.tender_title }}</p>{% else %}<p>No opportunities.</p>{% endfor %}")

    run_system()
    print("Core Engine Test Run Finished.")
