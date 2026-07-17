"""
Schema Validator for the Vedika 2D Mascot Companion.
Contains structural validation rules for LMS Context events, Agent Decisions, and Mascot Commands
to ensure compatibility between the LMS frontend and PyQt agent backend.
"""

import time

# List of valid mascot states
VALID_MASCOT_STATES = {"idle", "thinking", "dance", "sad", "sleep", "wake"}

# List of valid activity types (legacy compatibility)
LEGACY_ACTIVITY_TYPES = {"progress", "quiz", "assignment", "error"}

# List of valid actions (new schema)
VALID_ACTIONS = {"navigate", "submit_quiz", "compile_code", "chat_message", "idle_start"}

# List of valid routes
VALID_ROUTES = {
    "/dashboard", "/ai-tutor", "/grades", "/assignments", "/profile", "/login", "/"
}

# List of valid client actions
VALID_CLIENT_ACTION_TYPES = {"navigate_to_page", "open_external_url", "highlight_element"}


def validate_lms_context(data: dict) -> tuple[bool, str]:
    """
    Validates the LMS context input payload.
    Supports both legacy format (activity_type, data) and new format (action, currentRoute, contextData).
    
    Returns (is_valid, error_message).
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object"
    
    # 1. Legacy Compatibility Check
    is_legacy = "activity_type" in data
    
    if is_legacy:
        act_type = data.get("activity_type")
        if act_type not in LEGACY_ACTIVITY_TYPES:
            return False, f"Invalid legacy 'activity_type': '{act_type}'. Expected one of {LEGACY_ACTIVITY_TYPES}"
        if "data" in data and not isinstance(data["data"], dict):
            return False, "Legacy 'data' parameter must be a JSON object"
        return True, ""
        
    # 2. Approved Plan Schema Check
    # Required parameters
    if "action" not in data:
        return False, "Missing required parameter 'action'"
    
    action = data.get("action")
    if action not in VALID_ACTIONS:
        return False, f"Invalid 'action': '{action}'. Expected one of {VALID_ACTIONS}"
    
    if "currentRoute" in data:
        route = data.get("currentRoute")
        if route not in VALID_ROUTES and not isinstance(route, str):
            return False, f"Invalid 'currentRoute': '{route}'"
            
    if "timestamp" in data:
        if not isinstance(data["timestamp"], (int, float)):
            return False, "'timestamp' must be a numeric Unix timestamp"
            
    if "contextData" in data:
        ctx = data.get("contextData")
        if not isinstance(ctx, dict):
            return False, "'contextData' must be a JSON object"
            
        # Validate specific sub-fields if present
        if "quizScore" in ctx:
            score = ctx["quizScore"]
            if not isinstance(score, (int, float)) or not (0 <= score <= 100):
                return False, "'quizScore' must be a number between 0 and 100"
                
        if "assignmentStatus" in ctx:
            status = ctx["assignmentStatus"]
            valid_statuses = {"assigned", "in_progress", "submitted", "completed"}
            if status not in valid_statuses:
                return False, f"Invalid 'assignmentStatus': '{status}'"

    return True, ""


def validate_agent_decision(data: dict) -> tuple[bool, str]:
    """
    Validates the agent decision payload returned to the companion application or LMS.
    
    Returns (is_valid, error_message).
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object"
    
    # Check 'message'
    if "message" not in data:
        return False, "Missing required parameter 'message'"
    
    message = data.get("message")
    if not isinstance(message, dict):
        return False, "'message' parameter must be a JSON object"
    if "text" not in message:
        return False, "Missing required parameter 'message.text'"
    if not isinstance(message["text"], str):
        return False, "'message.text' must be a string"
    if "tone" in message and not isinstance(message["tone"], str):
        return False, "'message.tone' must be a string"
        
    # Check 'mascot'
    if "mascot" not in data:
        return False, "Missing required parameter 'mascot'"
        
    mascot = data.get("mascot")
    if not isinstance(mascot, dict):
        return False, "'mascot' parameter must be a JSON object"
    if "state" not in mascot:
        return False, "Missing required parameter 'mascot.state'"
    
    state = mascot.get("state")
    if state not in VALID_MASCOT_STATES:
        return False, f"Invalid 'mascot.state': '{state}'. Expected one of {VALID_MASCOT_STATES}"
        
    # Check 'actions' if present
    if "actions" in data:
        actions = data.get("actions")
        if not isinstance(actions, list):
            return False, "'actions' parameter must be an array"
            
        for idx, act in enumerate(actions):
            if not isinstance(act, dict):
                return False, f"Action at index {idx} must be a JSON object"
            if "type" not in act:
                return False, f"Action at index {idx} is missing 'type'"
            act_type = act.get("type")
            if act_type not in VALID_CLIENT_ACTION_TYPES:
                return False, f"Action at index {idx} has invalid type '{act_type}'"
            if "params" in act and not isinstance(act["params"], dict):
                return False, f"Action at index {idx} 'params' must be a JSON object"
                
    return True, ""
