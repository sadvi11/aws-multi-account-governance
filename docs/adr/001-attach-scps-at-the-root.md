# ADR 001: Attach organisation-wide SCPs at the root

Status: Accepted

## Context

Five of the six guardrails (leaving the organisation, root user, data
residency, security services, encryption) should apply to every member account.
New OUs will be created over time.

## Options considered

1. **Attach each policy to each OU.** Fine-grained, but an OU added later has no
   guardrails until someone remembers to attach them.
2. **Attach at the root.** Policies are inherited by every OU and account below
   it, including OUs created later.
3. **Attach per account.** Maximum control, highest maintenance, easy to miss
   new accounts.

## Decision

Attach the five organisation-wide policies at the root (`for_each` over
`local.organization_wide` in `terraform/scp.tf`). Attach the sandbox spend
policy only to the Sandbox OU, because it is the one control other OUs do not
need.

## Consequences

- New OUs and accounts are covered by default.
- A mistake in a root-attached policy affects every member account, so changes
  should be tried on a test OU first.
- SCPs do not apply to the management account
  ([SCP effects](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)),
  so that account must stay minimal and hold no workloads.
