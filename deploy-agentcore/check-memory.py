# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging
from bedrock_agentcore.memory import MemoryClient
import boto3
import os

REGION = os.environ.get('AWS_REGION', 'us-east-1')
memory_id = '<PASTE_MEMORY_ID_ERE'
actorId = ''

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

client = MemoryClient(region_name=REGION)

# Helper function to get namespaces from memory strategies list
def get_namespaces(mem_client: MemoryClient, memory_id: str) -> dict:
    """Get namespace mapping for memory strategies."""
    strategies = mem_client.get_memory_strategies(memory_id)
    return {i["type"]: i["namespaces"][0] for i in strategies}

namespaces_dict = get_namespaces(client, memory_id)
print (namespaces_dict)

# Check stored customer memories
print("\n📚 Customer Memory Summary:")
print("=" * 50)
for context_type, namespace_template in namespaces_dict.items():
    namespace = namespace_template.replace("{actorId}", actorId)
    
    try:
        memories = client.retrieve_memories(
            memory_id=memory_id,
            namespace=namespace,
            query="customer orders and preferences",
            top_k=3
        )
        
        print(f"\n{context_type.upper()} ({len(memories)} items):")
        for i, memory in enumerate(memories, 1):
            if isinstance(memory, dict):
                content = memory.get('content', {})
                if isinstance(content, dict):
                    text = content.get('text', '')[:150] + "..."
                    print(f"  {i}. {text}")
                    
    except Exception as e:
        print(f"Error retrieving {context_type} memories: {e}")

print("\n" + "=" * 50)
