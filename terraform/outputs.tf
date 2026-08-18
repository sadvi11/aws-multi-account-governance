output "organization_id" {
  value = aws_organizations_organization.main.id
}

output "organizational_units" {
  description = "OU names and IDs, for account-creation automation to reference."
  value = {
    security          = aws_organizations_organizational_unit.security.id
    infrastructure    = aws_organizations_organizational_unit.infrastructure.id
    workloads_prod    = aws_organizations_organizational_unit.workloads_prod.id
    workloads_nonprod = aws_organizations_organizational_unit.workloads_nonprod.id
    sandbox           = aws_organizations_organizational_unit.sandbox.id
    suspended         = aws_organizations_organizational_unit.suspended.id
  }
}

output "guardrails_applied_organization_wide" {
  value = keys(local.organization_wide)
}
