# validation/individual_validator.py
# version: 1.0.0
# author: Bumble and Grok 3
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from loguru import logger
from .models import Participant, RulesManager
from config import (Config, SPORT_TYPE, SPORT_CATEGORY, SPORT_FORMAT, GENDER, 
                   SPORT_UNSELECTED, DEFAULT_SPORT, RACQUET_SPORTS, RULE_LEVEL,
                   VALIDATION_SEVERITY, AGE_RESTRICTIONS, is_racquet_sport)

class IndividualValidator:
    """Simple validator for individual participants."""
    
    def __init__(self, collection="SUMMER_2025"):
        """Initialize with collection name."""
        self.rules_manager = RulesManager(collection)
        self.sports_fest_date = self._parse_event_date()
    
    def _parse_event_date(self):
        """Parse the event date from rules."""
        for rule in self.rules_manager.rules:
            if rule.get("rule_type") == "event_date":
                try:
                    return datetime.strptime(rule.get("value"), "%Y-%m-%d").date()
                except Exception:
                    pass
        
        # Default to July 19, 2025 if not found
        return datetime(2025, 7, 19).date()
    
    def validate(self, participant_data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
        """Validate a participant and return (is_valid, issues)."""
        # Convert dict to Pydantic model for basic structure validation
        try:
            participant = Participant(**participant_data)
        except Exception as e:
            return False, [{"type": "invalid_data", "description": str(e), "severity": VALIDATION_SEVERITY["ERROR"]}]
        
        # Run validation rules
        issues = []
        issues.extend(self._validate_age(participant))
        issues.extend(self._validate_gender(participant))
        issues.extend(self._validate_photo(participant))
        issues.extend(self._validate_consent(participant))
        
        # Participant is valid unless there’s an ERROR severity issue
        is_valid = not any(issue.get("severity") == VALIDATION_SEVERITY["ERROR"] for issue in issues)
        return is_valid, issues

    def _validate_age(self, participant: Participant) -> List[Dict[str, str]]:
        """Validate participant age against rules."""
        issues = []
        
        if not participant.birthdate:
            return [{"type": "missing_birthdate", "description": "Birthdate required for age validation", "severity": VALIDATION_SEVERITY["ERROR"]}]
        
        try:
            # Parse birthdate
            birth_date = datetime.strptime(participant.birthdate, "%Y-%m-%d").date()
            
            # Calculate age on sports fest date
            age = self.sports_fest_date.year - birth_date.year
            if (self.sports_fest_date.month, self.sports_fest_date.day) < (birth_date.month, birth_date.day):
                age -= 1
            
            # Get sports for this participant
            sports = []
            if participant.primary_sport and participant.primary_sport != SPORT_UNSELECTED:
                sports.append(participant.primary_sport.split(" - ")[0] if " - " in participant.primary_sport else participant.primary_sport)
            if participant.secondary_sport and participant.secondary_sport != SPORT_UNSELECTED:
                sports.append(participant.secondary_sport.split(" - ")[0] if " - " in participant.secondary_sport else participant.secondary_sport)
            if participant.other_events:
                sports.extend([s.strip() for s in participant.other_events.split(",")])
            
            # Default to 'default' if no sports specified
            if not sports:
                sports = [DEFAULT_SPORT]
            
            # Check each sport
            for sport in sports:
                # Get age rules for this sport
                min_rules = [r for r in self.rules_manager.get_rules_for_sport(sport) 
                            if r.get("rule_type") == "age" and r.get("category") == "min"]
                max_rules = [r for r in self.rules_manager.get_rules_for_sport(sport) 
                            if r.get("rule_type") == "age" and r.get("category") == "max"]
                
                # Apply min age rules
                for rule in min_rules:
                    min_age = int(rule.get("value", 0))
                    if age < min_age:
                        issues.append({
                            "type": "age_restriction",
                            "description": f"Age {age} is below minimum age {min_age} for {sport}",
                            "rule_code": rule.get("rule_code"),
                            "severity": rule.get("severity", VALIDATION_SEVERITY["ERROR"]),
                            "sport": sport  # Add this field to include sport information
                        })
                
                # Apply max age rules
                for rule in max_rules:
                    max_age = int(rule.get("value", 99))
                    if age >= max_age:
                        issues.append({
                            "type": "age_restriction",
                            "description": f"Age {age} exceeds maximum age {max_age} for {sport}",
                            "rule_code": rule.get("rule_code"),
                            "severity": rule.get("severity", VALIDATION_SEVERITY["ERROR"]),
                            "sport": sport  # Add this field to include sport information
                        })
        
        except ValueError:
            issues.append({"type": "invalid_birthdate", "description": "Invalid birthdate format", "severity": VALIDATION_SEVERITY["ERROR"]})
        
        return issues
    
    def _validate_gender(self, participant: Participant) -> List[Dict[str, str]]:
        """Validate gender requirements for sports."""
        issues = []
        
        if not participant.gender:
            return [{"type": "missing_gender", "description": "Gender required for validation", "severity": VALIDATION_SEVERITY["ERROR"]}]
        
        gender = participant.gender.lower()
        
        # Check primary sport
        if participant.primary_sport and participant.primary_sport != SPORT_UNSELECTED:
            sport_parts = participant.primary_sport.split(" - ")
            sport = sport_parts[0]
            param = sport_parts[1] if len(sport_parts) > 1 else None
            
            # Get gender rules for this sport
            rules = [r for r in self.rules_manager.get_rules_for_sport(sport, param) 
                    if r.get("rule_type") == "gender" and r.get("category") == "restriction"]
            
            for rule in rules:
                required_gender = rule.get("value", "").lower()
                if required_gender and gender != required_gender:
                    issues.append({
                        "type": "gender_mismatch",
                        "description": f"{participant.primary_sport} requires {required_gender} gender",
                        "rule_code": rule.get("rule_code"),
                        "severity": rule.get("severity", VALIDATION_SEVERITY["ERROR"]),
                        "sport": sport  # Add this field to include sport information
                    })
        
        # Check secondary sport
        if participant.secondary_sport and participant.secondary_sport != SPORT_UNSELECTED:
            sport_parts = participant.secondary_sport.split(" - ")
            sport = sport_parts[0]
            param = sport_parts[1] if len(sport_parts) > 1 else None
            
            # Get gender rules for this sport
            rules = [r for r in self.rules_manager.get_rules_for_sport(sport, param) 
                    if r.get("rule_type") == "gender" and r.get("category") == "restriction"]
            
            for rule in rules:
                required_gender = rule.get("value", "").lower()
                if required_gender and gender != required_gender:
                    issues.append({
                        "type": "gender_mismatch",
                        "description": f"{participant.secondary_sport} requires {required_gender} gender",
                        "rule_code": rule.get("rule_code"),
                        "severity": rule.get("severity", VALIDATION_SEVERITY[VALIDATION_SEVERITY["ERROR"]]),
                        "sport": sport  # Add this field to include sport information
                    })
        
        return issues
    
    def _validate_photo(self, participant: Participant) -> List[Dict[str, str]]:
        """Validate photo requirements.
        
        Checks:
        1. If a photo URL exists
        2. If it's a valid URL format
        3. If URL is accessible (optional, only during LIVE_TEST)
        """
        issues = []
        
        # Get photo rules
        rules = [r for r in self.rules_manager.get_rules_by_type("photo") 
                if r.get("category") == "required"]
        
        if not rules:
            # If no photo rules defined, skip validation
            return issues
        
        # Check if photo URL exists
        if not participant.photo_url:
            for rule in rules:
                issues.append({
                    "type": "missing_photo",
                    "description": "No profile photo provided",
                    "rule_code": rule.get("rule_code"),
                    "severity": rule.get("severity", VALIDATION_SEVERITY["WARNING"])
                })
            return issues
        
        # Validate URL format
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(participant.photo_url):
            for rule in rules:
                issues.append({
                    "type": "invalid_photo_url",
                    "description": f"Invalid photo URL format: {participant.photo_url}",
                    "rule_code": rule.get("rule_code"),
                    "severity": rule.get("severity", VALIDATION_SEVERITY["WARNING"])
                })
            return issues
        
        # Check if the URL is accessible (only during LIVE_TEST)
        live_test = os.getenv("LIVE_TEST", "false").strip().lower() == "true"
        if live_test:
            try:
                import requests
                from requests.exceptions import RequestException
                
                # Set a short timeout to avoid long waits
                response = requests.head(participant.photo_url, timeout=5)
                
                # Check status code
                if response.status_code != 200:
                    for rule in rules:
                        issues.append({
                            "type": "inaccessible_photo",
                            "description": f"Photo URL returned status code {response.status_code}",
                            "rule_code": rule.get("rule_code"),
                            "severity": rule.get("severity", VALIDATION_SEVERITY["WARNING"])
                        })
                
                # Optionally check content type
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith('image/'):
                    for rule in rules:
                        issues.append({
                            "type": "non_image_photo",
                            "description": f"Photo URL content type is {content_type}, not an image",
                            "rule_code": rule.get("rule_code"),
                            "severity": rule.get("severity", VALIDATION_SEVERITY["WARNING"])
                        })
            
            except RequestException as e:
                for rule in rules:
                    issues.append({
                        "type": "photo_request_failed",
                        "description": f"Failed to access photo URL: {str(e)}",
                        "rule_code": rule.get("rule_code"),
                        "severity": rule.get("severity", VALIDATION_SEVERITY["WARNING"])
                    })
        
        return issues
    
    def _validate_consent(self, participant: Participant) -> List[Dict[str, str]]:
        """Validate consent form requirements."""
        issues = []
        
        # Calculate age
        birthdate = participant.birthdate
        sports_fest_date = datetime.strptime(Config.SPORTS_FEST_DATE, "%Y-%m-%d")
        age = None
        if birthdate:
            birthdate_dt = datetime.strptime(birthdate, "%Y-%m-%d")
            age = (sports_fest_date - birthdate_dt).days // 365
        
        # Get consent rules
        rules = [r for r in self.rules_manager.get_rules_by_type("consent") 
                if r.get("category") == "required"]
        
        for rule in rules:
            if rule.get("value", "").lower() == "true" and not participant.consent_status:
                # Adjust severity based on age
                severity = VALIDATION_SEVERITY["ERROR"] if age is not None and age < 18 else VALIDATION_SEVERITY["WARNING"]
                issues.append({
                    "type": "missing_consent",
                    "description": "Consent form status unknown or not provided",
                    "rule_code": rule.get("rule_code"),
                    "severity": severity
                })
        
        return issues