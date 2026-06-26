"""
Phase 2: Content Safety with Guardrails

This module extends Phase 1 by adding Bedrock Guardrails for content filtering
and safety controls. It maintains all Phase 1 functionality while adding
guardrail intervention handling.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, Any
import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.tools import tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from ddgs import DDGS

# Utility function for building system prompt with date
def build_system_prompt_with_date(base_prompt: str) -> str:
    """Add current date context to system prompt"""
    current_date = datetime.now().strftime("%B %d, %Y")
    return f"""{base_prompt}

Current Date: {current_date}
When discussing dates, times, or scheduling, use this as your reference point."""

# Base system prompt for Phase 2 (with safety guidelines)
PHASE2_SYSTEM_PROMPT_BASE = """You are a helpful travel assistant with content safety controls. Your role is to help users plan their trips, answer questions about destinations, and provide travel advice in a safe and appropriate manner.

Guidelines:
- Be friendly and conversational
- Ask clarifying questions when needed
- Provide specific, actionable recommendations
- Stay focused on travel-related topics
- Remember context from earlier in the conversation
- If content is filtered, acknowledge it gracefully and redirect to helpful travel topics
- Maintain professional and appropriate interactions at all times
- Provide concise responses - be brief and to the point while still being helpful

You have access to:
- Conversation history within this session
- Web search for finding hotels and travel information

