terraform {
  backend "s3" {
    bucket = "tfstate-secure-eks-prod-eu-west-1"
    key    = "secure-agentcore/test/terraform.tfstate"
    region = "eu-west-1"
  }
}
