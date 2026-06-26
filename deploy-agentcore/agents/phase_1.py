"""
Phase 1: Basic Agent with Sessions

This module implements a basic travel agent using Strands Agents SDK with
session management via FileSessionManager. This is the foundation phase that
demonstrates conversational AI with context retention within a session.

Requirements: 2.1, 2.2, 2.3, 2.5
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, Any

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

# Base system prompt for Phase 1
PHASE1_SYSTEM_PROMPT_BASE = """You are a helpful travel assistant. Your role is to help users plan their trips, answer questions about destinations, and provide travel advice.

Guidelines:
- Be friendly and conversational
- Ask clarifying questions when needed
- Provide specific, actionable recommendations
- Stay focused on travel-related topics
- Remember context from earlier in the conversation
- Provide concise responses - be brief and to the point while still being helpful

You have access to:
- Conversation history within this session
- Web search for finding hotels and travel information"""

# Build final system prompt with current date context
PHASE1_SYSTEM_PROMPT = build_system_prompt_with_date(PHASE1_SYSTEM_PROMPT_BASE)


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
    error: str = None
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
logger = setup_logging("phase1", level=os.getenv("LOG_LEVEL", "INFO"))

# Configuration
MODEL_ID = os.getenv(
    "MODEL_ID",
    "us.anthropic.claude-sonnet-4-6"
)
REGION = os.getenv("AWS_REGION", "us-east-1")
SESSION_DIR = os.getenv("SESSION_DIR", "/tmp/sessions")

# Initialize BedrockAgentCoreApp
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    """
    AgentCore Runtime entrypoint function for Phase 1.
    
    Handles incoming requests, manages sessions, and invokes the travel agent.
    
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
    
    try:
        # Extract and validate input
        user_input = payload.get("prompt")
        if not user_input:
            raise ValueError("No prompt found in input. Please provide a 'prompt' key.")
        
        # Get session ID from frontend (required)
        # Priority: payload > context
        session_id = (
            payload.get("sessionId") or  # Frontend sends in body
            payload.get("session_id") or  # Alternative naming
            (context.get("session_id") if context else None) or  # AgentCore context
            (context.get("sessionId") if context else None)  # Alternative in context
        )
        
        # Session ID is required from frontend
        if not session_id:
            raise ValueError("Session ID is required. Please provide 'sessionId' in the request payload.")
        
        if not validate_session_id(session_id):
            raise ValueError(f"Invalid session ID: must be at least 33 characters (received: {len(session_id)} chars)")
        
        logger.info(f"Processing request for session: {session_id}")
        logger.info(f"User input: {user_input}")
        
        # Initialize Bedrock model
        try:
            model = BedrockModel(
                model_id=MODEL_ID,
                region_name=REGION
            )
            logger.info(f"Initialized Bedrock model: {MODEL_ID}")
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
                system_prompt=PHASE1_SYSTEM_PROMPT,
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
        
        # Extract result
        result = response.message["content"][0]["text"]
        
        # Log invocation metrics
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=session_id,
            phase="phase1",
            duration=duration,
            status="success"
        )
        
        logger.info(f"Returning response (length: {len(result)} chars)")
        return result
        
    except ValueError as e:
        # Validation errors
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=payload.get("session_id", "unknown"),
            phase="phase1",
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
            phase="phase1",
            duration=duration,
            status="error",
            error=str(e)
        )
        logger.error(f"Error in invoke function: {e}")
        raise


if __name__ == "__main__":
    # Run the AgentCore app
    app.run() 