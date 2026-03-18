terraform {
  backend "s3" {
    bucket       = "fm-tfstate-financialmanager-prod"
    key          = "financial-manager/deploy/prodstate/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }
}