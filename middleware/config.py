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

def _running_under_pytest() -> bool:
    """Return True when the module is imported as part of a pytest run."""
    argv0 = Path(sys.argv[0]).name.lower()
    return "pytest" in argv0 or "PYTEST_CURRENT_TEST" in os.environ

# Base directories - Windows-compatible using Path for robustness
BASE_DIR = Path(__file__).parent.resolve()
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"

# Export settings - default to G:\VAYSF-data to share the files with Church Rep from my Google Drive 
DEFAULT_EXPORT_PATH_STR = r"G:\Shared drives\RP Google Drive\VAY\SportsFest\VAYSF-data"
DEFAULT_TEST_EXPORT_DIR = TEMP_DIR / "pytest-export"

export_dir_env = os.getenv("EXPORT_DIR")
if export_dir_env:
    EXPORT_DIR = Path(export_dir_env)
elif _running_under_pytest():
    EXPORT_DIR = DEFAULT_TEST_EXPORT_DIR
else:
    EXPORT_DIR = Path(DEFAULT_EXPORT_PATH_STR)
DEFAULT_APPROVED_GROUP_NAME = "2026 Sports Fest"
DEFAULT_SPORTS_FEST_DATE = "2026-07-18"

# Athlete registration fees
ATHLETE_FEE_STANDARD = 30          # athlete with a primary or secondary sport (early registration)
ATHLETE_FEE_OTHER_EVENTS_ONLY = 20  # athlete registered only under Other Events (no deadline increase)
ATHLETE_FEE_LATE = 60              # athlete with primary or secondary sport (after deadline)
REGISTRATION_DEADLINE = "2026-05-16"  # ISO date; on/after this date, late fee applies

# Ensure directories exist with error handling
for directory in [LOG_DIR, DATA_DIR, TEMP_DIR, EXPORT_DIR]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
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
    "TABLE_TENNIS_35": "Table Tennis 35+",
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
        SPORT_TYPE["TABLE_TENNIS_35"],
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
    
# ChMeetings custom field names (must match labels in ChMeetings exactly)
# Used in participants.py _map_chmeetings_participants() to extract data from additional_fields.
# To verify these match the live API, run: python main.py test --system chmeetings --test-type api-inspect
CHM_FIELDS = {
    "CHURCH_TEAM": "Church Team",
    "PRIMARY_SPORT": "Primary Sport",
    "PRIMARY_FORMAT": "Primary Racquet Sport Format",
    "PRIMARY_PARTNER": "Primary Racquet Sport Partner (if applied)",
    "SECONDARY_SPORT": "Secondary Sport",
    "SECONDARY_FORMAT": "Secondary Racquet Sport Format",
    "SECONDARY_PARTNER": "Secondary Racquet Sport Partner (if applied)",
    "OTHER_EVENTS": "Other Events",
    "COMPLETION_CHECKLIST": "Completion Check List",
    "PARENT_NAME":  "Name of my parents or legal guardian",
    "PARENT_EMAIL": "Email of my parents or legal guardian",
    "PARENT_PHONE": "Cell phone of my parents or legal guardian",
    "ROLES": "My role is",
}

# ── Season Reset: ChMeetings Custom Field & Option IDs ──────────────────────
# Sports Fest section (section_id: 116139)
SF_SECTION_ID = 116139

SF_FIELD_IDS = {
    "MY_ROLE":             1282085,  # checkbox
    "CHURCH_TEAM":         1281851,  # dropdown
    "IS_MEMBER":           1281852,  # multiple_choice
    "PRIMARY_SPORT":       1281847,  # dropdown
    "PRIMARY_FORMAT":      1313281,  # dropdown
    "PRIMARY_PARTNER":     1313282,  # text
    "SECONDARY_SPORT":     1281848,  # dropdown
    "SECONDARY_FORMAT":    1313283,  # dropdown
    "SECONDARY_PARTNER":   1313284,  # text
    "OTHER_EVENTS":        1281849,  # checkbox
    "AGE_VERIFICATION":    1283264,  # multiple_choice
    "PARENT_NAME":         1283265,  # text
    "PARENT_EMAIL":        1283266,  # text
    "PARENT_PHONE":        1283267,  # text
    "ADDITIONAL_INFO":     1281850,  # multi_line_text
    # Church Rep Verification section (section_id: 116188)
    "CHECKLIST":           1283271,  # checkbox
    "NOTES_PROGRESS":      1283358,  # multi_line_text
}

