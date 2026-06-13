# validation/models.py
import json
import os
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
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
    primary_format: Optional[str] = None
    primary_partner: Optional[str] = None
    secondary_sport: Optional[str] = None
    secondary_format: Optional[str] = None
    secondary_partner: Optional[str] = None
    other_events: Optional[str] = None
    photo_url: Optional[str] = None
    consent_status: Optional[bool] = None
    
    model_config = ConfigDict(extra="allow")
#    class Config:
#        # Allow extra fields
#        extra = "allow"


class ParticipantRolesConfiguration(BaseModel):
    """Validated ChMeetings role-value configuration."""

    model_config = ConfigDict(extra="forbid")

    qualifying: List[str] = Field(min_length=1)
    known_excluded: List[str] = Field(default_factory=list)

    @field_validator("qualifying", "known_excluded")
    @classmethod
    def _roles_must_be_nonblank(cls, values: List[str]) -> List[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("role values must be nonblank strings")
        return cleaned

    @model_validator(mode="after")
    def _role_sets_must_be_disjoint(self):
        qualifying = {role.casefold() for role in self.qualifying}
        excluded = {role.casefold() for role in self.known_excluded}
        overlap = sorted(qualifying & excluded)
        if overlap:
            raise ValueError(
                f"qualifying and known_excluded roles overlap: {overlap}"
            )
        return self


class ValidationConfiguration(BaseModel):
    """Validated top-level configuration section in a rules document."""

    model_config = ConfigDict(extra="allow")

    participant_roles: Optional[ParticipantRolesConfiguration] = None


class RulesManager:
    """Simple manager for loading validation rules."""

    def __init__(self, collection="SUMMER_2025", rules_file=None):
        """Initialize with collection name and optional rules file path."""
        self.collection = collection
        self.rules_file = rules_file or os.path.join(
            os.path.dirname(__file__),
            f"{collection.lower()}.json"
        )
        self.rules = self._load_rules()
        self.configuration_error: Optional[str] = None
        self.configuration = self._load_configuration()

    def _load_rules(self):
        """Load rules from JSON file."""
        try:
            with open(self.rules_file, 'r') as f:
                data = json.load(f)
                return data.get("rules", [])
        except Exception as e:
            logger.error(f"Error loading rules from {self.rules_file}: {e}")
            return []

    def _load_configuration(self):
        """Load and validate the configuration section from rules JSON."""
        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            validated = ValidationConfiguration.model_validate(
                data.get("configuration", {})
            )
            return validated.model_dump(exclude_none=True)
        except ValidationError as e:
            self.configuration_error = str(e)
            logger.error(
                f"Invalid configuration in rules file {self.rules_file}: {e}"
            )
            return {}
        except Exception as e:
            self.configuration_error = str(e)
            logger.error(f"Error loading configuration from {self.rules_file}: {e}")
            return {}

    @property
    def participant_roles_configured(self) -> bool:
        """Whether a valid, nonempty participant-role policy was loaded."""
        return (
            self.configuration_error is None
            and bool(self.configuration.get("participant_roles", {}).get("qualifying"))
        )

    @property
    def qualifying_roles(self) -> frozenset:
        """Case-folded set of roles that make a participant eligible."""
        roles = self.configuration.get("participant_roles", {}).get("qualifying", [])
        return frozenset(r.casefold() for r in roles if r)

    @property
    def known_excluded_roles(self) -> frozenset:
        """Case-folded set of roles that are intentionally excluded (no warning)."""
        roles = self.configuration.get("participant_roles", {}).get("known_excluded", [])
        return frozenset(r.casefold() for r in roles if r)
    
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
    
