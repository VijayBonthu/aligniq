"""
Intent Handlers Package

Contains specialized handlers for different types of user intents
in the chat-with-doc conversation flow.
"""

from handlers.intent_handlers import (
    IntentHandler,
    ConfirmationHandler,
    DeclineHandler,
    ArchitectureChallengeHandler,
    QuestionHandler,
    SuggestionHandler,
    CommandHandler,
    HybridQueryHandler,
    PendingChangeManagementHandler,
    UndoRedoHandler,
    ReportComparisonHandler,
    WhatIfHandler,
    RequirementEditHandler,
    get_intent_handler
)

__all__ = [
    "IntentHandler",
    "ConfirmationHandler",
    "DeclineHandler",
    "ArchitectureChallengeHandler",
    "QuestionHandler",
    "SuggestionHandler",
    "CommandHandler",
    "HybridQueryHandler",
    "PendingChangeManagementHandler",
    "UndoRedoHandler",
    "ReportComparisonHandler",
    "WhatIfHandler",
    "RequirementEditHandler",
    "get_intent_handler"
]
