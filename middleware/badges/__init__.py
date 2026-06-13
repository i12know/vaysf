"""
Athlete badge generation for VAY Sports Fest (Issue #77).

v1 scope — visual identity verification, local render only:
- ``generator.BadgeGenerator`` renders a 1080x1920 PNG credential per athlete.
- ``runner.BadgeRunner`` fetches approved participants (WordPress canonical
  data) + the ChMeetings profile photo, then drives the generator.

Out of v1 (future follow-up): WordPress upload endpoint, ChMeetings
``<img>`` write-back, audit log, and the QR interoperability spike. The QR
on the badge is an ID-only placeholder for now (see Issue #77 comments).
"""

from badges.generator import BadgeGenerator
from badges.runner import BadgeRunner

__all__ = ["BadgeGenerator", "BadgeRunner"]
