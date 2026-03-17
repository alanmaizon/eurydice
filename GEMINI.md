Repository Architecture Report: Eurydice
Scope: This report is based on the repository structure and files provided in context, including the README.md, backend Python files, and frontend React hooks.

1. Structural Overview
The Eurydice project is a full-stack application with a clear separation of concerns, following modern development patterns.

Frontend Architecture The frontend is a React Single-Page Application (SPA). Its core logic is encapsulated in the useEurydiceApp custom hook (frontend/src/hooks/useEurydiceApp.js), which manages application state, side effects, and user interactions. This centralized hook pattern handles everything from authentication and session management to live WebSocket connections and browser-based audio/video capture, processing, and playback.

Backend Architecture The backend is a FastAPI application that serves both a REST API and a live WebSocket transport layer. It follows a domain-driven structure, with music-specific logic isolated in backend/app/domains/music/. This domain contains deterministic tools for transcription, comparison, and rendering. Sessions are backed by a PostgreSQL database, managed via SQLAlchemy.

Infrastructure & Deployment The deployment pattern is a single, containerized service intended for Google Cloud Run. The Dockerfile builds both the frontend and backend into one image. The FastAPI server is configured in backend/app/main.py to serve the static assets of the built React application, simplifying deployment and routing.

2. High-level Architecture Map
The following diagram, sourced from the project's README.md, illustrates the overall system architecture and data flow between components.

