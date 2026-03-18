# Thin re-export — source of truth is domains/eurydice/session.py
from domains.eurydice.session import *  # noqa: F401,F403
from domains.eurydice.session import (  # explicit re-exports for importers
    SessionState as SessionState,
    EurydiceSession as EurydiceSession,
    MasteryGate as MasteryGate,
    MasteryCheckResult as MasteryCheckResult,
    AttemptRecord as AttemptRecord,
    TargetPassage as TargetPassage,
    TargetValidationResult as TargetValidationResult,
    create_session as create_session,
    get_session as get_session,
    drop_session as drop_session,
)
