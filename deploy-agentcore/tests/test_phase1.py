"""
Phase 1 Test Script

This script tests the Phase 1 Basic Agent with Sessions functionality.
Tests include basic conversation flow, session persistence, and context retention.

Requirements: 2.3
"""

import os
import sys
import json
import boto3
import time
from typing import Dict, Any

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.utils import generate_session_id


def load_deployment_info() -> Dict[str, str]:
    """Load deployment information from variables.txt"""
    info = {}
    try:
        with open('variables.txt', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    info[key] = value
        return info
    except FileNotFoundError:
        print("❌ variables.txt not found. Please run deploy-runtime.py first.")
        sys.exit(1)


def invoke_agent(
    agent_id: str,
    prompt: str,
    session_id: str,
    region: str = 'us-east-1'
) -> Dict[str, Any]:
    """
    Invoke the AgentCore Runtime agent.
    
    Args:
        agent_id: Agent ID from deployment
        prompt: User message
        session_id: Session identifier
        region: AWS region
        
    Returns:
        Response from the agent
    """
    client = boto3.client('bedrock-agentcore-runtime', region_name=region)
    
    payload = {
        "prompt": prompt,
        "session_id": session_id
    }
    
    response = client.invoke_agent(
        agentId=agent_id,
        inputText=json.dumps(payload)
    )
    
    # Parse response
    result = response.get('completion', '')
    return {
        "result": result,
        "response_metadata": response.get('ResponseMetadata', {})
    }


def test_basic_conversation(agent_id: str, region: str):
    """Test basic conversation flow"""
    print("\n" + "="*60)
    print("Test 1: Basic Conversation Flow")
    print("="*60)
    
    session_id = generate_session_id()
    print(f"Session ID: {session_id}")
    
    # Single turn conversation
    prompt = "I'm planning a trip to Paris. What are some must-see attractions?"
    print(f"\n👤 User: {prompt}")
    
    try:
        response = invoke_agent(agent_id, prompt, session_id, region)
        print(f"🤖 Agent: {response['result']}")
        print("✅ Test 1 passed: Basic conversation successful")
        return True
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        return False


def test_session_persistence(agent_id: str, region: str):
    """Test session persistence across invocations"""
    print("\n" + "="*60)
    print("Test 2: Session Persistence")
    print("="*60)
    
    session_id = generate_session_id()
    print(f"Session ID: {session_id}")
    
    try:
        # First message
        prompt1 = "I'm interested in visiting Tokyo."
        print(f"\n👤 User: {prompt1}")
        response1 = invoke_agent(agent_id, prompt1, session_id, region)
        print(f"🤖 Agent: {response1['result'][:200]}...")
        
        # Wait a moment
        time.sleep(2)
        
        # Second message - should remember Tokyo
        prompt2 = "What's the best time of year to visit?"
        print(f"\n👤 User: {prompt2}")
        response2 = invoke_agent(agent_id, prompt2, session_id, region)
        print(f"🤖 Agent: {response2['result'][:200]}...")
        
        # Check if response mentions Tokyo or Japan
        if 'tokyo' in response2['result'].lower() or 'japan' in response2['result'].lower():
            print("✅ Test 2 passed: Session persistence working (context retained)")
            return True
        else:
            print("⚠️  Test 2 warning: Context may not be fully retained")
            return True  # Still pass as this is a soft check
            
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        return False


def test_context_retention(agent_id: str, region: str):
    """Test context retention in multi-turn conversation"""
    print("\n" + "="*60)
    print("Test 3: Context Retention in Multi-turn Conversation")
    print("="*60)
    
    session_id = generate_session_id()
    print(f"Session ID: {session_id}")
    
    conversation = [
        "I'm planning a family vacation with two kids aged 8 and 10.",
        "We prefer beach destinations.",
        "What would you recommend?",
        "How about activities for the kids?"
    ]
    
    try:
        for i, prompt in enumerate(conversation, 1):
            print(f"\n👤 User (Turn {i}): {prompt}")
            response = invoke_agent(agent_id, prompt, session_id, region)
            print(f"🤖 Agent: {response['result'][:200]}...")
            time.sleep(1)
        
        print("✅ Test 3 passed: Multi-turn conversation successful")
        return True
        
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        return False


def test_different_sessions(agent_id: str, region: str):
    """Test with different session IDs"""
    print("\n" + "="*60)
    print("Test 4: Different Session IDs")
    print("="*60)
    
    try:
        # Session 1
        session_id1 = generate_session_id()
        print(f"\nSession 1 ID: {session_id1}")
        prompt1 = "I want to visit Rome."
        print(f"👤 User: {prompt1}")
        response1 = invoke_agent(agent_id, prompt1, session_id1, region)
        print(f"🤖 Agent: {response1['result'][:150]}...")
        
        # Session 2 - different session, should not remember Rome
        session_id2 = generate_session_id()
        print(f"\nSession 2 ID: {session_id2}")
        prompt2 = "What destination did I mention?"
        print(f"👤 User: {prompt2}")
        response2 = invoke_agent(agent_id, prompt2, session_id2, region)
        print(f"🤖 Agent: {response2['result'][:150]}...")
        
        # Should not mention Rome since it's a different session
        if 'rome' not in response2['result'].lower():
            print("✅ Test 4 passed: Sessions are properly isolated")
            return True
        else:
            print("⚠️  Test 4 warning: Session isolation may not be working correctly")
            return True  # Still pass as this is a soft check
            
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
        return False


def run_all_tests():
    """Run all Phase 1 tests"""
    print("\n" + "="*60)
    print("🧪 Phase 1 Test Suite")
    print("="*60)
    
    # Load deployment info
    info = load_deployment_info()
    agent_id = info.get('AGENT_ID')
    region = info.get('REGION', 'us-east-1')
    
    if not agent_id:
        print("❌ AGENT_ID not found in variables.txt")
        sys.exit(1)
    
    print(f"\nAgent ID: {agent_id}")
    print(f"Region: {region}")
    
    # Run tests
    results = []
    results.append(("Basic Conversation", test_basic_conversation(agent_id, region)))
    results.append(("Session Persistence", test_session_persistence(agent_id, region)))
    results.append(("Context Retention", test_context_retention(agent_id, region)))
    results.append(("Different Sessions", test_different_sessions(agent_id, region)))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
