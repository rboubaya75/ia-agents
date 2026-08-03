# V2-LLD-001 §5.1 — Task IAM roles.
#
# ecs-task-role-ingestion (§5.2) is a V3 target and is deliberately not created.
#
# Statements whose target is not yet known are removed rather than pointed at a
# placeholder ARN: a role that grants nothing is auditable, a role that grants
# something on a malformed ARN is not.

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    sid     = "EcsTasksAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:ecs:${local.region}:${local.account_id}:*"]
    }
  }
}

# ---------------------------------------------------------------------------
# Execution role — pulls the image and writes to the log group.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-ecs-task-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = var.common_tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid    = "WriteEncryptedLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.fastapi.arn}:*"]
  }

  # §12.1 — the execution role must be able to encrypt through the log CMK,
  # otherwise the task cannot write a single line.
  statement {
    sid    = "EncryptLogsThroughCmk"
    effect = "Allow"

    actions = [
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:Decrypt",
    ]

    resources = [local.logs_kms_key_arn]
  }

  dynamic "statement" {
    for_each = length(var.fastapi_secrets) > 0 ? [1] : []

    content {
      sid       = "ReadInjectedSecrets"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = values(var.fastapi_secrets)
    }
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "${var.name_prefix}-ecs-task-execution"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# ---------------------------------------------------------------------------
# Task role fastapi — §5.1
# ---------------------------------------------------------------------------

resource "aws_iam_role" "fastapi" {
  name               = "${var.name_prefix}-ecs-task-role-fastapi"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = var.common_tags
}

data "aws_iam_policy_document" "fastapi" {
  dynamic "statement" {
    for_each = var.agentcore_runtime_arn == "" ? [] : [var.agentcore_runtime_arn]

    content {
      sid       = "AgentCoreRuntime"
      effect    = "Allow"
      actions   = ["bedrock-agentcore:InvokeAgent"]
      resources = [statement.value]
    }
  }

  # bedrock:RetrieveAndGenerate is absent by design: V2-LLD-002 §6.1 makes the
  # absence itself the control, not a comment.
  dynamic "statement" {
    for_each = var.knowledge_base_arn == "" ? [] : [var.knowledge_base_arn]

    content {
      sid       = "KnowledgeBaseRetrieveV2"
      effect    = "Allow"
      actions   = ["bedrock-agent-runtime:Retrieve"]
      resources = [statement.value]
    }
  }

  dynamic "statement" {
    for_each = var.knowledge_base_data_source_arn == "" ? [] : [var.knowledge_base_data_source_arn]

    content {
      sid    = "KnowledgeBaseIngestionV2"
      effect = "Allow"

      actions = [
        "bedrock-agent:StartIngestionJob",
        "bedrock-agent:GetIngestionJob",
        "bedrock-agent:ListIngestionJobs",
      ]

      resources = [statement.value]
    }
  }

  dynamic "statement" {
    for_each = length(var.dynamodb_table_arns) > 0 ? [1] : []

    content {
      sid    = "DynamoDBAccess"
      effect = "Allow"

      actions = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:ConditionCheckItem",
      ]

      resources = var.dynamodb_table_arns
    }
  }

  # Command store, deliberately narrower than the statement above.
  # PutItem is withheld because creating a command belongs to the proposal tool,
  # which operates from a distinct role: granting it here would let FastAPI
  # fabricate an authorisation without going through materialisation.
  # DeleteItem is withheld because an application-side delete would reopen the
  # replay window that the executed retention closes.
  dynamic "statement" {
    for_each = length(var.commands_table_arns) > 0 ? [1] : []

    content {
      sid    = "CommandStoreConfirmationOnly"
      effect = "Allow"

      actions = [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:UpdateItem",
      ]

      resources = var.commands_table_arns
    }
  }

  dynamic "statement" {
    for_each = var.documents_bucket_arn == "" ? [] : [var.documents_bucket_arn]

    content {
      sid    = "S3DocumentSource"
      effect = "Allow"

      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
      ]

      resources = ["${statement.value}/*"]
    }
  }

  statement {
    sid    = "KmsDecrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]

    resources = compact([
      local.logs_kms_key_arn,
      var.documents_cmk_arn,
    ])
  }

  statement {
    sid       = "SecretsManagerRead"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:${local.partition}:secretsmanager:${local.region}:${local.account_id}:secret:${var.secrets_path_prefix}/*"]
  }

  # The X-Ray actions of §5.1 are absent: they exist only to serve the ADOT
  # sidecar, which the MVP does not deploy. They come back with V2-LLD-007.
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.fastapi.arn}:*"]
  }
}

resource "aws_iam_role_policy" "fastapi" {
  name   = "${var.name_prefix}-ecs-task-role-fastapi"
  role   = aws_iam_role.fastapi.id
  policy = data.aws_iam_policy_document.fastapi.json
}
