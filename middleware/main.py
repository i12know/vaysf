# main.py

import os
import sys
import argparse
import time
import datetime
from typing import Optional
from loguru import logger
import schedule
from tenacity import retry, stop_after_attempt, wait_exponential
from config import Config, DATA_DIR

# Add parent directory to import path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from sync.manager import SyncManager
from config import Config

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the VAYSF middleware."""
    parser = argparse.ArgumentParser(description="Sports Fest 2025 ChMeetings Integration")
    subparsers = parser.add_subparsers(dest="command", help="Command to run", required=True)

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync data between systems")
    sync_parser.add_argument("--type", choices=["churches", "participants", "approvals", "validation", "full"],
                             default="full", help="Type of data to sync")

    # Sync-churches command (new)
    sync_churches_parser = subparsers.add_parser("sync-churches", help="Sync churches from Excel file")
    sync_churches_parser.add_argument("--file", default=os.path.join("data", "Church Application Form.xlsx"),
                                      help="Path to the church Excel file")

    # Group assignment command
    group_assignment_parser = subparsers.add_parser("assign-groups", 
                                             help="Create group assignments for people with church codes")
    group_assignment_parser.add_argument("--output", help="Output directory path", 
                                             default=DATA_DIR)

    # Config command
    config_parser = subparsers.add_parser("config", help="Configure system settings")
    config_parser.add_argument("--validate", action="store_true", help="Validate current configuration")

    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Run scheduled sync jobs")
    schedule_parser.add_argument("--interval", type=int, default=Config.SYNC_INTERVAL_MINUTES,
                                 help="Interval in minutes between sync jobs")
    schedule_parser.add_argument("--daemon", action="store_true", help="Run as daemon process")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test connectivity and functionality of systems")
    test_parser.add_argument("--system", choices=["chmeetings", "wordpress", "all"],
                             default="all", help="System to test")
    test_parser.add_argument("--test-type", choices=["connectivity", "churches", "email", "all"],
                             default="connectivity", help="Type of test to run (connectivity, churches, email, or all)")
    test_parser.add_argument("--test-email", default=os.getenv("TEST_EMAIL", "PastorBumble@gmail.com"),
                             help="Email address for email test")
                             
    return parser.parse_args()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def run_sync(manager: SyncManager, sync_type: str = "full") -> bool:
    """Run synchronization process with retry logic.

    Args:
        manager: SyncManager instance to use.
        sync_type: Type of sync to perform (churches, participants, approvals, validation, full).

    Returns:
        bool: True if successful, False otherwise.
    """
    logger.info(f"Running {sync_type} synchronization")
    try:
        if not manager.authenticate():
            logger.error("Authentication failed")
            return False
        if sync_type == "churches":
            excel_path = os.path.join("data", "Church Application Form.xlsx")
            if not os.path.exists(excel_path):
                logger.error(f"Excel file not found at {excel_path}")
                return False
            return manager.sync_churches_from_excel(excel_path)  # Fixed            
        elif sync_type == "participants":
            return manager.sync_participants()
        elif sync_type == "approvals":
            success1 = manager.generate_approvals()
            success2 = manager.sync_approvals_to_chmeetings()
            return success1 and success2
        elif sync_type == "validation":
            return manager.validate_data()
        elif sync_type == "full":
            stats = manager.run_full_sync()
            logger.info(f"Full sync completed with stats: {stats}")
            return True
        else:
            logger.error(f"Invalid sync type: {sync_type}")
            return False
    except Exception as e:
        logger.exception(f"Sync failed: {e}")
        return False

def validate_config() -> bool:
    """Validate system configuration."""
    logger.info("Validating configuration")
    valid = Config.validate()
    if valid:
        logger.info("Configuration is valid")
    else:
        logger.error("Configuration validation failed")
    return valid

def run_scheduled_sync(interval: int, daemon: bool = False) -> None:
    """Run sync jobs at scheduled intervals."""
    logger.info(f"Starting scheduled sync with {interval}-minute intervals")
    with SyncManager() as manager:
        schedule.every(interval).minutes.do(run_sync, manager=manager, sync_type="full")
        if daemon:
            logger.info("Running as daemon process")
            run_sync(manager, "full")  # Initial run
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(min(60, interval * 60))
                except KeyboardInterrupt:
                    logger.info("Scheduled sync interrupted by user")
                    break
                except Exception as e:
                    logger.exception(f"Scheduled sync error: {e}")
        else:
            logger.info("Running scheduled tasks once")
            schedule.run_all()

def test_connectivity(system: str = "all", test_type: str = "connectivity", test_email: str = "PastorBumble@gmail.com") -> bool:
    """Test connectivity and functionality to ChMeetings and/or WordPress."""
    logger.info(f"Testing {test_type} for {system}")
    success = True

    if system in ["chmeetings", "all"]:
        from chmeetings.backend_connector import ChMeetingsConnector
        logger.info("Testing ChMeetings functionality")
        try:
            with ChMeetingsConnector() as connector:
                if test_type in ["connectivity", "all"]:
                    if connector.authenticate():
                        logger.info("Successfully connected to ChMeetings")
                    else:
                        logger.error("Failed to connect to ChMeetings")
                        success = False
        except Exception as e:
            logger.error(f"ChMeetings test failed: {e}")
            success = False

    if system in ["wordpress", "all"]:
        from wordpress.frontend_connector import WordPressConnector
        logger.info("Testing WordPress functionality")
        try:
            with WordPressConnector() as connector:
                if test_type == "connectivity":
                    churches = connector.get_churches()
                    if churches is not None:
                        logger.info(f"Successfully connected to WordPress: Retrieved {len(churches)} churches")
                    else:
                        logger.error("Failed to connect to WordPress")
                        success = False
                elif test_type == "churches":
                    test_church = {
                        "church_name": "Test Church API",
                        "church_code": "API",
                        "pastor_name": "Pastor Test",
                        "pastor_email": "pastor@testchurch.org",
                        "pastor_phone": "555-123-4567",
                        "church_rep_name": "Rep Test",
                        "church_rep_email": "rep@testchurch.org",
                        "church_rep_phone": "555-987-6543",
                        "sports_ministry_level": 2
                    }
                    new_church = connector.create_church(test_church)
                    if new_church:
                        logger.info(f"Created church: {new_church.get('church_id')}")
                    else:
                        logger.error("Failed to create church")
                        success = False
                    church_by_code = connector.get_church_by_code("API")
                    if church_by_code:
                        logger.info(f"Retrieved church by code: {church_by_code['church_name']}")
                    else:
                        logger.error("Failed to get church by code")
                        success = False
                    update_data = {"church_name": "Updated Test Church API", "sports_ministry_level": 3}
                    updated_church = connector.update_church_by_code("API", update_data)
                    if updated_church:
                        logger.info(f"Updated church: {updated_church['church_name']}")
                    else:
                        logger.error("Failed to update church by code")
                        success = False
                elif test_type == "email":
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    email_data = {
                        "to": test_email,
                        "subject": "Test Email from Sports Fest API",
                        "message": f"""
                        <h2>Sports Fest Email Test</h2>
                        <p>This is a test email sent via the middleware.</p>
                        <p>Time of test: {current_time}</p>
                        """,
                        "from_email": "SportsFest Staff <info@sportsfest.vayhub.us>"
                    }
                    result = connector.send_email(**email_data)
                    if result.get("success", False):
                        logger.info(f"Email sent successfully to {test_email}")
                    else:
                        logger.error(f"Failed to send email: {result.get('message', 'Unknown error')}")
                        success = False
                elif test_type == "all":
                    churches = connector.get_churches()
                    if churches is not None:
                        logger.info(f"Successfully connected to WordPress: Retrieved {len(churches)} churches")
                    else:
                        logger.error("Failed to connect to WordPress")
                        success = False
                    test_church = {
                        "church_name": "Test Church API",
                        "church_code": "API",
                        "pastor_name": "Pastor Test",
                        "pastor_email": "pastor@testchurch.org",
                        "pastor_phone": "555-123-4567",
                        "church_rep_name": "Rep Test",
                        "church_rep_email": "rep@testchurch.org",
                        "church_rep_phone": "555-987-6543",
                        "sports_ministry_level": 2
                    }
                    new_church = connector.create_church(test_church)
                    if new_church:
                        logger.info(f"Created church: {new_church.get('church_id')}")
                    else:
                        logger.error("Failed to create church")
                        success = False
                    church_by_code = connector.get_church_by_code("API")
                    if church_by_code:
                        logger.info(f"Retrieved church by code: {church_by_code['church_name']}")
                    else:
                        logger.error("Failed to get church by code")
                        success = False
                    update_data = {"church_name": "Updated Test Church API", "sports_ministry_level": 3}
                    updated_church = connector.update_church_by_code("API", update_data)
                    if updated_church:
                        logger.info(f"Updated church: {updated_church['church_name']}")
                    else:
                        logger.error("Failed to update church by code")
                        success = False
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    email_data = {
                        "to": test_email,
                        "subject": "Test Email from Sports Fest API",
                        "message": f"""
                        <h2>Sports Fest Email Test</h2>
                        <p>This is a test email sent via the middleware.</p>
                        <p>Time of test: {current_time}</p>
                        """,
                        "from_email": "SportsFest Staff <info@sportsfest.vayhub.us>"
                    }
                    result = connector.send_email(**email_data)
                    if result.get("success", False):
                        logger.info(f"Email sent successfully to {test_email}")
                    else:
                        logger.error(f"Failed to send email: {result.get('message', 'Unknown error')}")
                        success = False
        except Exception as e:
            logger.error(f"WordPress test failed: {e}")
            success = False

    return success
    
def main() -> None:
    """Main entry point for the VAYSF middleware."""
    args = parse_args()
    logger.info(f"Executing command: {args.command}")

    if args.command == "sync":        
        manager = SyncManager()
        with manager:
            success = run_sync(manager, args.type)        
    elif args.command == "sync-churches":
        if not os.path.exists(args.file):
            logger.error(f"Excel file not found at {args.file}")
            success = False
        else:
            with SyncManager() as manager:
                success = manager.sync_churches_from_excel(args.file)  # Fixed
    elif args.command == "assign-groups":
        from group_assignment import export_people_with_church_codes
        success = export_people_with_church_codes()
        if success:
            logger.info(f"Group assignment file created successfully at: {success}")
            # Try to open the file for the user
            import platform
            import subprocess
            if platform.system() == 'Windows':
                os.startfile(success)
    elif args.command == "config":
        success = validate_config()
    elif args.command == "schedule":
        run_scheduled_sync(args.interval, args.daemon)
        success = True  # No exit until interrupted
    elif args.command == "test":
        success = test_connectivity(args.system, args.test_type, args.test_email)
    else:
        logger.error(f"Unknown command: {args.command}")
        success = False

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()