# Begin of sync/churches.py
import pandas as pd
from loguru import logger
from wordpress.frontend_connector import WordPressConnector

# Exact header of the Church Application Form's file-attachment column for the
# proof-of-insurance document (Issue #154, Path 2). Update this single constant
# if the Google Form / JotForm header changes between seasons. The column is
# optional: rows without it (or with an empty value) sync exactly as before.
INSURANCE_ATTACHMENT_COLUMN = "Proof of Insurance"


class ChurchSyncer:
    """Handles synchronization of church data from Excel to WordPress."""

    def __init__(self, wordpress_connector: WordPressConnector, stats: dict):
        self.wordpress_connector = wordpress_connector
        self.stats = stats  # Reference to SyncManager's stats dictionary

    def sync_from_excel(self, excel_file_path: str) -> bool:
        """Sync church data from an Excel file to WordPress."""
        try:
            df = pd.read_excel(excel_file_path)
            logger.info(f"Loaded {len(df)} churches from {excel_file_path}")

            has_insurance_column = INSURANCE_ATTACHMENT_COLUMN in df.columns

            for _, row in df.iterrows():
                wp_church = {
                    "church_name": row["Church Name"],
                    "church_code": row["Church Code"].strip().upper(),
                    "pastor_name": row["Pastor Name"],
                    "pastor_email": row["Pastor Email"].strip(),
                    "pastor_phone": row["Pastor Phone Number"],
                    "church_rep_name": f"{row['First Name']} {row['Last Name']}",
                    "church_rep_email": row["Your Email"].strip(),
                    "church_rep_phone": row["Your Mobile Phone"],
                    "sports_ministry_level": self._parse_sports_level(row["Your Church's Level of Sports Ministry"])
                }

                existing_church = self.wordpress_connector.get_church_by_code(wp_church["church_code"])

                # Path 2: carry the Church Application Form's insurance attachment
                # URL into WordPress. Only act when the column exists and the row
                # actually carries a URL.
                if has_insurance_column:
                    insurance_url = self._clean_insurance_url(row[INSURANCE_ATTACHMENT_COLUMN])
                    if insurance_url:
                        wp_church["insurance_file_url"] = insurance_url
                        current_status = (existing_church or {}).get("insurance_status", "pending")
                        # Advance pending -> submitted; never downgrade an
                        # already-approved church.
                        if current_status == "pending":
                            wp_church["insurance_status"] = "submitted"
                        logger.info(
                            f"Church {wp_church['church_code']}: insurance attachment "
                            f"{insurance_url} (status {current_status} -> "
                            f"{wp_church.get('insurance_status', current_status)})"
                        )

                if existing_church:
                    logger.info(f"Updating church {wp_church['church_code']}")
                    self.wordpress_connector.update_church_by_code(wp_church["church_code"], wp_church)
                    self.stats["churches"]["updated"] += 1
                else:
                    logger.info(f"Creating church {wp_church['church_code']}")
                    self.wordpress_connector.create_church(wp_church)
                    self.stats["churches"]["created"] += 1

            logger.info(f"Church sync completed: {self.stats['churches']}")
            return True
        except Exception as e:
            logger.error(f"Failed to sync churches: {e}")
            self.stats["churches"]["errors"] += 1
            return False

    @staticmethod
    def _clean_insurance_url(value) -> str:
        """Return a trimmed URL string, or '' for blank/NaN attachment cells."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            return ""
        return text

    def _parse_sports_level(self, level: str) -> int:
        """Convert sports ministry level string to integer."""
        if isinstance(level, str):
            if level.startswith("Level "):
                return int(level.replace("Level ", ""))
            try:
                return int(level)
            except ValueError:
                logger.warning(f"Invalid sports level '{level}', defaulting to 1")
        return 1
# End of sync/churches.py