# Begin of sync/churches.py
import pandas as pd
from loguru import logger
from wordpress.frontend_connector import WordPressConnector

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