module "trip_tools_lambda" {
  source = "../../modules/trip_tools_lambda"

  function_name = "${local.name_prefix}-trip-tools"
  source_file   = "${path.root}/../../../deploy-agentcore/lambda_function_code.py"

  trips_table_name = module.dynamodb_trips.table_name
  trips_table_arn  = module.dynamodb_trips.table_arn

  reserved_concurrent_executions = 5
  log_retention_days             = 30
  tags                           = local.common_tags
}

data "aws_iam_policy_document" "gateway_trip_tools" {
  statement {
    sid       = "InvokeOnlyTripToolsLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [module.trip_tools_lambda.function_arn]
  }
}

resource "aws_iam_role_policy" "gateway_trip_tools" {
  name   = "${local.name_prefix}-gateway-trip-tools"
  role   = aws_iam_role.agentcore_gateway.id
  policy = data.aws_iam_policy_document.gateway_trip_tools.json
}

resource "aws_bedrockagentcore_gateway_target" "trip_tools" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name               = "${local.name_prefix}-trip-tools"
  gateway_identifier = aws_bedrockagentcore_gateway.tools_mcp[0].gateway_id
  description        = "Authenticated trip CRUD tools backed by DynamoDB."

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = module.trip_tools_lambda.function_arn

        tool_schema {
          inline_payload {
            name        = "create_trip"
            description = "Create a trip for the authenticated user. userId is injected by Runtime."

            input_schema {
              type = "object"

              property {
                name        = "userId"
                type        = "string"
                description = "Server-injected user identifier."
              }
              property {
                name        = "tripName"
                type        = "string"
                description = "Human-readable trip name."
                required    = true
              }
              property {
                name        = "startDate"
                type        = "string"
                description = "Trip start date in ISO-8601 format."
                required    = true
              }
              property {
                name        = "endDate"
                type        = "string"
                description = "Trip end date in ISO-8601 format."
                required    = true
              }
              property {
                name = "destination"
                type = "string"
              }
              property {
                name = "description"
                type = "string"
              }
              property {
                name = "status"
                type = "string"
              }
            }
          }

          inline_payload {
            name        = "get_trips"
            description = "List trips belonging to the authenticated user. userId is injected by Runtime."

            input_schema {
              type = "object"

              property {
                name        = "userId"
                type        = "string"
                description = "Server-injected user identifier."
              }
            }
          }

          inline_payload {
            name        = "get_trip"
            description = "Retrieve one trip belonging to the authenticated user."

            input_schema {
              type = "object"

              property {
                name        = "userId"
                type        = "string"
                description = "Server-injected user identifier."
              }
              property {
                name        = "tripId"
                type        = "string"
                description = "Trip identifier."
                required    = true
              }
            }
          }

          inline_payload {
            name        = "update_trip"
            description = "Update one trip belonging to the authenticated user."

            input_schema {
              type = "object"

              property {
                name        = "userId"
                type        = "string"
                description = "Server-injected user identifier."
              }
              property {
                name        = "tripId"
                type        = "string"
                description = "Trip identifier."
                required    = true
              }
              property {
                name = "tripName"
                type = "string"
              }
              property {
                name = "startDate"
                type = "string"
              }
              property {
                name = "endDate"
                type = "string"
              }
              property {
                name = "destination"
                type = "string"
              }
              property {
                name = "description"
                type = "string"
              }
              property {
                name = "status"
                type = "string"
              }
            }
          }
        }
      }
    }
  }

  depends_on = [aws_iam_role_policy.gateway_trip_tools]
}
