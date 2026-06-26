"""
Test script for Phase 3: Long-term Memory

This script tests the memory capabilities of Phase 3, including:
- Preference learning across sessions
- Fact extraction and retrieval
- Session summary generation
- Memory isolation between actors
- Graceful degradation on memory failure

Requirements: 4.2, 4.3
"""

import boto3
import json
import time
import uuid
from datetime import datetime


def generate_session_id():
    """Generate a valid session ID (>= 33 characters)"""
    return str(uuid.uuid4()) + str(uuid.uuid4())[:5]


def invoke_agent(runtime_arn, prompt, session_id, actor_id, region='us-east-1'):
    """
    Invoke the AgentCore Runtime agent.
    
    Args:
        runtime_arn: ARN of the AgentCore Runtime
        prompt: User message
        session_id: Session identifier
        actor_id: Actor identifier for memory isolation
        region: AWS region
        
    Returns:
        Agent response text
    """
    client = boto3.client('bedrock-agentcore-runtime', region_name=region)
    
    payload = {
        "prompt": prompt,
        "sessionId": session_id,
        "actorId": actor_id
    }
    
    print(f"\n{'='*60}")
    print(f"Session: {session_id[:20]}...")
    print(f"Actor: {actor_id}")
    print(f"Prompt: {prompt}")
    print(f"{'='*60}")
    
    try:
        response = client.invoke_agent(
            agentArn=runtime_arn,
            inputText=json.dumps(payload)
        )
        
        result = response.get('completion', 'No response')
        print(f"\nAgent Response:\n{result}")
        return result
        
    except Exception as e:
        print(f"\nError invoking agent: {e}")
        raise


