"""
Agent Decorators - Convenience imports from core

This module provides convenient access to agent-related decorators.
"""

# Import decorators from core
from core.decorators import (
    agent_required,
    supervisor_required,
    manager_required,
    campaign_access_required,
    ajax_required,
)

# Re-export for convenience
__all__ = [
    'agent_required',
    'supervisor_required',
    'manager_required',
    'campaign_access_required',
    'ajax_required',
]
