# validation/models.py
import os
import json
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import date
from loguru import logger
from config import DEFAULT_SPORT

class Participant(BaseModel):
    """Basic participant data structure validation."""
    chmeetings_id: str
    first_name: str
    last_name: str
    gender: Optional[str] = None
    birthdate: Optional[str] = None
    primary_sport: Optional[str] = None
    secondary_sport: Optional[str] = None
    other_events: Optional[str] = None
    photo_url: Optional[str] = None
    consent_status: Optional[bool] = None
    
    model_config = ConfigDict(extra="allow")
#    class Config:
#        # Allow extra fields
#        extra = "allow"


class RulesManager:
    """Simple manager for loading validation rules."""
    
    def __init__(self, collection="SUMMER_2025", rules_file=None):
        """Initialize with collection name and optional rules file path."""
        self.collection = collection
        self.rules_file = rules_file or os.path.join(
            os.path.dirname(__file__), 
            f"{collection.title()}.json"
        )
        self.rules = self._load_rules()
    
    def _load_rules(self):
        """Load rules from JSON file."""
        try:
            with open(self.rules_file, 'r') as f:
                data = json.load(f)
                return data.get("rules", [])
        except Exception as e:
            logger.error(f"Error loading rules from {self.rules_file}: {e}")
            return []
    
    def get_rules_by_type(self, rule_type):
        """Get rules filtered by type."""
        return [r for r in self.rules if r.get("rule_type") == rule_type]
    
    def get_rules_for_sport(self, sport_event, parameter=None):
        """Get rules for a specific sport event and parameter."""
        # First look for exact sport match
        rules = [r for r in self.rules 
                if r.get("sport_event") == sport_event 
                and (parameter is None or r.get("parameter") == parameter)]
        
        # Add default rules if no specific match
        if not rules or sport_event != DEFAULT_SPORT:
            default_rules = [r for r in self.rules 
                            if r.get("sport_event") == DEFAULT_SPORT
                            and (parameter is None or r.get("parameter") == parameter)]
            # Only add default rules that don't conflict with specific ones
            for rule in default_rules:
                rule_type = rule.get("rule_type")
                category = rule.get("category")
                
                # Skip if we already have a rule of this type and category for this sport
                if not any(r.get("rule_type") == rule_type and r.get("category") == category 
                           for r in rules):
                    rules.append(rule)
        
        return rules
    