# main.py
"""
Main entry point for AutoRevenue Enterprise Intelligence v10.0.
This script is intended to be called by the scheduler (e.g., GitHub Actions).
"""
import logging
import os
import sys

# Add project root to Python path to allow direct imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from core_engine import run_system
from config import GITHUB_WORKSPACE, GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH

logger = logging.getLogger(__name__)

def setup_environment_for_github_actions():
    """
    Handles environment setup specific to GitHub Actions,
    such as creating credentials files from secrets.
    """
    if os.getenv("CI") and os.getenv("GITHUB_ACTIONS") == "true":
        logger.info("Running in GitHub Actions environment. Setting up credentials from secrets.")
        
        google_creds_content = os.getenv("GOOGLE_CREDENTIALS_JSON_CONTENT")
        google_token_content = os.getenv("GOOGLE_TOKEN_JSON_CONTENT")

        creds_path = os.path.join(GITHUB_WORKSPACE, GOOGLE_CREDENTIALS_PATH)
        token_path = os.path.join(GITHUB_WORKSPACE, GOOGLE_TOKEN_PATH)
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)

        if google_creds_content:
            try:
                with open(creds_path, 'w') as f:
                    f.write(google_creds_content)
                logger.info(f"Successfully wrote GOOGLE_CREDENTIALS_JSON_CONTENT to {creds_path}")
            except IOError as e:
                logger.error(f"Failed to write GOOGLE_CREDENTIALS_JSON_CONTENT to {creds_path}: {e}")
        else:
            logger.warning("GOOGLE_CREDENTIALS_JSON_CONTENT secret not found. OAuth might fail if credentials.json is needed.")

        if google_token_content:
            try:
                with open(token_path, 'w') as f:
                    f.write(google_token_content)
                logger.info(f"Successfully wrote GOOGLE_TOKEN_JSON_CONTENT to {token_path}")
            except IOError as e:
                logger.error(f"Failed to write GOOGLE_TOKEN_JSON_CONTENT to {token_path}: {e}")
        else:
            logger.warning("GOOGLE_TOKEN_JSON_CONTENT secret not found. OAuth will likely require interactive auth if token.json is not valid or present.")
    else:
        logger.info("Not running in GitHub Actions or CI env var not set. Assuming local setup for credentials.")
        # For local: ensure credentials.json exists and token.json will be created/used.
        # Ensure data/templates directories exist
        for dirname in ["data", "templates"]:
            dirpath = os.path.join(GITHUB_WORKSPACE, dirname)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath)
                logger.info(f"Created directory: {dirpath}")
        # Create a dummy template if it doesn't exist for local test
        dummy_template_path = os.path.join(GITHUB_WORKSPACE, "templates/email_report_template.html")
        if not os.path.exists(dummy_template_path):
            with open(dummy_template_path, "w") as f:
                f.write("<h1>Test Report: {{ company_name }}</h1><p>{{ report_date }}</p>{% for opp in opportunities %}<p>{{ opp.tender_title }}</p>{% else %}<p>No opportunities.</p>{% endfor %}")


if __name__ == "__main__":
    # Basic logging setup for main script before core_engine takes over
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    logger.info("AutoRevenue Enterprise Intelligence v10.0 - Main Process Starting.")
    
    # Setup environment (handles GitHub secrets if in Actions)
    setup_environment_for_github_actions()
    
    # Run the main system logic
    try:
        run_system()
    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main process: {e}", exc_info=True)
        sys.exit(1) # Exit with error code for CI
    
    logger.info("AutoRevenue Enterprise Intelligence v10.0 - Main Process Finished.")
    sys.exit(0)
