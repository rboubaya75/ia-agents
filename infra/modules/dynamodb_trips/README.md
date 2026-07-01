# dynamodb_trips

DynamoDB table used by the trip tools.

## Keys

- Partition key: `userId`
- Sort key: `tripId`

The table is configured with on-demand billing, server-side encryption and optional point-in-time restore capability.
