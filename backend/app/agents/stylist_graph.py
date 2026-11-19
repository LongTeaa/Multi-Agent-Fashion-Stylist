from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any
from sqlmodel import Session

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.context_agent import VIETNAM_TZ, context_agent_node
from app.agents.coordinator import coordinator_node
from app.agents.fashion_agent import fashion_agent_node
from app.agents.personalization_agent import personalization_agent_node
from app.agents.state import (
    AgentTraceEvent,
    StylistGraphState,
    is_critique_loop_enabled,
    is_relaxation_loop_enabled,
)
from app.agents.wardrobe_agent import wardrobe_agent_node
from app.services.providers import ContextLLMProviderProtocol, WeatherProviderProtocol

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

def _make_empty_candidate_pool() -> dict[str, list[Any]]:
    return {
        "tops": [],
        "bottoms": [],
        "dresses": [],
        "footwear": [],
        "outerwear": [],
        "accessories": [],
    }


# ============================================================================
# CONDITIONAL ROUTING FUNCTIONS
# ============================================================================

def route_after_context(state: StylistGraphState) -> str:
    """Routes after Context Agent.

    Continues to 'wardrobe' only when context exists, needs_clarification is False,
    and no errors exist. Otherwise routes directly to END.
    """
    ctx = state.get("context")
    if ctx and ctx.needs_clarification is False and not state.get("errors"):
        return "wardrobe"
    return END


def route_after_wardrobe(state: StylistGraphState) -> str:
    """Routes after Wardrobe Agent.

    Continues to 'fashion' only when no errors exist (e.g. WARDROBE_EMPTY).
    Otherwise routes directly to END.
    """
    if not state.get("errors"):
        return "fashion"
    return END


def route_after_fashion(state: StylistGraphState) -> str:
    """Routes after Fashion Agent.

    Continues back to 'wardrobe' when a bounded RelaxationRequest is emitted,
    forward to 'personalization' when evaluated outfits exist, or to END on errors.
    """
    if state.get("errors"):
        return END
    if is_relaxation_loop_enabled(state) and state.get("relaxation_request") is not None:
        return "wardrobe"
    if state.get("evaluated_outfits"):
        return "personalization"
    return END


def route_after_personalization(state: StylistGraphState) -> str:
    """Routes after Personalization Agent.

    Continues to 'coordinator' only when no errors exist and at least one
    ranked outfit exists. Otherwise routes directly to END.
    """
    if not state.get("errors") and bool(state.get("ranked_outfits")):
        return "coordinator"
    return END


def route_after_coordinator(state: StylistGraphState) -> str:
    """Routes after Coordinator Agent.

    Routes back to 'fashion' on a bounded Critic reroute, or terminates at END.
    """
    if state.get("errors"):
        return END
    if is_critique_loop_enabled(state) and state.get("coordinator_decision") == "reroute_fashion":
        return "fashion"
    return END


# ============================================================================
# GRAPH BUILDER & RUNNER
# ============================================================================

def create_stylist_graph(
    *,
    session: Session | None = None,
    clock: Clock | None = None,
    llm_provider: ContextLLMProviderProtocol | None = None,
    weather_provider: WeatherProviderProtocol | None = None,
    enable_agent_loops: bool = True,
) -> CompiledStateGraph:
    """Creates and compiles the 5-agent cyclic recommendation LangGraph workflow.

    Nodes:
        context -> wardrobe <-> fashion -> personalization -> coordinator -> (fashion | END)

    Dependencies (database session, clock) are injected into node closures so
    tests and callers do not require live services or SDK patching.
    """
    workflow = StateGraph(StylistGraphState)

    # 1. Context Node
    def _context_step(state: StylistGraphState) -> dict[str, Any]:
        ref_time = state.get("reference_time")
        if ref_time is None:
            ref_time = clock() if clock else datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        else:
            ref_time = ref_time.astimezone(timezone.utc)

        curr_date = ref_time.astimezone(VIETNAM_TZ).date()
        result = context_agent_node(
            state,
            current_date=curr_date,
            llm_provider=llm_provider,
            weather_provider=weather_provider,
        )
        result["reference_time"] = ref_time
        if "enable_agent_loops" not in state:
            result["enable_agent_loops"] = enable_agent_loops
        ctx = result.get("context")
        needs_clar = bool(ctx and ctx.needs_clarification)
        result["agent_trace"] = list(state.get("agent_trace", [])) + [
            AgentTraceEvent(
                round=0,
                sender="context",
                receiver="end" if needs_clar else "wardrobe",
                event_type="CLARIFICATION_REQUESTED" if needs_clar else "CONTEXT_EXTRACTED",
                summary_vi="Yêu cầu làm rõ ngữ cảnh." if needs_clar else "Đã trích xuất StylistContext.",
            )
        ]
        return result

    # 2. Wardrobe Node
    def _wardrobe_step(state: StylistGraphState) -> dict[str, Any]:
        return wardrobe_agent_node(state, session=session)

    # 3. Fashion Node
    def _fashion_step(state: StylistGraphState) -> dict[str, Any]:
        return fashion_agent_node(state)

    # 4. Personalization Node
    def _personalization_step(state: StylistGraphState) -> dict[str, Any]:
        return personalization_agent_node(state, session=session)

    # 5. Coordinator Node
    def _coordinator_step(state: StylistGraphState) -> dict[str, Any]:
        return coordinator_node(state, session=session, llm_provider=llm_provider)

    # Register nodes
    workflow.add_node("context", _context_step)
    workflow.add_node("wardrobe", _wardrobe_step)
    workflow.add_node("fashion", _fashion_step)
    workflow.add_node("personalization", _personalization_step)
    workflow.add_node("coordinator", _coordinator_step)

    # Register edges (5 agent nodes, 12 directed edges with 2 bounded feedback loops)
    workflow.add_edge(START, "context")
    workflow.add_conditional_edges("context", route_after_context, ["wardrobe", END])
    workflow.add_conditional_edges("wardrobe", route_after_wardrobe, ["fashion", END])
    workflow.add_conditional_edges("fashion", route_after_fashion, ["wardrobe", "personalization", END])
    workflow.add_conditional_edges("personalization", route_after_personalization, ["coordinator", END])
    workflow.add_conditional_edges("coordinator", route_after_coordinator, ["fashion", END])

    return workflow.compile()


