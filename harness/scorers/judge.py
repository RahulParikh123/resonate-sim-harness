"""DEPRECATED. The generic 0-10 "judge panel" was replaced by the review council
in harness/reviewers.py — diverse critic personas, each with their own criteria,
that review (never rewrite) the draft Grok produces.

Kept as a thin redirect so any stray import doesn't break.
"""

from ..reviewers import review_draft  # noqa: F401
