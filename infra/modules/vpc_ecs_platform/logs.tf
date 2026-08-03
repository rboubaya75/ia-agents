# V2-LLD-001 §12.1 — CloudWatch log groups encrypted by a dedicated CMK.
#
# This is the only observability the MVP provisions. Container Insights, the ADOT
# sidecar and the derived metrics belong to V2-LLD-007, which is deferred.

resource "aws_kms_key" "logs" {
  count = local.create_logs_cmk ? 1 : 0

  description             = "CMK for the ${local.cluster_name} CloudWatch log groups (V2-LLD-001 sec. 12.1)."
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.logs_cmk[0].json

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-logs-cmk"
  })
}

resource "aws_kms_alias" "logs" {
  count = local.create_logs_cmk ? 1 : 0

  name          = "alias/${var.name_prefix}-logs"
  target_key_id = aws_kms_key.logs[0].key_id
}

# §12.1.1 — the erasure audit log group does not live under /ecs/, so a condition
# scoped to /ecs/<cluster>/* would not cover it. It is listed explicitly.
data "aws_iam_policy_document" "logs_cmk" {
  count = local.create_logs_cmk ? 1 : 0

  statement {
    sid       = "AllowAccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid    = "AllowCloudWatchLogsEncryption"
    effect = "Allow"

    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:Describe*",
    ]

    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["logs.${local.region}.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"

      values = compact([
        "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/ecs/${local.cluster_name}/*",
        var.erasure_audit_log_group_name == "" ? "" : "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:${var.erasure_audit_log_group_name}",
      ])
    }
  }
}

resource "aws_cloudwatch_log_group" "fastapi" {
  name              = local.fastapi_log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = local.logs_kms_key_arn

  tags = merge(var.common_tags, {
    Name = local.fastapi_log_group_name
  })
}
