"""
Phase 3: Long-term Memory with AgentCore Memory

This module extends Phase 2 by adding AgentCore Memory for long-term context
retention across sessions. It maintains all Phase 1 and Phase 2 functionality
while adding memory hooks for automatic storage and retrieval.
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError

from strands import Agent
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry, MessageAddedEvent
from strands.tools import tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from ddgs import DDGS

# Utility function for building system prompt with date
def build_system_prompt_with_date(base_prompt: str) -> str:
    """Add current date context to system prompt"""
    current_date = datetime.now().strftime("%B %d, %Y")
    return f"""{base_prompt}

Current Date: {current_date}
When discussing dates, times, or scheduling, use this as your reference point."""

# Base system prompt for Phase 3 (with memory awareness)
PHASE3_SYSTEM_PROMPT_BASE = """You are a helpful travel assistant with long-term memory capabilities. Your role is to help users plan their trips, answer questions about destinations, and provide personalized travel advice based on their history and preferences.

Guidelines:
- Be friendly and conversational
- Ask clarifying questions when needed
- Provide specific, actionable recommendations
- Stay focused on travel-related topics
- Remember context from earlier in the conversation AND from previous sessions
- Use user preferences and history to provide personalized recommendations
- Reference previous trips, preferences, and conversations when relevant
- If content is filtered, acknowledge it gracefully and redirect to helpful travel topics
- Maintain professional and appropriate interactions at all times
- Provide concise responses - be brief and to the point while still being helpful

You have access to:
- Conversation history within this session
- Long-term memory of user preferences from previous sessions
- Web search for finding hotels and travel information

Content safety measures are in place to ensure appropriate interactions."""

# Build final system prompt with current date context
PHASE3_SYSTEM_PROMPT = build_system_prompt_with_date(PHASE3_SYSTEM_PROMPT_BASE)


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
    guardrail_intervened: bool = False,
    memory_retrieved: int = 0
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
    
    if memory_retrieved > 0:
        log_data["memory_items_retrieved"] = memory_retrieved
    
    logger.info(json.dumps(log_data))


def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Get namespace mapping for memory strategies."""
    try:
        strategies = mem_client.get_memory_strategies(memory_id)
        return {i["type"]: i["namespaces"][0] for i in strategies}
    except Exception as e:
        logger.warning(f"Failed to get namespaces: {e}")
        # Return default namespace structure matching deploy-agentcore.py
        return {"USER_PREFERENCE": "travel/{actorId}/preferences"}


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
logger = setup_logging("phase3", level=os.getenv("LOG_LEVEL", "INFO"))

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

# Load configuration from Secrets Manager
GUARDRAIL_ID = get_secret('GUARDRAILS_ID')
GUARDRAIL_VERSION = get_secret("GUARDRAILS_VERSION")
MEMORY_ID = get_secret("MEMORY_ID")

# Initialize Memory Client
memory_client = MemoryClient(region_name=REGION)


class TravelAgentMemoryHooks(HookProvider):
    """Memory hooks for travel agent with long-term memory
    
    Matches memory configuration from deploy-agentcore.py:
    - Strategy: USER_PREFERENCE
    - Namespace: travel/{actorId}/preferences
    - Event expiry: 7 days
    """
    
    def __init__(self, memory_id: str, client: MemoryClient):
        self.memory_id = memory_id
        self.client = client
        self.namespaces = get_namespaces(self.client, self.memory_id)
        self.memory_retrieved_count = 0
    
    def retrieve_user_context(self, event: MessageAddedEvent):
        """Retrieve user context before processing query"""
        messages = event.agent.messages
        if messages[-1]["role"] == "user" and "toolResult" not in messages[-1]["content"][0]:
            user_query = messages[-1]["content"][0]["text"]
            
            try:
                # Get actor_id from agent state
                actor_id = event.agent.state.get("actor_id")
                if not actor_id:
                    logger.warning("Missing actor_id in agent state - skipping memory retrieval")
                    return
                
                # Retrieve user context from all namespaces
                all_context = []
                
                for context_type, namespace in self.namespaces.items():
                    try:
                        memories = self.client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=namespace.format(actorId=actor_id),
                            query=user_query,
                            top_k=3
                        )
                        
                        for memory in memories:
                            if isinstance(memory, dict):
                                content = memory.get('content', {})
                                if isinstance(content, dict):
                                    text = content.get('text', '').strip()
                                    if text:
                                        all_context.append(f"[{context_type.upper()}] {text}")
                    except Exception as e:
                        logger.warning(f"Failed to retrieve {context_type} memories: {e}")
                        continue
                
                # Inject user context into the query
                if all_context:
                    context_text = "\n".join(all_context)
                    original_text = messages[-1]["content"][0]["text"]
                    messages[-1]["content"][0]["text"] = (
                        f"User Context from Previous Sessions:\n{context_text}\n\n"
                        f"Current Query: {original_text}"
                    )
                    self.memory_retrieved_count = len(all_context)
                    logger.info(f"Retrieved {len(all_context)} memory items for actor {actor_id}")
                else:
                    logger.info(f"No memory items found for actor {actor_id}")
                    
            except Exception as e:
                logger.error(f"Failed to retrieve user context: {e}")
                # Continue without memory - graceful degradation
    
    def save_interaction(self, event: AfterInvocationEvent):
        """Save interaction after agent response"""
        try:
            messages = event.agent.messages
            if len(messages) >= 2 and messages[-1]["role"] == "assistant":
                # Get last user query and agent response
                user_query = None
                agent_response = None
                
                for msg in reversed(messages):
                    if msg["role"] == "assistant" and not agent_response:
                        agent_response = msg["content"][0]["text"]
                    elif msg["role"] == "user" and not user_query and "toolResult" not in msg["content"][0]:
                        user_query = msg["content"][0]["text"]
                        break
                
                if user_query and agent_response:
                    # Get session info from agent state
                    actor_id = event.agent.state.get("actor_id")
                    session_id = event.agent.state.get("session_id")
                    
                    if not actor_id or not session_id:
                        logger.warning("Missing actor_id or session_id in agent state - skipping memory save")
                        return
                    
                    # Clean user query if it contains injected context
                    if "User Context from Previous Sessions:" in user_query:
                        # Extract only the current query part
                        parts = user_query.split("Current Query:")
                        if len(parts) > 1:
                            user_query = parts[1].strip()
                    
                    # Save the interaction
                    self.client.create_event(
                        memory_id=self.memory_id,
                        actor_id=actor_id,
                        session_id=session_id,
                        messages=[(user_query, "USER"), (agent_response, "ASSISTANT")]
                    )
                    logger.info(f"Saved interaction to memory for actor {actor_id}")
                    
        except Exception as e:
            logger.error(f"Failed to save interaction: {e}")
            # Continue without saving - graceful degradation
    
    def register_hooks(self, registry: HookRegistry) -> None:
        """Register memory hooks"""
        registry.add_callback(MessageAddedEvent, self.retrieve_user_context)
        registry.add_callback(AfterInvocationEvent, self.save_interaction)
        logger.info("Travel agent memory hooks registered")


