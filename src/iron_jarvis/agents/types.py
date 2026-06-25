"""Agent definitions (§11).

An agent = identity + capabilities + provider + tools + permissions + policies.
The slice ships a working Builder; the other types (§11) are defined as stubs so
multi-agent orchestration (§12, Phase 6) can flesh them out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import AgentType

_FILE_TOOLS = ["read_file", "write_file", "edit_file", "list_files", "grep"]
# Memory + skills are registered on the platform (§21, §23); advertise them to
# worker agents so they're actually reachable from the agent loop, not just the
# HTTP/registry surface. All default to ``allow`` (low-risk reads/writes).
_KNOWLEDGE_TOOLS = [
    "memory_search",
    "memory_read",
    "memory_write",
    "skill_search",
    "skill_load",
]
# Self-service: agents can search drives, write long-term memory, and create
# their own schedules / webhooks / workflows (the last appears on the user's
# visual workflow canvas). All low-risk + user-visible.
_SELF_SERVICE_TOOLS = [
    "file_search",
    "ltm_search",
    "ltm_append",
    "schedule_create",
    "webhook_add",
    "workflow_create",
]
# Real documents: read any file type, write within the workspace.
_DOCUMENT_TOOLS = ["read_document", "write_document", "extract_pdf"]
# Self-correction: record preferences learned mid-task; recall past lessons.
_LEARNING_TOOLS = ["remember_preference", "recall_lessons"]

# A warm, human voice shared across agents. Accumulated lessons are appended to
# this prompt at runtime (see LearningEngine.apply_to_prompt), so it improves
# every time the user interacts.
_VOICE = (
    "You are Iron Jarvis — a sharp, friendly teammate, not a faceless bot. Talk "
    "like a trusted colleague: warm, concise, plain-spoken, and proactive. You "
    "can read and write real documents (PDF, Word, Excel, PowerPoint, CSV, "
    "Markdown, text) as naturally as a person. Narrate briefly what you're doing "
    "and why; if something is ambiguous, make a sensible assumption and say so. "
    "When you notice how the user likes things done, call `remember_preference` "
    "so you do it that way next time. Finish with a friendly, plain-language "
    "summary — no further tool calls."
)


@dataclass
class AgentDefinition:
    type: AgentType
    system_prompt: str
    tools: list[str]
    permission_overrides: dict[str, str] = field(default_factory=dict)


_DEFINITIONS: dict[AgentType, AgentDefinition] = {
    AgentType.BUILDER: AgentDefinition(
        type=AgentType.BUILDER,
        system_prompt=(
            _VOICE + " As the Builder, you roll up your sleeves and get the task "
            "done inside your workspace — one concrete action at a time."
        ),
        tools=(
            _FILE_TOOLS + ["shell"] + _KNOWLEDGE_TOOLS + _SELF_SERVICE_TOOLS
            + _DOCUMENT_TOOLS + _LEARNING_TOOLS
        ),
    ),
    AgentType.PLANNER: AgentDefinition(
        type=AgentType.PLANNER,
        system_prompt=(
            _VOICE + " As the Planner, you think a few steps ahead — break the goal "
            "into a clear plan and delegate, schedule, or author workflows the user "
            "can see and tweak."
        ),
        tools=(
            _FILE_TOOLS + _KNOWLEDGE_TOOLS + _SELF_SERVICE_TOOLS
            + _DOCUMENT_TOOLS + _LEARNING_TOOLS
        ),
    ),
    AgentType.REVIEWER: AgentDefinition(
        type=AgentType.REVIEWER,
        system_prompt=(
            _VOICE + " As the Reviewer, you're a careful, constructive second pair "
            "of eyes — read the work (including any documents), assess correctness "
            "and risk, and report clearly and kindly."
        ),
        tools=[
            "read_file", "list_files", "grep", "read_document", "extract_pdf",
            "memory_search", "skill_search", "recall_lessons",
        ],
    ),
    AgentType.SUPERVISOR: AgentDefinition(
        type=AgentType.SUPERVISOR,
        system_prompt=(
            _VOICE + " As the Supervisor, you coordinate: break the goal into "
            "subtasks and `delegate` each to a specialist subagent, then weave their "
            "results into one clear answer for the user."
        ),
        tools=["delegate", "read_file", "list_files", "read_document", "recall_lessons"],
    ),
}


def get_agent_definition(agent_type: AgentType) -> AgentDefinition:
    if agent_type in _DEFINITIONS:
        return _DEFINITIONS[agent_type]
    # Fall back to a generic builder-like definition.
    return _DEFINITIONS[AgentType.BUILDER]
