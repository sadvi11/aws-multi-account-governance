# =============================================================================
# AWS Organizations - the account structure
# =============================================================================
# Every enterprise of any size runs multiple AWS accounts. Not because they
# want more accounts, but because an account is the only truly hard boundary
# AWS gives you:
#
#   - IAM can be misconfigured. An account boundary cannot be misconfigured
#     into non-existence.
#   - Service quotas are per account, so one runaway workload cannot exhaust
#     another team's capacity.
#   - Blast radius is per account. A compromised credential in dev reaches
#     nothing in prod.
#   - The bill is per account, so cost attribution needs no tagging discipline
#     to be correct.
#
# The trade is that you now have many accounts to govern, which is what
# Organizations, Organizational Units and Service Control Policies exist for.
# =============================================================================

resource "aws_organizations_organization" "main" {
  # ALL means both consolidated billing and policy control. Without ALL you
  # cannot attach SCPs, which is the entire point of this repository.
  feature_set = "ALL"

  enabled_policy_types = [
    "SERVICE_CONTROL_POLICY",
    "TAG_POLICY",
  ]

  # Services allowed to operate across the whole organization. Each one is a
  # deliberate grant, not a default - anything listed here can see or act
  # across every account.
  aws_service_access_principals = [
    "cloudtrail.amazonaws.com",  # organization-wide audit trail
    "config.amazonaws.com",      # organization-wide compliance recording
    "sso.amazonaws.com",         # IAM Identity Center
    "guardduty.amazonaws.com",   # threat detection, delegated admin
    "securityhub.amazonaws.com", # findings aggregation
    "account.amazonaws.com",     # alternate contacts
  ]
}

# -----------------------------------------------------------------------------
# Organizational Units
#
# The structure follows AWS's own guidance: group accounts by what policy they
# need, NOT by team or product. Teams reorganise; policy requirements do not.
# An OU per team means rewriting the whole hierarchy at the next reorg.
# -----------------------------------------------------------------------------

# Security tooling. Deliberately the first OU, because these accounts are what
# everything else is audited by - they must exist before the workloads do.
resource "aws_organizations_organizational_unit" "security" {
  name      = "Security"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# Shared infrastructure: networking, CI/CD, shared registries. Things many
# accounts consume but nobody owns individually.
resource "aws_organizations_organizational_unit" "infrastructure" {
  name      = "Infrastructure"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# Production workloads. The most restricted OU.
resource "aws_organizations_organizational_unit" "workloads_prod" {
  name      = "Workloads-Prod"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# Non-production. Same guardrails on data residency and root usage, looser on
# instance types and regions so people can experiment.
resource "aws_organizations_organizational_unit" "workloads_nonprod" {
  name      = "Workloads-NonProd"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# Sandbox. Individual experimentation, hard spend limits, and NOT connected to
# the production network. Exists so that "I just want to try something" has a
# safe destination instead of happening in dev.
resource "aws_organizations_organizational_unit" "sandbox" {
  name      = "Sandbox"
  parent_id = aws_organizations_organization.main.roots[0].id
}

# Suspended. Accounts pending closure. Everything is denied here except what is
# needed to extract data and close them - AWS account closure is not instant,
# and an abandoned account with live credentials is a standing risk.
resource "aws_organizations_organizational_unit" "suspended" {
  name      = "Suspended"
  parent_id = aws_organizations_organization.main.roots[0].id
}
