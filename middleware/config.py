# config.py
# version 1.01
import os
import platform
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from loguru import logger
import json
import datetime
from urllib.parse import urlparse
from pathlib import Path
import sys

# Load environment variables
load_dotenv()

# Base directories - Windows-compatible using Path for robustness
BASE_DIR = Path(__file__).parent.resolve()
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"

# Export settings - default to G:\VAYSF-data to share the files with Church Rep from my Google Drive 
DEFAULT_EXPORT_PATH_STR = r"G:\Shared drives\RP Google Drive\VAY\SportsFest\VAYSF-data"
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", DEFAULT_EXPORT_PATH_STR))

# Ensure directories exist with error handling
for directory in [LOG_DIR, DATA_DIR, TEMP_DIR, EXPORT_DIR]:
    try:
        directory.mkdir(exist_ok=True)
    except OSError as e:
        print(f"Failed to create directory {directory}: {e}")
        raise

# Configure logging (file and console)
log_file = LOG_DIR / f"sportsfest_{datetime.datetime.now().strftime('%Y%m%d')}.log"
logger.remove()  # Remove default handler
logger.add(log_file, rotation="1 day", retention="30 days", level="DEBUG", 
           format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
logger.add(sys.stdout, level="DEBUG", format="{time:HH:mm:ss} | {level} | {message}", colorize=True)

# Encryption setup
def get_or_create_key() -> bytes:
    """Generate or load encryption key from .key file."""
    key_file = BASE_DIR / ".key"
    try:
        if key_file.exists():
            return key_file.read_bytes()
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        if platform.system() == "Windows":
            os.system(f"icacls \"{key_file}\" /inheritance:r /grant:r \"%username%:R\"")
        logger.info(f"Generated new encryption key at {key_file}")
        return key
    except Exception as e:
        logger.error(f"Failed to manage encryption key: {e}")
        raise

FERNET_KEY = get_or_create_key()
fernet = Fernet(FERNET_KEY)

# Sport Type Constants: These should match the actual data entry form!!!
SPORT_TYPE = {
    # Team sports
    "BASKETBALL": "Basketball - Men Team",
    "VOLLEYBALL_MEN": "Volleyball - Men Team",
    "VOLLEYBALL_WOMEN": "Volleyball - Women Team",
    "BIBLE_CHALLENGE": "Bible Challenge - Mixed Team",
    
    # Racquet sports
    "BADMINTON": "Badminton",
    "PICKLEBALL": "Pickleball",
    "PICKLEBALL_35": "Pickleball 35+",
    "TABLE_TENNIS": "Table Tennis",
    "TENNIS": "Tennis",
    
    # Other events
    "TRACK_FIELD": "Track & Field",
    "TUG_OF_WAR": "Tug-of-war",
    "SCRIPTURE": "Scripture Memorization"
}

# Constants for sport selection states
SPORT_UNSELECTED = "Unselected/NA"
DEFAULT_SPORT = "default"

# Sport Category Classification
SPORT_CATEGORY = {
    "TEAM": "Team",
    "INDIVIDUAL": "Individual",
    "RACQUET": "Racquet"
}

# Classification of sports by category
SPORT_BY_CATEGORY = {
    SPORT_CATEGORY["TEAM"]: [
        SPORT_TYPE["BASKETBALL"],
        SPORT_TYPE["VOLLEYBALL_MEN"],
        SPORT_TYPE["VOLLEYBALL_WOMEN"],
        SPORT_TYPE["BIBLE_CHALLENGE"]
    ],
    SPORT_CATEGORY["RACQUET"]: [
        SPORT_TYPE["BADMINTON"],
        SPORT_TYPE["PICKLEBALL"],
        SPORT_TYPE["PICKLEBALL_35"],
        SPORT_TYPE["TABLE_TENNIS"],
        SPORT_TYPE["TENNIS"]
    ],
    SPORT_CATEGORY["INDIVIDUAL"]: [
        SPORT_TYPE["TRACK_FIELD"],
        SPORT_TYPE["TUG_OF_WAR"],
        SPORT_TYPE["SCRIPTURE"]
    ]
}

# Set of racquet sports for easy checking
RACQUET_SPORTS = set(SPORT_BY_CATEGORY[SPORT_CATEGORY["RACQUET"]])

# Sport Format Constants
SPORT_FORMAT = {
    "SINGLES": "Singles",
    "DOUBLES": "Doubles",
    "MIXED_DOUBLES": "Mixed Doubles",
    "TEAM": "Team"
}

# Gender Categories
GENDER = {
    "MEN": "Men",
    "WOMEN": "Women",
    "MIXED": "Mixed",
    "ANY": "Any"
}

# Format to Gender+Format Mapping
FORMAT_MAPPINGS = {
    "Men Single": (SPORT_FORMAT["SINGLES"], GENDER["MEN"]),
    "Women Single": (SPORT_FORMAT["SINGLES"], GENDER["WOMEN"]),
    "Men Double": (SPORT_FORMAT["DOUBLES"], GENDER["MEN"]),
    "Women Double": (SPORT_FORMAT["DOUBLES"], GENDER["WOMEN"]),
    "Mixed Double": (SPORT_FORMAT["DOUBLES"], GENDER["MIXED"])
}

# Self-disclosed membership question:
MEMBERSHIP_QUESTION = "Would the team's Senior Pastor say that you belong to his church?"

# Church Rep's check list for participant WITHOUT COMMA
CHECK_BOXES = {
    "1-IDENTITY": "1. Correct identity, gender, age range",
    "2-CONSENT": "2. Consent Form Signed by Self or Parents",
    "3-ACCOUNT": "3. Account created on Member Portal and logged in",
    "4-PHOTO_ID": "4. Valid Photo as ID for event check-in",
    "5-APPROVAL": "5. Approval from Pastor",
    "6-PAID": "6. Paid All Fees"
}
    
# Approval Status Constants
APPROVAL_STATUS = {
    "PENDING": "pending",                   ## Initial status for participants who have validation issues or incomplete requirements: NOT yet ready for pastoral approval.
    "VALIDATED": "validated",               ## Passed all technical validation checks. Their data is complete and valid according to the system rules
    "PENDING_APPROVAL": "pending_approval", ## Completed all required checklist items for Pastoral Approval and is now awaiting the pastor's decision
    "APPROVED": "approved",                 ## Set when a pastor explicitly approves a participant
    "DENIED": "denied"                      ## Set when a pastor explicitly denies a participant
}

# Validation Severity Constants
VALIDATION_SEVERITY = {
    "ERROR": "ERROR",
    "WARNING": "WARNING",
    "INFO": "INFO"
}

# Validation Status Constants
VALIDATION_STATUS = {
    "OPEN": "open",
    "RESOLVED": "resolved"
}

# Rule Level Constants (for validation)
RULE_LEVEL = {
    "INDIVIDUAL": "INDIVIDUAL",
    "TEAM": "TEAM",
    "CHURCH": "CHURCH",
    "TOURNAMENT": "TOURNAMENT"
}

# Sport-specific age restrictions
AGE_RESTRICTIONS = {
    "DEFAULT": {"min": 13, "max": 35},
    SPORT_TYPE["SCRIPTURE"]: {"min": 10, "max": 99},
    SPORT_TYPE["TUG_OF_WAR"]: {"min": 13, "max": 99},
    SPORT_TYPE["PICKLEBALL_35"]: {"min": 35, "max": 99}
}

def is_racquet_sport(sport: str) -> bool:
    """Check if a sport is a racquet sport.

    Args:
        sport (str): The sport name.

    Returns:
        bool: True if it's a racquet sport, False otherwise.
    """
    return sport in RACQUET_SPORTS

# Configuration class
class Config:
    """Configuration settings for VAYSF middleware."""
    # ChMeetings configuration
    CHM_API_URL = os.getenv("CHM_API_URL", "https://api.chmeetings.com")
    CHM_USERNAME = os.getenv("CHM_USERNAME")
    CHM_PASSWORD = os.getenv("CHM_PASSWORD")
    CHM_API_KEY = os.getenv("CHM_API_KEY")
    
    # WordPress configuration
    WP_URL = os.getenv("WP_URL")
    WP_API_KEY = os.getenv("WP_API_KEY")
    
    # Email configuration
    EMAIL_FROM = os.getenv("EMAIL_FROM", "info@vaysm.org")
    
    # Selenium configuration
    CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")  # Empty if using webdriver-manager
    USE_CHROME_HEADLESS = os.getenv("USE_CHROME_HEADLESS", "True").lower() == "true"
    CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", "")
    
    # Application settings
    # Default APP_ENV to "test" when running under pytest to avoid failing
    # configuration validation during imports. This allows the modules to be
    # imported without a populated .env when running the unit tests.
    APP_ENV = os.getenv(
        "APP_ENV",
        "test" if "pytest" in sys.argv[0] or "PYTEST_CURRENT_TEST" in os.environ else "development",
    )
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    TOKEN_EXPIRY_DAYS = int(os.getenv("TOKEN_EXPIRY_DAYS", 30))
    CHURCH_EXCEL_FILE = DATA_DIR / os.getenv("CHURCH_EXCEL_FILE", "Church Application Form.xlsx")
    APPROVED_GROUP_NAME = os.getenv("APPROVED_GROUP_NAME", "2025 Sports Fest")
    APPROVED_EXCEL_FILE = DATA_DIR / os.getenv("APPROVED_EXCEL_FILE", "group_import_approved_participants.xlsx")
    
    # Sync settings
    SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", 60))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 50))
    TEAM_PREFIX = os.getenv("TEAM_PREFIX", "Team")
    SPORTS_FEST_DATE = os.getenv("SPORTS_FEST_DATE", "2025-03-17")

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings."""
        required_vars = {
            "CHM_API_URL": cls.CHM_API_URL,
            "CHM_USERNAME": cls.CHM_USERNAME,
            "CHM_PASSWORD": cls.CHM_PASSWORD,
            "CHM_API_KEY": cls.CHM_API_KEY,
            "WP_URL": cls.WP_URL,
            "WP_API_KEY": cls.WP_API_KEY,
            "EMAIL_FROM": cls.EMAIL_FROM
        }
        
        missing = [key for key, value in required_vars.items() if not value]
        if missing:
            logger.error(f"Missing required configuration: {', '.join(missing)}")
            return False
        
        # Validate URLs
        for url_var in ["CHM_API_URL", "WP_URL"]:
            url = getattr(cls, url_var)
            if url:
                try:
                    result = urlparse(url)
                    if not all([result.scheme, result.netloc]):
                        logger.error(f"Invalid URL for {url_var}: {url}")
                        return False
                except ValueError as e:
                    logger.error(f"URL parsing error for {url_var}: {e}")
                    return False
        
        # Validate numeric settings
        for var in ["TOKEN_EXPIRY_DAYS", "SYNC_INTERVAL_MINUTES", "BATCH_SIZE"]:
            value = getattr(cls, var)
            if not isinstance(value, int) or value <= 0:
                logger.error(f"Invalid {var}: {value} (must be positive integer)")
                setattr(cls, var, int(os.getenv(var, {"TOKEN_EXPIRY_DAYS": 7, "SYNC_INTERVAL_MINUTES": 60, "BATCH_SIZE": 50}[var])))

        # Validate SPORTS_FEST_DATE
        try:
            datetime.datetime.strptime(cls.SPORTS_FEST_DATE, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid SPORTS_FEST_DATE: {cls.SPORTS_FEST_DATE} (must be YYYY-MM-DD)")
            cls.SPORTS_FEST_DATE = "2025-07-19"

        # Warn if CHURCH_EXCEL_FILE doesn’t exist in LIVE_TEST mode
        if os.getenv("LIVE_TEST", "false").lower() == "true" and not os.path.exists(cls.CHURCH_EXCEL_FILE):
            logger.warning(f"CHURCH_EXCEL_FILE not found at {cls.CHURCH_EXCEL_FILE}; sync may fail")

        logger.info("Configuration validated successfully")
        return True
        
# Encryption utilities
def encrypt_data(data: any) -> str:
    """Encrypt data for secure storage."""
    try:
        if isinstance(data, dict):
            data = json.dumps(data)
        if isinstance(data, str):
            data = data.encode()
        return fernet.encrypt(data).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise

def decrypt_data(encrypted_data: str) -> any:
    """Decrypt data from storage."""
    try:
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode()
        decrypted = fernet.decrypt(encrypted_data).decode()
        try:
            return json.loads(decrypted)
        except json.JSONDecodeError:
            return decrypted
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise

# Create .env template
def create_env_template() -> None:
    """Generate .env.template if it doesn’t exist."""
    env_template_path = BASE_DIR / ".env.template"
    if not env_template_path.exists():
        template = """# ChMeetings configuration
CHM_API_URL=https://api.chmeetings.com
CHM_USERNAME=
CHM_PASSWORD=
CHM_API_KEY=

# WordPress configuration
WP_URL=https://your-wordpress-site.com
WP_API_KEY=

# Email configuration
EMAIL_FROM=sportsfest@example.com

# Selenium configuration
CHROME_DRIVER_PATH=
USE_CHROME_HEADLESS=True
CHROME_PROFILE_DIR=

# Application settings
APP_ENV=development
DEBUG=True
TOKEN_EXPIRY_DAYS=7
SYNC_INTERVAL_MINUTES=60
BATCH_SIZE=50
CHURCH_EXCEL_FILE=Church Application Form.xlsx
APPROVED_GROUP_NAME=2025 Sports Fest
APPROVED_EXCEL_FILE=group_import_approved_participants.xlsx

# Sync settings
TEAM_PREFIX=Team
SPORTS_FEST_DATE=2025-07-19
CHURCH_EXCEL_FILE=

# Export directory 
# Default is now 'G:\\Shared drives\\RP Google Drive\\VAY\\SportsFest\\VAYSF-data' if not set here.
# You can override it, e.g., EXPORT_DIR=C:\\Users\\YourUser\\Desktop\\VAYSF_Exports
# or EXPORT_DIR=export (for a folder named 'export' in the project root)
EXPORT_DIR=
"""
        env_template_path.write_text(template)
        logger.info(f"Created .env template at {env_template_path}")

# Initialize and validate
create_env_template()
if not (BASE_DIR / ".env").exists():
    logger.warning("No .env file found. Please create one from .env.template.")
if not Config.validate() and Config.APP_ENV != "test":
    raise ValueError("Configuration validation failed. Check logs for details.")