# ADR 002: Keep policies as JSON files shared by Terraform and the tests

Status: Accepted

## Context

The tests assert what each Service Control Policy denies. If the tests read a
copy of a policy and Terraform deploys the original, the two can drift and the
tests keep passing while the deployed policy is wrong.

## Options considered

1. **Inline JSON in Terraform (`jsonencode`).** Compact, but tests would have to
   parse HCL or duplicate the policy.
2. **JSON files in `policies/`, read with `file()`.** One source of truth that
   both Terraform and pytest load.
3. **Generate policies from Python.** Flexible, but adds a build step between
   what is reviewed and what is deployed.

## Decision

Option 2. CI also checks that every file in `policies/` is referenced from
`terraform/` and every reference resolves.

## Consequences

- The tested artifact is the deployed artifact.
- Policies cannot use Terraform interpolation; anything account-specific must
  be expressed with policy condition keys instead.
- Each policy must stay within the SCP size limit, which CI reports.