Content safety measures are in place to ensure appropriate interactions."""

# Build final system prompt with current date context
PHASE2_SYSTEM_PROMPT = build_system_prompt_with_date(PHASE2_SYSTEM_PROMPT_BASE)


# Utility functions
def validate_session_id(session_id: str) -> bool:
    """Validate session ID meets AgentCore requirements (>= 33 characters)."""
    return len(session_id) >= 33


def setup_logging(phase: str, level: str = "INFO") -> logging.Logger:
    """Set up structured logging for the application."""
    logger = logging.getLogger(f"travel-agent-{phase}")
    logger.setLevel(getattr(logging, level.upper()))
    
    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, level.upper()))
    
    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"phase": "' + phase + '", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


def log_invocation(
    logger: logging.Logger,
    session_id: str,
    phase: str,
    duration: float,
    status: str,
    error: str = None,
    guardrail_intervened: bool = False
) -> None:
    """Log agent invocation with structured data."""
    log_data = {
        "event": "agent_invocation",
        "session_id": session_id,
        "phase": phase,
        "duration_ms": duration,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if error:
        log_data["error"] = error
    
    if guardrail_intervened:
        log_data["guardrail_intervened"] = True
    
    logger.info(json.dumps(log_data))


# Web search tool
@tool
def web_search(keywords: str, region: str = "us-en", max_results: int = 5) -> str:
    """Search the web for hotels, destinations, and travel information.
    
    Args:
        keywords: The search query keywords
        region: The search region (default: us-en)
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        Search results with titles and descriptions
    """
    try:
        results = DDGS().text(keywords, region=region, max_results=max_results)
        if not results:
            return "No search results found."
        
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            body = result.get('body', 'No description')
            formatted_results.append(f"{i}. {title}\n   {body}")
        
        return "\n".join(formatted_results)
    except Exception as e:
        return f"Search temporarily unavailable: {str(e)}"


# Set up logging
logger = setup_logging("phase2", level=os.getenv("LOG_LEVEL", "INFO"))

# Configuration
MODEL_ID = os.getenv(
    "MODEL_ID",
    "us.anthropic.claude-sonnet-4-6"
)
REGION = os.getenv("AWS_REGION", "us-east-1")
SESSION_DIR = os.getenv("SESSION_DIR", "/tmp/sessions")

def get_secret(key):
    """Get secret value from AWS Secrets Manager"""
    secrets_client = boto3.client('secretsmanager', region_name=REGION)
    response = secrets_client.get_secret_value(SecretId='wildrydes-secrets')
    secrets = json.loads(response['SecretString'])
    return secrets.get(key)

# Load guardrail configuration from Secrets Manager
GUARDRAIL_ID = get_secret('GUARDRAILS_ID')
GUARDRAIL_VERSION = get_secret("GUARDRAILS_VERSION")


# Initialize BedrockAgentCoreApp
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    """
    AgentCore Runtime entrypoint function for Phase 2.
    
    Handles incoming requests, manages sessions, invokes the travel agent,
    and handles guardrail interventions.
    
    Args:
        payload: Request payload containing:
            - prompt (str): User message (required)
            - sessionId (str): Session identifier (required, >= 33 chars)
        context: AgentCore Runtime context (may contain session_id)
            
    Returns:
        str: Agent response text
        
    Raises:
        ValueError: If prompt or sessionId is missing or invalid
        Exception: For model or session failures
    """
    start_time = datetime.now()
    guardrail_intervened = False
    
    try:
        # Extract and validate input
        user_input = payload.get("prompt")
        if not user_input:
            raise ValueError("No prompt found in input. Please provide a 'prompt' key.")
        
        # Get session ID from frontend (required)
        # Priority: payload > context
        session_id = (
            payload.get("sessionId") or
            payload.get("session_id") or
            (context.get("session_id") if context else None) or
            (context.get("sessionId") if context else None)
        )
        
        # Session ID is required from frontend
        if not session_id:
            raise ValueError("Session ID is required. Please provide 'sessionId' in the request payload.")
        
        if not validate_session_id(session_id):
            raise ValueError(f"Invalid session ID: must be at least 33 characters (received: {len(session_id)} chars)")
        
        logger.info(f"Processing request for session: {session_id}")
        logger.info(f"User input: {user_input}")
        
        # Validate guardrail configuration
        if not GUARDRAIL_ID:
            logger.warning("GUARDRAIL_ID not configured - guardrails will not be applied")
        
        # Initialize Bedrock model with guardrails
        try:
            model_config = {
                "model_id": MODEL_ID,
                "region_name": REGION
            }
            
            # Add guardrail configuration if available
            if GUARDRAIL_ID:
                model_config.update({
                    "guardrail_id": GUARDRAIL_ID,
                    "guardrail_version": GUARDRAIL_VERSION,
                    "guardrail_trace": "enabled"
                    # Note: Not setting guardrail_redact_* to use the guardrail's native configured messages
                })
                logger.info(f"Initialized Bedrock model with guardrails: {GUARDRAIL_ID} v{GUARDRAIL_VERSION}")
            else:
                logger.info(f"Initialized Bedrock model without guardrails: {MODEL_ID}")
            
            model = BedrockModel(**model_config)
            
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock model: {e}")
            raise Exception(f"Model initialization failed: {str(e)}")
        
        # Initialize FileSessionManager
        try:
            session_manager = FileSessionManager(
                session_id=session_id,
                session_dir=SESSION_DIR
            )
            logger.info(f"Initialized FileSessionManager with directory: {SESSION_DIR}")
        except Exception as e:
            logger.error(f"Failed to initialize session manager: {e}")
            raise Exception(f"Session manager initialization failed: {str(e)}")
        
        # Create agent
        try:
            agent = Agent(
                system_prompt=PHASE2_SYSTEM_PROMPT,
                model=model,
                session_manager=session_manager,
                tools=[web_search]
            )
            logger.info("Created Strands Agent successfully")
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise Exception(f"Agent creation failed: {str(e)}")
        
        # Invoke agent
        try:
            logger.info("Invoking agent...")
            response = agent(user_input)
            logger.info("Agent invocation successful")
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}")
            raise Exception(f"Agent invocation failed: {str(e)}")
        
        # Check for guardrail intervention
        if response.stop_reason == "guardrail_intervened":
            guardrail_intervened = True
            logger.warning(f"Guardrail intervention for session {session_id}")
            logger.info(f"Guardrail intervention details: {response.stop_reason}")
        
        # Extract result
        result = response.message["content"][0]["text"]
        
        # Log invocation metrics
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=session_id,
            phase="phase2",
            duration=duration,
            status="success" if not guardrail_intervened else "guardrail_intervened",
            guardrail_intervened=guardrail_intervened
        )
        
        logger.info(f"Returning response (length: {len(result)} chars)")
        return result
        
    except ValueError as e:
        # Validation errors
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=payload.get("session_id", "unknown"),
            phase="phase2",
            duration=duration,
            status="validation_error",
            error=str(e)
        )
        logger.error(f"Validation error: {e}")
        raise
        
    except Exception as e:
        # All other errors
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=payload.get("session_id", "unknown"),
            phase="phase2",
            duration=duration,
            status="error",
            error=str(e)
        )
        logger.error(f"Error in invoke function: {e}")
        raise


if __name__ == "__main__":
    # Run the AgentCore app
    app.run()
