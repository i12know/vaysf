# middleware/group_assignment.py
import os
import sys
import pandas as pd
from loguru import logger
from config import Config, DATA_DIR

# Add parent directory to import path to access other modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from chmeetings.backend_connector import ChMeetingsConnector
from config import Config

def export_people_with_church_codes():
    """
    Export people from ChMeetings who have church codes assigned
    but aren't yet in their church groups.
    """
    logger.info("Exporting people with church codes...")
    
    with ChMeetingsConnector() as chm_connector:
        # Authenticate with ChMeetings
        if not chm_connector.authenticate():
            logger.error("Authentication with ChMeetings failed")
            return False
            
        # Get all people from ChMeetings
        all_people = chm_connector.get_people()
        logger.info(f"Retrieved {len(all_people)} people from ChMeetings")
        
        # Get all groups (to check who's already in a team)
        all_groups = chm_connector.get_groups()
        team_groups = [g for g in all_groups if g["name"].startswith(Config.TEAM_PREFIX)]
        
        # Create a set of people IDs who are already in team groups
        people_in_teams = set()
        for group in team_groups:
            group_people = chm_connector.get_group_people(group["id"])
            for person in group_people:
                people_in_teams.add(str(person.get("person_id")))
        
        logger.info(f"Found {len(people_in_teams)} people already in team groups")
        
        # Filter people who need group assignment
        people_for_assignment = []
        for person in all_people:
            person_id = str(person.get("id"))
            
            # Skip people already in teams
            if person_id in people_in_teams:
                continue
                
            # Get all additional fields
            additional_fields = {f["field_name"]: f["value"] for f in person.get("additional_fields", [])}
            
            # Check if they have a church code
            church_code = additional_fields.get("Church Team", "").strip().upper()
            if church_code:
                # This person needs to be assigned to a team
                people_for_assignment.append({
                    "Person Id": person_id,
                    "First Name": person.get("first_name", ""),
                    "Last Name": person.get("last_name", ""),
                    "Email": person.get("email", ""),
                    "Church Code": church_code,
                    "Group Name": f"Team {church_code}"
                })
        
        logger.info(f"Found {len(people_for_assignment)} people needing team assignment")
        
        # Create Excel file
        if people_for_assignment:
            df = pd.DataFrame(people_for_assignment)
            
            # Create the output directory if it doesn't exist
            output_dir = DATA_DIR
            os.makedirs(output_dir, exist_ok=True)
            
            # Export to Excel
            output_file = os.path.join(output_dir, "church_team_assignments.xlsx")
            df.to_excel(output_file, index=False)
            logger.info(f"Exported team assignments to {output_file}")
            
            # Also create a ChMeetings-compatible import file
            chm_import_file = os.path.join(output_dir, "chm_group_import.xlsx")
            chm_df = df[["Person Id", "First Name", "Last Name", "Group Name"]]
            chm_df.to_excel(chm_import_file, index=False)
            logger.info(f"Created ChMeetings import file at {chm_import_file}")
            
            return chm_import_file
        else:
            logger.info("No people found needing team assignment")
            return None

if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(os.path.join(current_dir, "logs", "group_assignment.log"), rotation="10 MB")
    
    try:
        result = export_people_with_church_codes()
        if result:
            logger.info(f"Success! Import file created at: {result}")
            logger.info("You can now import this file in ChMeetings using Tools > Import Group")
        else:
            logger.info("No assignment file created. Either all people are already assigned or there are no people with church codes.")
    except Exception as e:
        logger.exception(f"Error in group assignment process: {e}")