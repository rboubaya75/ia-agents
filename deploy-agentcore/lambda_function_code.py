# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import json
import boto3
import uuid
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('wildrydes-trips-workshop')

def lambda_handler(event, context):
    toolName = context.client_context.custom['bedrockAgentCoreToolName']
    print(context.client_context)
    print(event)
    print(f"Original toolName: , {toolName}")
    delimiter = "___"
    if delimiter in toolName:
        toolName = toolName[toolName.index(delimiter) + len(delimiter):]
    print(f"Converted toolName: , {toolName}")
    
    if toolName == 'create_trip':
        trip_id = str(uuid.uuid4())
        
        item = {
            'userId': event['userId'],
            'tripId': trip_id,
            'tripName': event['tripName'],
            'startDate': event['startDate'],
            'endDate': event['endDate'],
            'createdAt': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
        }
        
        if 'destination' in event:
            item['destination'] = event['destination']
        if 'description' in event:
            item['description'] = event['description']
        
        table.put_item(Item=item)
        
        return {'statusCode': 200, 'body': f"Trip {trip_id} created successfully for user {event['userId']}"}
    
    elif toolName == 'get_trips':
        response = table.query(
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': event['userId']}
        )
        return {'statusCode': 200, 'body': json.dumps(response['Items'])}
    
    elif toolName == 'get_trip':
        response = table.get_item(
            Key={'userId': event['userId'], 'tripId': event['tripId']}
        )
        if 'Item' in response:
            return {'statusCode': 200, 'body': json.dumps(response['Item'])}
        else:
            return {'statusCode': 404, 'body': 'Trip not found'}
    
    elif toolName == 'update_trip':
        update_expression = "SET updatedAt = :updatedAt"
        expression_values = {':updatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}
        
        if 'tripName' in event:
            update_expression += ", tripName = :tripName"
            expression_values[':tripName'] = event['tripName']
        if 'startDate' in event:
            update_expression += ", startDate = :startDate"
            expression_values[':startDate'] = event['startDate']
        if 'endDate' in event:
            update_expression += ", endDate = :endDate"
            expression_values[':endDate'] = event['endDate']
        if 'description' in event:
            update_expression += ", description = :description"
            expression_values[':description'] = event['description']
        
        table.update_item(
            Key={'userId': event['userId'], 'tripId': event['tripId']},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        return {'statusCode': 200, 'body': f"Trip {event['tripId']} updated successfully"}
    
    else:
        return {'statusCode': 400, 'body': "Unsupported operation"}