# Initialize BedrockAgentCoreApp
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    """
    AgentCore Runtime entrypoint function for Phase 3.
    
    Handles incoming requests, manages sessions, invokes the travel agent with
    long-term memory, and handles guardrail interventions.
    
    Args:
        payload: Request payload containing:
            - prompt (str): User message (required)
            - sessionId (str): Session identifier (required, >= 33 chars)
            - actorId (str): Actor identifier for memory isolation (optional, defaults to session_id)
        context: AgentCore Runtime context (may contain session_id)
            
    Returns:
        str: Agent response text
        
    Raises:
        ValueError: If prompt or sessionId is missing or invalid
        Exception: For model, session, or memory failures
    """
    start_time = datetime.now()
    guardrail_intervened = False
    memory_retrieved = 0
    
    try:
        # Extract and validate input
        user_input = payload.get("prompt")
        if not user_input:
            raise ValueError("No prompt found in input. Please provide a 'prompt' key.")
        
        # Get session ID from frontend (required)
        session_id = (
            payload.get("sessionId") or
            payload.get("session_id") or
            (context.get("session_id") if context else None) or
            (context.get("sessionId") if context else None)
        )
        
        if not session_id:
            raise ValueError("Session ID is required. Please provide 'sessionId' in the request payload.")
        
        if not validate_session_id(session_id):
            raise ValueError(f"Invalid session ID: must be at least 33 characters (received: {len(session_id)} chars)")
        
        # Get actor ID for memory isolation (defaults to session_id if not provided)
        actor_id = (
            payload.get("actorId") or
            payload.get("actor_id") or
            session_id
        )
        
        logger.info(f"Processing request for session: {session_id}, actor: {actor_id}")
        logger.info(f"User input: {user_input}")
        
        # Validate memory configuration
        if not MEMORY_ID:
            logger.warning("MEMORY_ID not configured - memory features will not be available")
        
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
        
        # Initialize memory hooks if memory is configured
        hooks = []
        if MEMORY_ID:
            try:
                memory_hooks = TravelAgentMemoryHooks(MEMORY_ID, memory_client)
                hooks.append(memory_hooks)
                logger.info(f"Initialized memory hooks with memory ID: {MEMORY_ID}")
            except Exception as e:
                logger.warning(f"Failed to initialize memory hooks: {e}")
                logger.warning("Continuing without memory - graceful degradation")
        else:
            logger.info("Memory not configured - running without long-term memory")
        
        # Create agent
        try:
            agent = Agent(
                system_prompt=PHASE3_SYSTEM_PROMPT,
                model=model,
                session_manager=session_manager,
                hooks=hooks,
                tools=[web_search],
                state={"actor_id": actor_id, "session_id": session_id}
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
            
            # Get memory retrieval count if hooks were used
            for hook in hooks:
                if hasattr(hook, 'memory_retrieved_count'):
                    memory_retrieved = hook.memory_retrieved_count
                    break
            
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
            phase="phase3",
            duration=duration,
            status="success" if not guardrail_intervened else "guardrail_intervened",
            guardrail_intervened=guardrail_intervened,
            memory_retrieved=memory_retrieved
        )
        
        logger.info(f"Returning response (length: {len(result)} chars)")
        return result
        
    except ValueError as e:
        # Validation errors
        duration = (datetime.now() - start_time).total_seconds() * 1000
        log_invocation(
            logger=logger,
            session_id=payload.get("session_id", "unknown"),
            phase="phase3",
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
            phase="phase3",
            duration=duration,
            status="error",
            error=str(e)
        )
        logger.error(f"Error in invoke function: {e}")
        raise


if __name__ == "__main__":
    # Run the AgentCore app
    app.run()
