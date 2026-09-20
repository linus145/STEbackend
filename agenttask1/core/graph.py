from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END

from agenttask1.tools.intent_extractor import detect_tool_intent
from agenttask1.tools.payroll_tool import run_payroll_generation_tool


class AgentTaskState(TypedDict):
    user_input: str
    tool_id: Optional[str]
    month: Optional[int]
    year: Optional[int]
    startup: Any
    is_valid: bool
    error_message: Optional[str]
    execution_result: Dict[str, Any]
    summary: str
    audit_logs: List[str]
    status: str


# ==========================================
# Graph Nodes (Deterministic, Zero AI)
# ==========================================

def node_detect_intent(state: AgentTaskState) -> Dict[str, Any]:
    """Node 1: Parses user input to identify tool and extract parameters."""
    logs = list(state.get("audit_logs", []))
    parsed = detect_tool_intent(state.get("user_input", ""))
    
    if not parsed["intent_detected"]:
        logs.append("[DETECTION] No matching automation tool found for query.")
        return {
            "tool_id": None,
            "is_valid": False,
            "error_message": "Could not identify a supported tool from your message. Example: 'Run payroll for September 2026'",
            "audit_logs": logs
        }
    
    params = parsed.get("parameters", {})
    month = state.get("month") or params.get("month")
    year = state.get("year") or params.get("year")
    
    logs.append(f"[DETECTION] Activated Tool: '{parsed['tool_id']}' | Extracted Params: Month={month}, Year={year}")
    
    return {
        "tool_id": parsed["tool_id"],
        "month": month,
        "year": year,
        "audit_logs": logs
    }


def node_validate_parameters(state: AgentTaskState) -> Dict[str, Any]:
    """Node 2: Validates extracted parameters before tool invocation."""
    logs = list(state.get("audit_logs", []))
    month = state.get("month")
    year = state.get("year")

    if not month:
        logs.append("[VALIDATION] Failed: Missing required parameter 'month'.")
        return {
            "is_valid": False,
            "error_message": "Please specify the month (e.g. 'September' or '09').",
            "audit_logs": logs
        }
        
    if not (1 <= month <= 12):
        logs.append(f"[VALIDATION] Failed: Month '{month}' is out of range 1-12.")
        return {
            "is_valid": False,
            "error_message": f"Month '{month}' is invalid. Month must be between 1 and 12.",
            "audit_logs": logs
        }

    if not year or year < 2020 or year > 2035:
        logs.append(f"[VALIDATION] Failed: Invalid year '{year}'.")
        return {
            "is_valid": False,
            "error_message": f"Year '{year}' is invalid. Must be between 2020 and 2035.",
            "audit_logs": logs
        }

    logs.append(f"[VALIDATION] Passed: Period {month:02d}/{year} is valid for processing.")
    return {
        "is_valid": True,
        "error_message": None,
        "audit_logs": logs
    }


def node_execute_tool(state: AgentTaskState) -> Dict[str, Any]:
    """Node 3: Executes the target automation tool deterministically."""
    logs = list(state.get("audit_logs", []))
    month = state["month"]
    year = state["year"]
    startup = state.get("startup")

    logs.append(f"[EXECUTION] Triggering 'run_payroll_generation_tool' for {month:02d}/{year}...")
    result = run_payroll_generation_tool(startup, month, year)

    if result.get("status") == "ERROR":
        logs.append(f"[EXECUTION] Tool error: {result.get('error')}")
        return {
            "execution_result": result,
            "is_valid": False,
            "error_message": result.get("error"),
            "audit_logs": logs
        }

    logs.append(f"[EXECUTION] Completed: {result.get('message', 'Payroll processed successfully.')}")
    return {
        "execution_result": result,
        "audit_logs": logs
    }


def node_format_response(state: AgentTaskState) -> Dict[str, Any]:
    """Node 4: Assembles user-facing summary and final status."""
    logs = list(state.get("audit_logs", []))
    result = state.get("execution_result", {})
    month = state["month"]
    year = state["year"]
    
    emp_count = result.get("employee_count", 0)
    payout = result.get("total_net_payout", 0.0)
    
    summary = (
        f"Generated payroll cycle draft for {month:02d}/{year}. "
        f"Processed {emp_count} active employees with total net payout of INR {payout:,.2f}."
    )
    logs.append("[COMPLETION] Workflow finished successfully.")

    return {
        "status": "SUCCESS",
        "summary": summary,
        "audit_logs": logs
    }


def node_handle_error(state: AgentTaskState) -> Dict[str, Any]:
    """Error Node: Formats error feedback."""
    logs = list(state.get("audit_logs", []))
    err = state.get("error_message", "Unknown error in automation pipeline")
    logs.append(f"[HALTED] {err}")
    return {
        "status": "FAILED",
        "summary": err,
        "audit_logs": logs
    }


# ==========================================
# Routers (Conditional Edges)
# ==========================================

def route_after_detect(state: AgentTaskState) -> str:
    if state.get("tool_id"):
        return "validate_parameters"
    return "handle_error"


def route_after_validate(state: AgentTaskState) -> str:
    if state.get("is_valid"):
        return "execute_tool"
    return "handle_error"


def route_after_execute(state: AgentTaskState) -> str:
    if state.get("is_valid", True) and state.get("execution_result", {}).get("status") != "ERROR":
        return "format_response"
    return "handle_error"


# ==========================================
# Compile StateGraph
# ==========================================

def build_agent_task_graph():
    builder = StateGraph(AgentTaskState)

    builder.add_node("detect_intent", node_detect_intent)
    builder.add_node("validate_parameters", node_validate_parameters)
    builder.add_node("execute_tool", node_execute_tool)
    builder.add_node("format_response", node_format_response)
    builder.add_node("handle_error", node_handle_error)

    builder.add_edge(START, "detect_intent")
    builder.add_conditional_edges(
        "detect_intent",
        route_after_detect,
        {
            "validate_parameters": "validate_parameters",
            "handle_error": "handle_error"
        }
    )
    builder.add_conditional_edges(
        "validate_parameters",
        route_after_validate,
        {
            "execute_tool": "execute_tool",
            "handle_error": "handle_error"
        }
    )
    builder.add_conditional_edges(
        "execute_tool",
        route_after_execute,
        {
            "format_response": "format_response",
            "handle_error": "handle_error"
        }
    )
    builder.add_edge("format_response", END)
    builder.add_edge("handle_error", END)

    return builder.compile()


# Singleton compiled graph
agent_task_pipeline = build_agent_task_graph()
