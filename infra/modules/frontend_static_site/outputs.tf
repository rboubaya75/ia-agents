output "bucket_name" {
  description = "Private S3 bucket name for frontend assets."
  value       = aws_s3_bucket.frontend.bucket
}

output "bucket_arn" {
  description = "Private S3 bucket ARN."
  value       = aws_s3_bucket.frontend.arn
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID."
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name."
  value       = aws_cloudfront_distribution.frontend.domain_name
}
