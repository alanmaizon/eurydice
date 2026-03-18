# Thin re-export — combines generic engine contracts with Eurydice-specific messages.
#
# Source of truth:
#   engine/contracts/session_contracts.py  (domain-agnostic)
#   domains/eurydice/schemas/messages.py   (Eurydice-specific)

# Generic session lifecycle messages
from engine.contracts.session_contracts import (  # noqa: F401
    SessionConfig as SessionConfig,
    SessionStartMessage as SessionStartMessage,
    SessionEndMessage as SessionEndMessage,
    TextInputMessage as TextInputMessage,
    AudioInputMessage as AudioInputMessage,
    ImageInputMessage as ImageInputMessage,
    InterruptMessage as InterruptMessage,
    SessionStartedMessage as SessionStartedMessage,
    SessionEndedMessage as SessionEndedMessage,
    TextDeltaMessage as TextDeltaMessage,
    TextDoneMessage as TextDoneMessage,
    AudioDeltaMessage as AudioDeltaMessage,
    AudioDoneMessage as AudioDoneMessage,
    ToolCallMessage as ToolCallMessage,
    ToolResultMessage as ToolResultMessage,
    ErrorMessage as ErrorMessage,
    StatusMessage as StatusMessage,
    LogMessage as LogMessage,
)

# Eurydice-specific messages
from domains.eurydice.schemas.messages import (  # noqa: F401
    StateChangedMessage as StateChangedMessage,
    MasteryUpdateMessage as MasteryUpdateMessage,
    MasteryAchievedMessage as MasteryAchievedMessage,
    AudioRecordingMessage as AudioRecordingMessage,
    TargetSetMessage as TargetSetMessage,
    TargetValidationMessage as TargetValidationMessage,
    CaptureInvalidMessage as CaptureInvalidMessage,
    UserDisagreementMessage as UserDisagreementMessage,
)
