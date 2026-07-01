terraform {
  backend "s3" {
    bucket = "tfstate-secure-eks-prod-eu-west-1"
    key    = "ia-agents/secure-bedrock-agentcore/test/terraform.tfstate"
    region = "eu-west-3"
  }
}