mermaid
flowchart LR
    U[Student Browser<br/>React + Vite UI] -->|HTTPS /api/*| B[FastAPI Backend<br/>Cloud Run]
    U -->|WebSocket /ws/live| B
    U -->|Session cookie| B

    B -->|Serve built SPA + assets| U
    B -->|Score import / render / compare| M[Music Domain Services<br/>transcription, comparison, rendering]
    B -->|SQLAlchemy async| D[(Cloud SQL PostgreSQL)]
    B -->|Verify ID token / mint session cookie| F[Firebase Auth + Admin SDK]
    B -->|Live multimodal streaming| G[Vertex AI Gemini Live]
    B -->|Read secrets| S[Secret Manager]
    B -->|Optional private feature sync at build time| C[Cloud Storage]

    M --> D
3. AI Interaction System Diagram
This diagram details the real-time interaction flow between the user, the application, and the AI services during a live tutoring session.

mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend (React)
    participant BE as Backend (FastAPI)
    participant GL as Gemini Live API
    participant DT as Deterministic Tools

    U->>+FE: Speaks / Plays Music / Uses Camera
    FE->>+BE: WebSocket: client.audio / client.video
    BE->>+GL: send_audio / send_image
    GL-->>-BE: server.transcript / server.text / server.audio
    BE-->>-FE: WebSocket: server.transcript / server.text / server.audio
    FE-->>-U: Renders text / Plays audio

    Note over GL: Model decides to call a tool
    GL->>BE: server.tool_call (e.g., lesson_action)
    BE->>+DT: run_live_music_tool()
    DT-->>-BE: Tool Result
    BE->>GL: send_text("TOOL_RESULT: ...")
    BE-->>FE: server.tool_result (for client-invoked tools)

    Note over FE: User clicks a button (e.g., "Compare Bar")
    FE->>BE: WebSocket: client.tool (e.g., lesson_action)
    BE->>+DT: run_live_music_tool()
    DT-->>-BE: Tool Result
    BE-->>-FE: server.tool_result
4. Current Strengths
The project is built on a solid architectural foundation.

Clear Domain Split: There is an excellent separation between generic live infrastructure (backend/app/live/) and music-specific logic (backend/app/domains/music/), which promotes modularity.
Deterministic Tool Layer: The system is designed to rely on deterministic tools for music analysis, avoiding LLM hallucination for critical feedback. This is evident in backend/app/domains/music/live_tools.py and the various endpoints in backend/app/domains/music/api.py.
Comprehensive Testing: The repository includes a test suite (backend/tests/) that covers WebSocket interactions, session management, and domain logic, indicating a commitment to quality.
Prompt Quality Evaluation: The existence of backend/app/domains/music/prompt_eval.py shows a mature approach to prompt engineering, with processes for evaluating prompt quality and capability coverage.
Simplified Deployment: The single-service deployment model simplifies production routing, asset hosting, and operational management.
5. Technical Weaknesses
Despite its strengths, the architecture exhibits several points of dispersion that could be improved.

A. Prompt System is Fragmented: Prompt logic is scattered. backend/app/main.py assembles a system prompt from settings and tool fragments, while backend/app/domains/music/runtime.py constructs a separate, detailed opening_prompt. This fragmentation risks inconsistent persona and duplicated instructions.
B. Conversation State is Distributed: State is not centralized. The frontend's useEurydiceApp hook, the backend's MusicRuntime object, and the database all hold different pieces of the conversational state, which can lead to drift and complexity.
C. Session Lifecycle is Duplicated: The concept of a "session" is overloaded. It can refer to a database record (Session model), a WebSocket connection, or the Gemini Live API's conversational context. This ambiguity can complicate state management, especially for reconnects and resumption.
D. Streaming Architecture is Partially Normalized: The backend exposes both RESTful endpoints (in api.py) and a live streaming WebSocket. The frontend uses both (apiRequest and useLiveConnection), creating two different code paths for tutor logic and increasing maintenance overhead.
E. Tool Integration is Domain-Coupled: The tool execution logic in backend/app/main.py and backend/app/domains/music/live_tools.py is tightly coupled to the music domain, making it difficult to add tools for other domains or to create a generic observability layer.
F. Conversation Memory Structure is Unclear: There is no dedicated module for managing conversation memory. Context is built ad-hoc from the database via build_music_live_context and held partially in various runtimes, risking inefficient or incomplete context being sent to the model.
G. Evaluation is Not End-to-End: While unit and prompt evaluation tests exist, there is no visible evaluation harness for assessing the quality of multi-turn tutoring interactions, including latency, interruption recovery, and pedagogical effectiveness.
H. Overlapping Audio Pipelines: Audio processing responsibilities are split between the frontend (onset detection in capturePcmClip) and backend (pitch analysis in transcribe_pcm16). This can lead to inconsistencies, a problem acknowledged by the existence of the buildTraceMismatch function in useEurydiceApp.js.
6. Prompt Engineering Audit
Likely Current State: Prompt logic is distributed by concern, leading to potential persona drift, inconsistent tone, and weak guardrails.
Desired Prompt Architecture: A centralized prompt composer should be responsible for assembling the final prompt from distinct, well-defined components:
system_prompt: Defines the stable identity of the agent.
conversation_context: Provides recent turns, lesson state, and student profile.
tool_results: Injects structured, machine-generated evidence.
user_message: The user's current intent.
Missing Controls: The current system lacks explicit prompt controls to enforce when to ask questions, how to cite tool evidence, correction style, and safety boundaries.
7. Conversation Engine Design Review
Current State: A GeminiLiveBridge exists, but a distinct, high-level ConversationManager to orchestrate conversational flow is not apparent.
Recommended ConversationManager: A new conversation_manager.py module should be created. Its core responsibilities would be to:
Maintain a normalized, ordered log of all conversation events (turns, tool calls, results).
Build the context for the Gemini Live API.
Manage turn state, including interruptions and cancellations.
Persist relevant state and compact older turns for efficiency.
8. Streaming Architecture Audit
Desired Flow: A unified, semantic event contract should be the single source of truth for communication between the backend and frontend.
Likely Current Status: The system supports live transport, but event normalization is a weak point. The frontend likely receives raw data chunks rather than semantic deltas, and tool calls may not be cleanly integrated into the event stream.
Recommended Streaming Event Contract: All live communication should use a single, well-defined schema (e.g., {type, payload, metadata}), enabling the frontend to be a simple renderer of state changes and simplifying logic for partial text updates, interruptions, and cancellations.
9. Tool Integration Review
Existing Deterministic Tools: The music domain is well-supported with tools for pitch, transcription, comparison, and rendering.
Recommended Generic Tool Interface: A generic tool contract should be established. Gemini should never invent audio measurements; all feedback must be grounded in evidence from these deterministic tools.
Missing Platform Features: While the report outline suggested missing latency metrics, the codebase shows this is already implemented. The MusicLiveToolCall model in backend/app/domains/music/models.py includes latency_ms, and this is recorded in _record_live_tool_call in backend/app/main.py and exposed via the /api/music/analytics/live-tools endpoint. However, explicit retry policies, timeouts, and caching for tool calls could still be improved.
10. Session Lifecycle Review
The three session concepts (user, transport, and AI) should be explicitly linked but not conflated. The current naming and distribution of logic across REST APIs, the live bridge, and domain runtimes make this separation unclear, which complicates features like session resumption. A recommended model would clearly delineate these concepts in the architecture.

11. Live API Usage Audit
The project shows good patterns with a dedicated GeminiLiveBridge and a live_tool_loop. However, the mix of REST and live pathways for tutoring logic is suboptimal. The recommendation is to make Gemini Live the primary interaction engine for all conversational tutoring, relegating REST APIs to authentication, session history, and administrative tasks.

12. Evaluation Framework Recommendation
A dedicated evaluation system, separate from unit tests, is needed to measure the quality of the live tutoring experience. This harness should be scenario-based and track metrics like:

Response accuracy and grounding in tool evidence.
Tool-use correctness.
Latency (to first token and final response).
Interruption recovery and pedagogical clarity.
13. Caching and Latency Optimization
Good caching targets include stable prompt fragments, rendered score artifacts, and repeated tool outputs for identical audio inputs. Live token streams and transient turn state should not be cached.

14. Recommended Refactors
Centralize Prompting: Create a single PromptComposer to remove scattered prompt logic. I've included a sample implementation for this below.
Add a Conversation Manager: Introduce a ConversationManager as the single source of truth for conversational state.
Normalize Live Events: Define and use a single streaming event schema between the backend and frontend.
Unify Tutor Entrypoints: Route all tutoring interactions through a single runtime path, driven by the live engine.
Formalize Tool Registry: Replace ad-hoc tool wiring with a typed, observable tool registry.
Split Session Types Explicitly: Refactor to clearly distinguish between application, transport, and AI sessions.
Add a Live Eval Harness: Build a scenario runner for evaluating multi-turn pedagogical quality.
As an example of Refactor 1, you could introduce a new file to handle prompt composition and simplify the logic in main.py.

New file: prompts.py
+42
"""Centralized prompt composition for Eurydice."""

from __future__ import annotations

from .domains import SessionRuntime
from .domains.music.live_tools import music_live_tool_prompt_fragment
from .settings import settings


class PromptComposer:
    """Builds prompts for a live session from multiple sources."""

    def __init__(self, runtime: SessionRuntime, live_context: str):
        """Initialise the composer with session-specific context."""
        self.runtime = runtime
        self.live_context = live_context

    def get_system_prompt(self) -> str:
        """Build the full system prompt for the Gemini Live session."""
        base_system_prompt = self.runtime.system_prompt(
            settings.system_instructions,
            settings.music_system_instructions,
        )
        tool_prompt = music_live_tool_prompt_fragment()
        if tool_prompt:
            base_system_prompt = f"{base_system_prompt}\n\n{tool_prompt}"

        if self.live_context:
            return (
                f"{base_system_prompt}\n\n"
                "Retrieved session context:\n"
                f"{self.live_context}\n\n"
                "Use this context as supporting memory only. Prioritize current live evidence. "
                "When uncertain or conflicting, request replay/reframing before concluding."
            )
        return base_system_prompt

    def get_opening_user_prompt(self) -> str | None:
        """Return the opening user-role prompt, if the runtime requires one."""
        if self.runtime.uses_model_opening_prompt():
            return self.runtime.opening_prompt()
        return None

main.py
-21
+6
    CLIENT_TOOL,
    CLIENT_VIDEO,
)
from .prompts import PromptComposer
from .models import Session
from .sessions import router as sessions_router
from .settings import settings
        skill=resolved_skill,
        goal=session.goal,
    )
    base_system_prompt = runtime.system_prompt(
        settings.system_instructions,
        settings.music_system_instructions,
    )
    tool_prompt = music_live_tool_prompt_fragment()
    if tool_prompt:
        base_system_prompt = f"{base_system_prompt}\n\n{tool_prompt}"
    live_context = await _build_live_context_for_user(
        user_id=user["uid"],
        skill=runtime.skill,
        goal=session.goal,
    )
    if live_context:
        system_prompt = (
            f"{base_system_prompt}\n\n"
            "Retrieved session context:\n"
            f"{live_context}\n\n"
            "Use this context as supporting memory only. Prioritize live evidence. "
            "When uncertain or conflicting, request replay/reframing before concluding."
        )
    else:
        system_prompt = base_system_prompt
    composer = PromptComposer(runtime, live_context)
    system_prompt = composer.get_system_prompt()

    bridge = GeminiLiveBridge(
        model_id=settings.model_id,
        )
        for event in runtime.on_connect_events():
            await ws.send_json(event)
        if runtime.uses_model_opening_prompt():
            opening_prompt = runtime.opening_prompt()
            if opening_prompt:
                await bridge.send_text(opening_prompt, role="user")
        opening_prompt = composer.get_opening_user_prompt()
        if opening_prompt:
            await bridge.send_text(opening_prompt, role="user")

        forward_task = asyncio.create_task(
            _forward_bridge_events(

15. Implementation Roadmap
A phased approach is recommended to address these weaknesses systematically.

Phase 1 — Stabilize Architecture: Inventory all prompt sources and tutor entrypoints. Define canonical live event schemas and session model boundaries.
Phase 2 — Centralize AI Core: Implement the PromptComposer, ConversationManager, and a formal tool registry.
Phase 3 — Harden Streaming: Normalize all backend live events to the new schema and update the frontend to render deltas, supporting interruptions and cancellations.
Phase 4 — Ground the Tutor: Enforce that all pitch/rhythm feedback is backed by deterministic tool calls, with results stored in the turn memory.
Phase 5 — Evaluate and Optimize: Add the scenario-based evaluation harness and implement caching for stable prompts and tool outputs.
Phase 6 — Go Live-First: Migrate all conversational tutoring to the Gemini Live engine, simplifying the architecture by removing duplicate REST-based code paths.
16. Target Architecture
The repository already has the right primitives for a strong Gemini Live tutor: a live bridge, a browser audio pipeline, deterministic music tools, and good test scaffolding.

The primary weakness is architectural dispersion. Prompts, conversation state, and interaction flows are fragmented.

The highest-priority recommendation is to build a single, unified conversational core around a central prompt composer, a conversation manager, a typed tool registry, and a normalized streaming event schema. This is the most direct path to creating a robust, maintainable, and extensible real-time multi-turn music tutor.

I hope this comprehensive report is helpful. It validates the provided analysis and enriches it with evidence and actionable suggestions based on the project's source code.