# IS_MEMBER multiple_choice option_id → label (field_id: 1281852)
# Used by the membership-flip write-back in sync/participants.py.
# To look these up: run `python main.py test --system chmeetings --test-type api-inspect`
# on a registered person, then find field_id 1281852 in their additional_fields and note
# the selected_option_id for each value ("Yes" and "No").
# Leave as 0 to skip CHM write-back until verified against the live API.
SF_IS_MEMBER_OPTION_IDS = {
    "Yes": 199355,
    "No":  199356,
}

# Church Team dropdown option_id → church code mapping (field_id: 1281851)
SF_CHURCH_TEAM_OPTIONS = {
    199353: "Other",
    199354: "RPC",
    199451: "ORN",
    213666: "SDC",
    214591: "NSD",
    214653: "TLC",
    215122: "ANH",
    215123: "GLA",
    215124: "NHC",
    215125: "SGV",
    226673: "GAC",
    226674: "PCC",
    226675: "WSD",
    227107: "FVC",
    227108: "MWC",
    227109: "OCB",
    227110: "WCC",
    227627: "LBC",
    227691: "SBC",
    227692: "SFV",
}

# Primary Sport dropdown option_id → label (field_id: 1281847)
SF_PRIMARY_SPORT_OPTIONS = {
    199332: "Basketball - Men Team",
    199333: "Bible Challenge - Mixed Team",
    199334: "Volleyball - Men Team",
    199335: "Volleyball - Women Team",
    199343: "Badminton",
    199344: "Tennis",
    199345: "Table Tennis",
    199346: "Pickleball",
    212136: "Unselected/NA",
    212137: "Pickleball 35+",
    330427: "Table Tennis 35+",
}

# Secondary Sport dropdown option_id → label (field_id: 1281848)
SF_SECONDARY_SPORT_OPTIONS = {
    199336: "Basketball - Men Team",
    199337: "Bible Challenge - Mixed Team",
    199338: "Volleyball - Men Team",
    199339: "Volleyball - Women Team",
    199347: "Badminton",
    199348: "Tennis",
    199349: "Table Tennis",
    199350: "Pickleball",
    199352: "Unselected/NA",
    212143: "Pickleball 35+",
    330428: "Table Tennis 35+",
}

# My Role checkbox option_id → label (field_id: 1282085)
SF_MY_ROLE_OPTIONS = {
    199442: "Athlete/Participant",
    199443: "Parents paying for minors who play in Sports Fest",
    199444: "Church's Representative",
    199445: "Church Pastor, Leader, or Coach",
    199446: "VAY SM Staff",
    199447: "Fan and Supporter",
}

# Other Events checkbox option_id → label (field_id: 1281849)
SF_OTHER_EVENTS_OPTIONS = {
    199340: "Scripture Memorization",
    199341: "Track & Field",
    199342: "Tug-of-war",
    329599: "Soccer - Coed Exhibition",
}

# Age Verification multiple_choice option_id → label (field_id: 1283264)
SF_AGE_VERIFICATION_OPTIONS = {
    199606: "I am over 18 but under 35",
    199607: "I am under 18",
    212149: "I am over 35",
}

# Completion Checklist checkbox option_id → label (field_id: 1283271)
SF_CHECKLIST_OPTIONS = {
    199608: "1. Correct identity, gender, age range",
    199609: "2. Consent Form Signed by Self or Parents",
    199621: "3. Account created on Member Portal and logged in",
    199610: "4. Valid Photo as ID for event check-in",
    199611: "5. Approval from Pastor",
    199612: "6. Paid All Fees",
}

# Fields that use selected_option_ids (array) — reset to []
SF_CHECKBOX_FIELD_IDS = {
    SF_FIELD_IDS["MY_ROLE"],
    SF_FIELD_IDS["OTHER_EVENTS"],
    SF_FIELD_IDS["CHECKLIST"],
}

# Fields that use selected_option_id (scalar) — reset to null
SF_DROPDOWN_FIELD_IDS = {
    SF_FIELD_IDS["CHURCH_TEAM"],
    SF_FIELD_IDS["IS_MEMBER"],
    SF_FIELD_IDS["PRIMARY_SPORT"],
    SF_FIELD_IDS["PRIMARY_FORMAT"],
    SF_FIELD_IDS["SECONDARY_SPORT"],
    SF_FIELD_IDS["SECONDARY_FORMAT"],
    SF_FIELD_IDS["AGE_VERIFICATION"],
}

