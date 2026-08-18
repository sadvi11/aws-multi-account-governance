# =============================================================================
# Service Control Policies
# =============================================================================
# An SCP does NOT grant permissions. It sets the maximum permissions available
# to an account - a ceiling, not a floor. An account still needs IAM policies
# granting access; the SCP only decides what IAM is allowed to grant.
#
# Two consequences people get wrong:
#
#   1. An SCP containing only Allow statements changes nothing on its own.
#      Guardrails are written as Deny.
#   2. SCPs do NOT apply to the management account. Never rely on one to
#      protect it - that is what a separate, minimally-used management account
#      is for.
#
# The policy documents live in ../policies as JSON, so the file the tests
# evaluate is the same file Terraform deploys. A test suite that checks a copy
# is a test suite that eventually diverges.
# =============================================================================

locals {
  policy_dir = "${path.module}/../policies"
}

resource "aws_organizations_policy" "deny_leaving_organization" {
  name        = "DenyLeavingOrganization"
  description = "An account cannot opt out of every guardrail with one API call"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/deny-leaving-organization.json")
}

resource "aws_organizations_policy" "deny_root_user" {
  name        = "DenyRootUser"
  description = "Root bypasses IAM entirely; an SCP is the only control that reaches it"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/deny-root-user.json")
}

resource "aws_organizations_policy" "canadian_data_residency" {
  name        = "CanadianDataResidency"
  description = "Deny regions outside Canada, exempting global services"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/canadian-data-residency.json")
}

resource "aws_organizations_policy" "protect_security_services" {
  name        = "ProtectSecurityServices"
  description = "CloudTrail, GuardDuty, Config and Security Hub cannot be disabled"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/protect-security-services.json")
}

resource "aws_organizations_policy" "require_encryption" {
  name        = "RequireEncryption"
  description = "Unencrypted EBS, RDS and S3 writes are denied"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/require-encryption.json")
}

resource "aws_organizations_policy" "sandbox_spend_guardrails" {
  name        = "SandboxSpendGuardrails"
  description = "Sandbox accounts cannot launch expensive instance types or services"
  type        = "SERVICE_CONTROL_POLICY"
  content     = file("${local.policy_dir}/sandbox-spend-guardrails.json")
}

# -----------------------------------------------------------------------------
# Attachments
#
# Attached at the ROOT, so they apply everywhere including OUs added later. A
# guardrail attached per-OU is a guardrail that a new OU silently skips.
# -----------------------------------------------------------------------------
locals {
  organization_wide = {
    leaving    = aws_organizations_policy.deny_leaving_organization.id
    root_user  = aws_organizations_policy.deny_root_user.id
    residency  = aws_organizations_policy.canadian_data_residency.id
    security   = aws_organizations_policy.protect_security_services.id
    encryption = aws_organizations_policy.require_encryption.id
  }
}

resource "aws_organizations_policy_attachment" "root" {
  for_each = local.organization_wide

  policy_id = each.value
  target_id = aws_organizations_organization.main.roots[0].id
}

# Sandbox gets one additional restriction the rest do not need.
resource "aws_organizations_policy_attachment" "sandbox_spend" {
  policy_id = aws_organizations_policy.sandbox_spend_guardrails.id
  target_id = aws_organizations_organizational_unit.sandbox.id
}
