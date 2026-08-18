# Why these guardrails, in a Canadian context

Data residency shows up in most cloud governance templates as a nice-to-have.
In Canada it is frequently a legal or regulatory requirement, and which law
applies depends on who the customer is. That changes it from a preference into
a control that has to be *enforced* rather than documented.

This is the reasoning behind `canadian-data-residency.json`.

---

## What actually drives the requirement

**PIPEDA** — the federal private-sector privacy law. It does not require data
to stay in Canada, and this is worth stating accurately because it is commonly
overstated. What it does require is comparable protection wherever data goes,
and transparency with individuals about cross-border transfer. Many
organisations conclude that keeping data in-region is simply cheaper than
demonstrating equivalence.

**Provincial public-sector law is stricter.** British Columbia's FIPPA and Nova
Scotia's PIIDPA have historically imposed direct restrictions on storing
personal information outside Canada for public bodies — which is why public
sector, health authorities and universities in those provinces often treat
in-Canada as non-negotiable.

**Health information** is provincial and stricter again. Ontario's PHIPA,
Alberta's HIA and equivalents govern custodianship of health records, and
health authorities routinely require Canadian regions in procurement.

**OSFI B-13** applies to federally regulated financial institutions — banks,
insurers, federal trust companies. It sets expectations on technology and cyber
risk management including third-party and cloud arrangements. It is not a
residency rule as such, but it drives the control posture: demonstrable
oversight, and evidence rather than assertion.

**Provincial privacy commissioners** in Alberta, BC and Quebec regulate the
private sector under their own legislation, with Quebec's Law 25 adding notably
stronger consent and transfer-assessment obligations.

> **Not legal advice.** This is the engineering-side reasoning for why a
> residency control exists and why it is enforced technically rather than by
> policy document. Which laws apply to a given workload is a question for
> counsel, not for a repository.

---

## What that means for the design

**Residency is enforced by an SCP, not a convention.** An SCP cannot be
switched off from inside the account it applies to — which is exactly the
property an auditor asks about. A wiki page saying "use ca-central-1" is not a
control; it is a hope.

**The two Canadian regions are both permitted.** `ca-central-1` (Montreal) and
`ca-west-1` (Calgary). Restricting to one is a resilience decision, not a
compliance one, and conflating those is how people end up with a single-region
architecture they never chose.

**Global services are exempt, and they have to be.** IAM, Route 53, CloudFront,
STS and support answer in `us-east-1` regardless of where you work. Denying
them breaks the organization while providing no residency benefit — control
plane metadata is not customer data. Getting this wrong is the most common
implementation error, which is why there is a test for it.

**Evidence, not assertion.** CloudTrail cannot be stopped, Config cannot be
disabled, and both are enforced by SCP. Under OSFI-style expectations, "we have
a policy" is much weaker than "the control is technically enforced and here is
the audit trail proving it."

---

## Mapping to the controls in this repository

| Requirement | Control | Where |
|---|---|---|
| Keep regulated data in Canada | Deny all regions except `ca-central-1`, `ca-west-1` | `canadian-data-residency.json` |
| Demonstrate the control cannot be bypassed | SCP at the org root; accounts cannot leave | `deny-leaving-organization.json` |
| Protect data at rest | Deny unencrypted EBS, RDS, S3 writes | `require-encryption.json` |
| Maintain an audit trail | CloudTrail, Config, GuardDuty cannot be disabled | `protect-security-services.json` |
| Restrict privileged access | Root denied; escalation paths closed | `deny-root-user.json`, `developer-permission-boundary.json` |
| Separate duties | OU structure; developers cannot reach Organizations or Identity Center | `organization.tf`, boundary |

---

## The honest gap

This covers the **technical** half. A real compliance position also needs a
data classification scheme, records of processing, vendor assessments, an
incident response plan with regulator notification timelines, and evidence
collected on a schedule.

Infrastructure guardrails make those provable rather than aspirational. They
do not substitute for them.