# Fields that use value (string) — reset to null
SF_TEXT_FIELD_IDS = {
    SF_FIELD_IDS["PRIMARY_PARTNER"],
    SF_FIELD_IDS["SECONDARY_PARTNER"],
    SF_FIELD_IDS["PARENT_NAME"],
    SF_FIELD_IDS["PARENT_EMAIL"],
    SF_FIELD_IDS["PARENT_PHONE"],
    SF_FIELD_IDS["ADDITIONAL_INFO"],
    SF_FIELD_IDS["NOTES_PROGRESS"],
}
# ── End Season Reset constants ───────────────────────────────────────────────

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
    SPORT_TYPE["PICKLEBALL_35"]: {"min": 35, "max": 99},
    SPORT_TYPE["TABLE_TENNIS_35"]: {"min": 35, "max": 99},
}

def is_racquet_sport(sport: str) -> bool:
    """Check if a sport is a racquet sport.

    Args:
        sport (str): The sport name.

    Returns:
        bool: True if it's a racquet sport, False otherwise.
    """
    return sport in RACQUET_SPORTS

# Venue capacity estimation defaults (Issue #83)
# Used by church_teams_export.py to produce a quick court-time estimate
# for the major team-sport events. Constants only — no UI tuning yet.
COURT_ESTIMATE_EVENTS = [
    SPORT_TYPE["BASKETBALL"],
    SPORT_TYPE["VOLLEYBALL_MEN"],
    SPORT_TYPE["VOLLEYBALL_WOMEN"],
]

# Pool games per team. Kept low (2) to surface the *minimum* venue need.
# Tune upward once a venue is confirmed.
COURT_ESTIMATE_DEFAULT_POOL_GAMES_PER_TEAM = 2
COURT_ESTIMATE_DEFAULT_MINUTES_PER_GAME = 60
COURT_ESTIMATE_INCLUDE_THIRD_PLACE_GAME = False

# Fallback only — the JSON-driven MIN_TEAM_SIZE_* rules in
# validation/summer_2026.json are the source of truth. Used if a rule
# is missing for an event in COURT_ESTIMATE_EVENTS.
COURT_ESTIMATE_MIN_TEAM_SIZE = {
    SPORT_TYPE["BASKETBALL"]: 5,
    SPORT_TYPE["VOLLEYBALL_MEN"]: 6,
    SPORT_TYPE["VOLLEYBALL_WOMEN"]: 6,
}

COURT_ESTIMATE_PLAYOFF_RULES = [
    {"min_teams": 1, "max_teams": 3, "playoff_teams": 0},
    {"min_teams": 4, "max_teams": 7, "playoff_teams": 4},
    {"min_teams": 8, "max_teams": 999, "playoff_teams": 8},
]

# Configuration class
class Config:
    """Configuration settings for VAYSF middleware."""
    # ChMeetings configuration
    CHM_API_URL = os.getenv("CHM_API_URL", "https://api.chmeetings.com")
    CHM_API_KEY = os.getenv("CHM_API_KEY")

    # WordPress configuration
    WP_URL = os.getenv("WP_URL")
    WP_API_KEY = os.getenv("WP_API_KEY")

    # Email configuration
    EMAIL_FROM = os.getenv("EMAIL_FROM", "info@vaysm.org")
    
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
    APPROVED_GROUP_NAME = os.getenv("APPROVED_GROUP_NAME", DEFAULT_APPROVED_GROUP_NAME)
    APPROVED_EXCEL_FILE = DATA_DIR / os.getenv("APPROVED_EXCEL_FILE", "group_import_approved_participants.xlsx")
    VAYSM_GROUP_ID = os.getenv("VAYSM_GROUP_ID", "")
    
    # Sync settings
    SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", 60))
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 50))
    TEAM_PREFIX = os.getenv("TEAM_PREFIX", "Team")
    SPORTS_FEST_DATE = os.getenv("SPORTS_FEST_DATE", DEFAULT_SPORTS_FEST_DATE)

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings."""
        required_vars = {
            "CHM_API_URL": cls.CHM_API_URL,
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
            cls.SPORTS_FEST_DATE = DEFAULT_SPORTS_FEST_DATE

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
CHM_API_KEY=

# WordPress configuration
WP_URL=https://your-wordpress-site.com
WP_API_KEY=

# Email configuration
EMAIL_FROM=sportsfest@example.com

# Application settings
APP_ENV=development
DEBUG=True
TOKEN_EXPIRY_DAYS=7
SYNC_INTERVAL_MINUTES=60
BATCH_SIZE=50
CHURCH_EXCEL_FILE=Church Application Form.xlsx
APPROVED_GROUP_NAME={DEFAULT_APPROVED_GROUP_NAME}
APPROVED_EXCEL_FILE=group_import_approved_participants.xlsx

# Sync settings
TEAM_PREFIX=Team
SPORTS_FEST_DATE={DEFAULT_SPORTS_FEST_DATE}
VAYSM_GROUP_ID=

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
