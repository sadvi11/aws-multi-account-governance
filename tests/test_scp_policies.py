"""Do these Service Control Policies actually do what they claim?

An SCP is a JSON document. It is accepted by AWS if it parses, whether or not
it means what you intended - so "it deployed" proves almost nothing. These
tests check the properties that actually matter, and the ones that are easy to
get subtly wrong.

WHAT THIS IS NOT
----------------
Not a full IAM policy evaluator. Reimplementing AWS's evaluation logic would be
a large piece of work and would be subtly wrong, which is worse than not doing
it. These tests assert structural and semantic properties of the documents
themselves - the class of mistake that ships silently.

For real end-to-end verification you need the IAM policy simulator against a
live organization, which is noted in the README as the honest gap.
"""
import glob
import json
import os

import pytest

POLICY_DIR = os.path.join(os.path.dirname(__file__), "..", "policies")

# AWS quota: an SCP document may not exceed 5120 characters, whitespace
# included. Real policies hit this - it is the reason mature organizations
# split guardrails across several SCPs rather than writing one large one.
MAX_SCP_SIZE = 5120

# Services whose API endpoints are global and answer in us-east-1 regardless of
# where you are working. A region-restricting SCP that does not exempt these
# breaks IAM, Route 53, CloudFront and support access across the whole
# organization - while looking correct.
GLOBAL_SERVICES = ["iam", "organizations", "route53", "cloudfront", "sts", "support"]


def policy_files():
    return sorted(glob.glob(os.path.join(POLICY_DIR, "*.json")))