def execute_stylist_recommendation(
    state: StylistGraphState,
    *,
    session: Session | None = None,
    clock: Clock | None = None,
    llm_provider: ContextLLMProviderProtocol | None = None,
    weather_provider: WeatherProviderProtocol | None = None,
) -> StylistGraphState:
    """Executes the stylist recommendation workflow with fresh-state normalization.

    Contract:
    - Retains request-owned input: request_id, user_id, user_query, location,
      client_session_id, reference_time.
    - Normalizes reference_time to a timezone-aware UTC datetime.
    - Overwrites caller-supplied agent-owned output fields with fresh defaults to
      prevent stale leaks on early-termination paths.
    - Runs the compiled graph and returns the normalized final state.
    """
    # 1. Resolve and normalize reference_time
    ref_time = state.get("reference_time")
    if ref_time is None:
        ref_time = clock() if clock else datetime.now(timezone.utc)
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)
    else:
        ref_time = ref_time.astimezone(timezone.utc)

    # 2. Fresh state initialization (ignore any caller-provided agent outputs)
    fresh_state: StylistGraphState = {
        "request_id": state.get("request_id", ""),
        "user_id": state.get("user_id", ""),
        "user_query": state.get("user_query", ""),
        "location": state.get("location"),
        "client_session_id": state.get("client_session_id"),
        "reference_time": ref_time,
        "context": None,
        "candidate_pool": _make_empty_candidate_pool(),
        "evaluated_outfits": [],
        "ranked_outfits": [],
        "recommendation_ids": [],
        "grounding_validated": False,
        "feedback_prompt_eligible": False,
        "feedback_target_outfit_id": None,
        "errors": [],
        "warnings": [],
        "enable_agent_loops": state.get("enable_agent_loops", True),
        "enable_relaxation_loop": state.get("enable_relaxation_loop"),
        "enable_critique_loop": state.get("enable_critique_loop"),
        "disable_personalization": bool(state.get("disable_personalization", False)),
        "relaxation_round": 0,
        "relaxation_request": None,
        "active_relaxations": [],
        "critique_round": 0,
        "critique": None,
        "previous_ranked_outfits": [],
        "coordinator_decision": None,
        "conflict_notes": [],
        "agent_trace": [],
    }

    graph = create_stylist_graph(
        session=session,
        clock=clock,
        llm_provider=llm_provider,
        weather_provider=weather_provider,
        enable_agent_loops=bool(fresh_state["enable_agent_loops"]),
    )
    result = graph.invoke(fresh_state, config={"recursion_limit": 25})

    # 3. Defensive state normalization on return
    normalized_result = dict(result)
    pool = normalized_result.get("candidate_pool")
    if not isinstance(pool, dict):
        pool = {}
    normalized_result["candidate_pool"] = {
        "tops": list(pool.get("tops", [])),
        "bottoms": list(pool.get("bottoms", [])),
        "dresses": list(pool.get("dresses", [])),
        "footwear": list(pool.get("footwear", [])),
        "outerwear": list(pool.get("outerwear", [])),
        "accessories": list(pool.get("accessories", [])),
    }
    if normalized_result.get("evaluated_outfits") is None:
        normalized_result["evaluated_outfits"] = []
    if normalized_result.get("ranked_outfits") is None:
        normalized_result["ranked_outfits"] = []
    if normalized_result.get("recommendation_ids") is None:
        normalized_result["recommendation_ids"] = []
    if normalized_result.get("grounding_validated") is None:
        normalized_result["grounding_validated"] = False
    if normalized_result.get("feedback_prompt_eligible") is None:
        normalized_result["feedback_prompt_eligible"] = False
    if "feedback_target_outfit_id" not in normalized_result:
        normalized_result["feedback_target_outfit_id"] = None
    if normalized_result.get("errors") is None:
        normalized_result["errors"] = []
    if normalized_result.get("warnings") is None:
        normalized_result["warnings"] = []
    if normalized_result.get("active_relaxations") is None:
        normalized_result["active_relaxations"] = []
    if normalized_result.get("conflict_notes") is None:
        normalized_result["conflict_notes"] = []
    if normalized_result.get("agent_trace") is None:
        normalized_result["agent_trace"] = []

    return normalized_result  # type: ignore[return-value]
