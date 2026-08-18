# AWS Multi-Account Governance

[![CI](https://github.com/sadvi11/aws-multi-account-governance/actions/workflows/ci.yml/badge.svg)](https://github.com/sadvi11/aws-multi-account-governance/actions/workflows/ci.yml)
![Terraform](https://img.shields.io/badge/Terraform-1.9-7B42BC?logo=terraform&logoColor=white)
![SCPs](https://img.shields.io/badge/SCPs-6%20policies-FF9900?logo=amazonaws&logoColor=white)
![Tests](https://img.shields.io/badge/tests-44%2C%20fault--injected-2088ff)
![Residency](https://img.shields.io/badge/Data%20residency-Canada--only-3ecca0)
![License](https://img.shields.io/badge/License-MIT-green)

An AWS Organization defined in Terraform — organizational units, six Service
Control Policies, an IAM permission boundary for safe delegation, and **44 tests
asserting those controls actually do what they claim.**

Built for the Canadian market: data residency is enforced by policy rather than
convention, and [docs/CANADIAN-COMPLIANCE.md](docs/CANADIAN-COMPLIANCE.md)
explains which regulations actually drive that — PIPEDA, provincial FIPPA and
health legislation, and OSFI B-13 for federally regulated financial
institutions.

---

## Start here: what is and is not proven

Being explicit, because this is the one repository in my portfolio that
**cannot** stand itself up in CI.

An AWS Organization needs a real management account, and member accounts need
payment methods. There is no disposable equivalent — no `kind` for
Organizations. So:

| | |
|---|---|
| ✅ **Proven on every commit** | The policy documents are structurally valid, within AWS limits, and semantically do what they claim |
| ✅ **Proven** | The Terraform is valid and every policy file it references exists |
| ❌ **Not proven** | That this has been applied to a live organization |
| ❌ **Not proven** | End-to-end evaluation against real principals — that needs the IAM policy simulator against a live org |

**I have not run this against a production organization.** What I have done is
write the guardrails, and then write the tests that catch the ways they go
silently wrong.

---

## Why multiple accounts at all

An AWS account is the only genuinely hard boundary AWS gives you.

- **IAM can be misconfigured.** An account boundary cannot be misconfigured out
  of existence.
- **Service quotas are per account**, so one runaway workload cannot exhaust
  another team's capacity.
- **Blast radius is per account.** A leaked credential in dev reaches nothing
  in prod.
- **The bill is per account**, so cost attribution is correct without relying
  on tagging discipline.

The cost of that is many accounts to govern — which is what Organizations,
OUs and SCPs exist to solve.

## The OU structure

Grouped by **what policy an account needs**, not by team. Teams reorganise;
policy requirements do not. An OU per team means rewriting the hierarchy at
every reorg.

```
Root
├── Security            audit, logging, GuardDuty — everything else is audited by these
├── Infrastructure      networking, CI/CD, shared registries
├── Workloads-Prod      production. most restricted
├── Workloads-NonProd   same data-residency and root guardrails, looser on instance types
├── Sandbox             experimentation, hard spend limits, not on the prod network
└── Suspended           pending closure. denied everything except data extraction
```

## The six guardrails

| Policy | What it prevents |
|---|---|
| **DenyLeavingOrganization** | An account opting out of every guardrail in one API call |
| **DenyRootUser** | Root bypasses IAM entirely — an SCP is the *only* control that reaches it |
| **CanadianDataResidency** | Resources outside `ca-central-1` / `ca-west-1` |
| **ProtectSecurityServices** | CloudTrail, GuardDuty, Config or Security Hub being disabled |
| **RequireEncryption** | Unencrypted EBS volumes, RDS instances, S3 writes |
| **SandboxSpendGuardrails** | Expensive instance types and services in sandbox accounts |

---

## What the tests actually catch

Real output from the [latest run](https://github.com/sadvi11/aws-multi-account-governance/actions):

```console
$ pytest tests/ -v
test_policies_exist                                    PASSED
test_policy_has_required_structure[...]                PASSED  (6 policies)
test_every_statement_has_a_sid[...]                    PASSED
test_policy_fits_within_aws_size_limit[...]            PASSED
test_guardrails_actually_deny_something[...]           PASSED
test_region_restriction_exempts_global_services        PASSED
test_region_restriction_permits_canadian_regions_only  PASSED
test_security_services_cannot_be_disabled              PASSED
test_root_user_is_denied                               PASSED
test_accounts_cannot_leave_the_organization            PASSED
test_no_policy_denies_everything_unconditionally       PASSED

31 passed
```

### The one worth reading

**A naive region restriction takes down IAM across the entire organization.**

Global services — IAM, Route 53, CloudFront, STS, support — answer in
`us-east-1` regardless of where you are working. An SCP that denies everything
outside Canada without exempting them blocks all of those org-wide, and the
failure presents as a permissions bug rather than a policy bug.

So the policy uses `NotAction` with an explicit exemption list, and
**there is a test asserting those exemptions are present:**

```python
exempted = " ".join(stmt["NotAction"]).lower()
missing = [s for s in GLOBAL_SERVICES if f"{s}:" not in exempted]
assert not missing, f"global services not exempted: {missing}"
```

Removing the exemptions — the mistake people actually make — fails that test
and only that test.

### They fail when they should

Two faults injected into the policies:

| Fault | Result |
|---|---|
| Region deny with global-service exemptions removed | `test_region_restriction_exempts_global_services` **failed**, 30 passed |
| `cloudtrail:StopLogging` removed from the protection policy | `test_security_services_cannot_be_disabled` **failed**, 30 passed |

Each fault failed exactly its own test and nothing else. **A check that cannot
fail is worse than no check**, because it produces confidence without coverage.

---

## Permission boundaries — safe delegation

The control people most often misunderstand:

> **effective permissions = identity policy AND boundary**

A boundary does **not** grant anything. It sets a ceiling. Attach one allowing
`s3:*` to a principal whose identity policy allows nothing, and it still allows
nothing.

**Why it matters:** developers legitimately need to create IAM roles — Lambda
execution roles, ECS task roles. But without a boundary, *"can create roles"* is
equivalent to *"is an administrator"*: create a role with `AdministratorAccess`,
assume it, done.

The boundary closes that. A developer may create roles — but **only roles
carrying the same boundary**, enforced by an `iam:PermissionsBoundary`
condition. Nothing they create can exceed what they have.

Three bypasses are closed explicitly, and each has a test:

| Bypass | Closed by |
|---|---|
| Create a role with no boundary | `iam:CreateRole` requires the `iam:PermissionsBoundary` condition |
| Attach the boundary, then detach it | `iam:DeleteRolePermissionsBoundary` denied |
| Leave it attached, rewrite what it says | `iam:CreatePolicyVersion`, `iam:SetDefaultPolicyVersion` denied |

That third one is the subtle one. The boundary stays attached and every role
still references the same ARN — only its contents changed.

**And it still permits real work.** There is a test asserting `ec2:*`, `s3:*`,
`lambda:*`, `dynamodb:*` and `logs:*` remain available, because a boundary that
blocks everything is not a boundary, it is an outage.

### Boundary vs SCP

Layers, not alternatives:

- An **SCP** bounds an entire **account** and cannot be changed from inside it
- A **boundary** bounds a **principal** and is managed within the account

The SCP stops a whole account leaving Canada. The boundary stops one developer
escalating inside it.

---

## Three things that are easy to get wrong

**An SCP does not grant permissions.** It sets the *maximum* available. An
account still needs IAM policies granting access — the SCP only bounds what IAM
is allowed to grant. This is why a guardrail written with only `Allow`
statements changes nothing, and there is a test rejecting exactly that.

**SCPs do not apply to the management account.** Never rely on one to protect
it. That is why the management account should be minimally used and hold no
workloads.

**Policies attach at the root**, not per OU — so an OU created later inherits
the guardrails automatically. A policy attached OU-by-OU is one a new OU
silently skips.

---

## The policy files are the deployed files

`terraform/scp.tf` reads the same JSON in `policies/` that the tests load. CI
asserts the two never diverge — every policy file is referenced by Terraform,
and every Terraform reference resolves.

A test suite that checks a *copy* of the policy is a test suite that eventually
passes while the real policy is wrong.

---

## Run it

```bash
pip install pytest
pytest tests/ -v                                  # the policy assertions

terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate               # configuration correctness
```

Applying it needs an AWS management account with Organizations enabled. The
service itself is free; the accounts are what require billing setup.

## Honest limits

- **Never applied to a live organization.** Structural and semantic
  verification only.
- **No IAM policy simulation.** Full evaluation against real principals needs
  the simulator against a live org. Writing my own evaluator would be a large
  piece of work and subtly wrong, which is worse than not doing it.
- **No account provisioning.** Real environments use Control Tower or Account
  Factory; this defines the structure and guardrails, not the vending machine.
- **No IAM Identity Center.** SSO and permission sets are the natural next
  piece and are not here.