def load(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture(params=policy_files(), ids=lambda p: os.path.basename(p))
def policy(request):
    return request.param, load(request.param)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
def test_policies_exist():
    assert policy_files(), "no SCPs found - the tests would pass vacuously"


def test_policy_has_required_structure(policy):
    path, doc = policy
    assert doc.get("Version") == "2012-10-17", (
        f"{os.path.basename(path)}: wrong or missing Version. AWS rejects "
        "anything else."
    )
    assert isinstance(doc.get("Statement"), list) and doc["Statement"], (
        f"{os.path.basename(path)}: Statement must be a non-empty list"
    )
    for stmt in doc["Statement"]:
        assert stmt.get("Effect") in ("Allow", "Deny"), "Effect must be Allow or Deny"
        assert "Resource" in stmt, "every statement needs a Resource"
        assert ("Action" in stmt) ^ ("NotAction" in stmt), (
            "a statement takes exactly one of Action or NotAction, never both"
        )


def test_every_statement_has_a_sid(policy):
    """Sids are optional to AWS and essential to humans.

    When a deny fires in production, the Sid is what tells you which rule did
    it. Without one you are reading raw JSON during an incident.
    """
    path, doc = policy
    for i, stmt in enumerate(doc["Statement"]):
        assert stmt.get("Sid"), (
            f"{os.path.basename(path)}: statement {i} has no Sid - an operator "
            "hitting this deny cannot tell which rule caused it"
        )


def test_policy_fits_within_aws_size_limit(policy):
    path, doc = policy
    size = len(json.dumps(doc, separators=(",", ":")))
    assert size <= MAX_SCP_SIZE, (
        f"{os.path.basename(path)}: {size} characters exceeds the {MAX_SCP_SIZE} "
        "limit. Split it across multiple SCPs."
    )


def test_guardrails_actually_deny_something(policy):
    """An SCP with no Deny is almost always a mistake.

    SCPs do not grant permissions - they set the maximum available. An
    Allow-only SCP therefore changes nothing on its own, and reads as a
    guardrail while enforcing nothing.
    """
    path, doc = policy
    effects = {s["Effect"] for s in doc["Statement"]}
    assert "Deny" in effects, (
        f"{os.path.basename(path)}: no Deny statement. SCPs set a ceiling, they "
        "do not grant - this enforces nothing."
    )


# ---------------------------------------------------------------------------
# The subtle one: region restriction
# ---------------------------------------------------------------------------
def test_region_restriction_exempts_global_services():
    """A naive region deny takes down IAM across the organization.

    Global services answer in us-east-1 whatever region you are working in. A
    policy that denies everything outside ca-central-1 without exempting them
    blocks IAM, Route 53, CloudFront and support - and the failure looks like a
    permissions bug, not a policy bug.
    """
    doc = load(os.path.join(POLICY_DIR, "canadian-data-residency.json"))
    stmt = doc["Statement"][0]

    assert "NotAction" in stmt, (
        "region restriction must use NotAction to exempt global services"
    )
    exempted = " ".join(stmt["NotAction"]).lower()
    missing = [s for s in GLOBAL_SERVICES if f"{s}:" not in exempted]
    assert not missing, (
        f"global services not exempted: {missing}. This policy would break them "
        "organization-wide."
    )


def test_region_restriction_permits_canadian_regions_only():
    doc = load(os.path.join(POLICY_DIR, "canadian-data-residency.json"))
    stmt = doc["Statement"][0]

    assert stmt["Effect"] == "Deny"
    allowed = stmt["Condition"]["StringNotEquals"]["aws:RequestedRegion"]
    assert set(allowed) == {"ca-central-1", "ca-west-1"}, (
        f"permitted regions are {allowed}. Data residency requires Canadian "
        "regions only."
    )


# ---------------------------------------------------------------------------
# The guardrails that protect the audit trail
# ---------------------------------------------------------------------------
def test_security_services_cannot_be_disabled():
    """The first move after compromising an account is to stop the logging.

    These denials are what make the audit trail trustworthy. Without them, an
    attacker with admin turns CloudTrail off and the record of what they did
    afterwards does not exist.
    """
    doc = load(os.path.join(POLICY_DIR, "protect-security-services.json"))
    actions = {a.lower() for s in doc["Statement"] for a in s["Action"]}

    required = [
        "cloudtrail:stoplogging",
        "cloudtrail:deletetrail",
        "guardduty:deletedetector",
        "config:deleteconfigurationrecorder",
        "config:stopconfigurationrecorder",
        "securityhub:disablesecurityhub",
    ]
    missing = [a for a in required if a not in actions]
    assert not missing, f"these can still be disabled: {missing}"


def test_root_user_is_denied():
    """Root cannot be restricted by IAM, only by an SCP.

    It bypasses IAM policies entirely and cannot have permission boundaries
    applied. An SCP is the only control that reaches it - which is why this
    exists as a separate policy rather than a statement inside another.
    """
    doc = load(os.path.join(POLICY_DIR, "deny-root-user.json"))
    stmt = doc["Statement"][0]
    assert stmt["Effect"] == "Deny"
    assert stmt["Action"] == "*"
    principal = stmt["Condition"]["StringLike"]["aws:PrincipalArn"]
    assert principal.endswith(":root"), (
        f"condition targets {principal}, which does not match the root principal"
    )


def test_accounts_cannot_leave_the_organization():
    """Leaving the organization removes every SCP at once.

    Without this, any account admin can opt out of all governance in a single
    API call, and the guardrails above stop applying to them.
    """
    doc = load(os.path.join(POLICY_DIR, "deny-leaving-organization.json"))
    actions = {a.lower() for s in doc["Statement"] for a in s["Action"]}
    assert "organizations:leaveorganization" in actions


# ---------------------------------------------------------------------------
# Guarding the guard
# ---------------------------------------------------------------------------
def test_no_policy_denies_everything_unconditionally():
    """A Deny on "*" with no Condition locks every account out, including yours.

    SCPs do not apply to the management account, so this would not lock you out
    of the organization itself - but it would make every member account
    unusable, and recovering means removing the SCP from each OU by hand.
    """
    for path in policy_files():
        doc = load(path)
        for stmt in doc["Statement"]:
            if stmt["Effect"] != "Deny":
                continue
            action = stmt.get("Action")
            wildcard = action == "*" or action == ["*"]
            if wildcard and not stmt.get("Condition"):
                pytest.fail(
                    f"{os.path.basename(path)} statement '{stmt.get('Sid')}' denies "
                    "everything with no condition - every member account would be "
                    "unusable"
                )