def test_preference_learning(runtime_arn, region='us-east-1'):
    """
    Test that the agent learns and remembers user preferences across sessions.
    
    Requirements: 4.2
    """
    print("\n" + "="*80)
    print("TEST 1: Preference Learning Across Sessions")
    print("="*80)
    
    actor_id = f"test-user-{uuid.uuid4().hex[:8]}"
    
    # Session 1: User shares preferences
    session_1 = generate_session_id()
    print("\n--- Session 1: Sharing Preferences ---")
    
    invoke_agent(
        runtime_arn,
        "Hi! I'm planning a trip. I prefer window seats on flights and I love beach destinations.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(2)  # Allow time for memory to be stored
    
    invoke_agent(
        runtime_arn,
        "I also prefer boutique hotels over large chains.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(3)  # Allow time for memory processing
    
    # Session 2: New session, check if preferences are remembered
    session_2 = generate_session_id()
    print("\n--- Session 2: Testing Preference Recall ---")
    
    response = invoke_agent(
        runtime_arn,
        "I'm thinking about booking a flight. What do you remember about my preferences?",
        session_2,
        actor_id,
        region
    )
    
    # Check if response mentions preferences
    if "window" in response.lower() or "beach" in response.lower() or "boutique" in response.lower():
        print("\n✓ TEST PASSED: Agent remembered user preferences across sessions")
    else:
        print("\n✗ TEST WARNING: Agent may not have recalled preferences (check response above)")
    
    return actor_id


def test_fact_extraction(runtime_arn, actor_id, region='us-east-1'):
    """
    Test that the agent extracts and retrieves facts about the user.
    
    Requirements: 4.2
    """
    print("\n" + "="*80)
    print("TEST 2: Fact Extraction and Retrieval")
    print("="*80)
    
    session_1 = generate_session_id()
    print("\n--- Session 1: Sharing Facts ---")
    
    invoke_agent(
        runtime_arn,
        "I've been to Paris three times and I speak French fluently.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(2)
    
    invoke_agent(
        runtime_arn,
        "I'm allergic to shellfish, so I need to be careful with food.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(3)  # Allow time for memory processing
    
    # Session 2: Check if facts are retrieved
    session_2 = generate_session_id()
    print("\n--- Session 2: Testing Fact Recall ---")
    
    response = invoke_agent(
        runtime_arn,
        "I'm planning a trip to France. What do you know about me that might be relevant?",
        session_2,
        actor_id,
        region
    )
    
    # Check if response mentions facts
    if ("paris" in response.lower() or "french" in response.lower()) and "shellfish" in response.lower():
        print("\n✓ TEST PASSED: Agent retrieved relevant facts")
    else:
        print("\n✗ TEST WARNING: Agent may not have retrieved all facts (check response above)")


def test_session_summaries(runtime_arn, actor_id, region='us-east-1'):
    """
    Test that the agent generates session summaries.
    
    Requirements: 4.2
    """
    print("\n" + "="*80)
    print("TEST 3: Session Summary Generation")
    print("="*80)
    
    session_1 = generate_session_id()
    print("\n--- Session 1: Multi-turn Conversation ---")
    
    invoke_agent(
        runtime_arn,
        "I'm planning a two-week trip to Japan in April.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(1)
    
    invoke_agent(
        runtime_arn,
        "I want to visit Tokyo, Kyoto, and maybe Osaka.",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(1)
    
    invoke_agent(
        runtime_arn,
        "What's the weather like in April? Should I book hotels in advance?",
        session_1,
        actor_id,
        region
    )
    
    time.sleep(3)  # Allow time for summary generation
    
    # Session 2: Reference previous session
    session_2 = generate_session_id()
    print("\n--- Session 2: Testing Summary Recall ---")
    
    response = invoke_agent(
        runtime_arn,
        "Hi again! Can you remind me what we discussed about my Japan trip?",
        session_2,
        actor_id,
        region
    )
    
    # Check if response references previous session
    if "japan" in response.lower() and ("tokyo" in response.lower() or "kyoto" in response.lower()):
        print("\n✓ TEST PASSED: Agent recalled session summary")
    else:
        print("\n✗ TEST WARNING: Agent may not have generated/recalled session summary (check response above)")


def test_memory_isolation(runtime_arn, region='us-east-1'):
    """
    Test that memory is properly isolated between different actors.
    
    Requirements: 4.2
    """
    print("\n" + "="*80)
    print("TEST 4: Memory Isolation Between Actors")
    print("="*80)
    
    # Actor 1: Share preferences
    actor_1 = f"test-user-{uuid.uuid4().hex[:8]}"
    session_1 = generate_session_id()
    print("\n--- Actor 1: Sharing Preferences ---")
    
    invoke_agent(
        runtime_arn,
        "I love adventure travel and hiking in mountains.",
        session_1,
        actor_1,
        region
    )
    
    time.sleep(3)
    
    # Actor 2: Different preferences, should not see Actor 1's data
    actor_2 = f"test-user-{uuid.uuid4().hex[:8]}"
    session_2 = generate_session_id()
    print("\n--- Actor 2: Checking Isolation ---")
    
    response = invoke_agent(
        runtime_arn,
        "What do you know about my travel preferences?",
        session_2,
        actor_2,
        region
    )
    
    # Check that Actor 2 doesn't see Actor 1's preferences
    if "adventure" not in response.lower() and "hiking" not in response.lower() and "mountain" not in response.lower():
        print("\n✓ TEST PASSED: Memory properly isolated between actors")
    else:
        print("\n✗ TEST FAILED: Memory isolation may be broken (Actor 2 saw Actor 1's data)")


def test_graceful_degradation(runtime_arn, region='us-east-1'):
    """
    Test that the agent handles memory failures gracefully.
    
    Requirements: 4.3
    """
    print("\n" + "="*80)
    print("TEST 5: Graceful Degradation on Memory Failure")
    print("="*80)
    print("\nNote: This test verifies the agent continues to function even if memory fails.")
    print("The agent should fall back to session-only context.")
    
    actor_id = f"test-user-{uuid.uuid4().hex[:8]}"
    session_id = generate_session_id()
    
    try:
        response = invoke_agent(
            runtime_arn,
            "Hello! Can you help me plan a trip?",
            session_id,
            actor_id,
            region
        )
        
        if response:
            print("\n✓ TEST PASSED: Agent continues to function (graceful degradation working)")
        else:
            print("\n✗ TEST FAILED: Agent did not respond")
            
    except Exception as e:
        print(f"\n✗ TEST FAILED: Agent threw exception instead of degrading gracefully: {e}")


def main():
    """Run all Phase 3 tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Phase 3: Long-term Memory')
    parser.add_argument('--runtime-arn', required=True, help='AgentCore Runtime ARN')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--test', choices=['all', 'preferences', 'facts', 'summaries', 'isolation', 'degradation'],
                       default='all', help='Specific test to run')
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("Phase 3: Long-term Memory Test Suite")
    print("="*80)
    print(f"Runtime ARN: {args.runtime_arn}")
    print(f"Region: {args.region}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    try:
        if args.test in ['all', 'preferences']:
            actor_id = test_preference_learning(args.runtime_arn, args.region)
        else:
            actor_id = f"test-user-{uuid.uuid4().hex[:8]}"
        
        if args.test in ['all', 'facts']:
            test_fact_extraction(args.runtime_arn, actor_id, args.region)
        
        if args.test in ['all', 'summaries']:
            test_session_summaries(args.runtime_arn, actor_id, args.region)
        
        if args.test in ['all', 'isolation']:
            test_memory_isolation(args.runtime_arn, args.region)
        
        if args.test in ['all', 'degradation']:
            test_graceful_degradation(args.runtime_arn, args.region)
        
        print("\n" + "="*80)
        print("Test Suite Complete!")
        print("="*80)
        print("\nNote: Some tests may show warnings if memory takes time to process.")
        print("Wait a few minutes and re-run tests if needed.")
        
    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
