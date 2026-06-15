provider "aws" {
  # us-east-1 is required: CloudFront only accepts ACM certs from this region.
  region = "us-east-1"

  # Tagged distinctly from the agentic-fs footprint so a `Project=agentic-fs`
  # teardown-by-tag never sweeps the landing site.
  default_tags {
    tags = {
      Project   = "agenticfs-site"
      ManagedBy = "terraform"
      Repo      = "agentic-fs"
    }
  }
}
