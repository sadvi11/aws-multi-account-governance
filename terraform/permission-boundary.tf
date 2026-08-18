# =============================================================================
# Permission boundary - safe delegation of role creation
# =============================================================================
# The control people most often misunderstand, so precisely:
#
#     effective permissions = identity policy  AND  boundary
#
# A boundary does NOT grant anything. It sets a ceiling. Attaching a boundary
# that allows s3:* to a principal whose identity policy allows nothing still
# allows nothing.
#
# WHY IT IS NEEDED
#
# Developers legitimately need to create IAM roles - Lambda execution roles,
# ECS task roles, roles for their own infrastructure. But without a boundary,
# "can create roles" is equivalent to "is an administrator": create a role
# with AdministratorAccess, assume it, done.
#
# The boundary closes that. A developer may create roles, but only roles that
# carry this same boundary, so nothing they create can exceed it.
#
# HOW IT DIFFERS FROM THE SCPs
#
# An SCP bounds an entire ACCOUNT and cannot be changed from inside it.
# A boundary bounds a PRINCIPAL and is managed within the account.
#
# They are layers, not alternatives. The SCP stops a whole account leaving
# Canada; the boundary stops one developer escalating inside it.
# =============================================================================

resource "aws_iam_policy" "developer_permission_boundary" {
  name        = "DeveloperPermissionBoundary"
  path        = "/"
  description = "Maximum permissions any developer-created role may hold"
  policy      = file("${local.policy_dir}/developer-permission-boundary.json")
}

# An example of the delegation this enables. A developer assuming this role can
# build infrastructure and create roles under /app/, but every role they create
# must carry the boundary - so none of them can exceed it, and neither can they.
resource "aws_iam_role" "developer" {
  name                 = "Developer"
  permissions_boundary = aws_iam_policy.developer_permission_boundary.arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        # In a real organization this is the Identity Center permission set
        # rather than an account principal. Named here so the example is
        # complete without depending on an SSO instance existing.
        AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      }
      Action = "sts:AssumeRole"
      Condition = {
        # MFA required. Without this, a compromised long-lived credential
        # assumes the role directly.
        Bool = { "aws:MultiFactorAuthPresent" = "true" }
      }
    }]
  })
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy_attachment" "developer_power" {
  role = aws_iam_role.developer.name
  # PowerUserAccess grants broadly; the boundary is what makes that safe. This
  # is the intended shape - a generous identity policy intersected with a
  # restrictive ceiling - rather than trying to enumerate every permission.
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

output "permission_boundary_arn" {
  description = "Attach to every developer-created role. Required by the boundary itself."
  value       = aws_iam_policy.developer_permission_boundary.arn
}
