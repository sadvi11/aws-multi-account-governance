"""Does the developer permission boundary actually prevent escalation?

A permission boundary is the control people most often misunderstand, so it is
worth being precise about what it is:

    effective permissions = identity policy  AND  boundary

It does NOT grant anything. A boundary allowing s3:* on a principal whose
identity policy allows nothing still allows nothing. It only sets a ceiling.

That makes it the mechanism for safe delegation: developers can create their
own roles - which they need, for Lambda execution roles and similar - without
being able to create a role more powerful than themselves. Without a boundary,
"can create roles" is equivalent to "is an administrator", because they can
create an admin role and assume it.

These tests assert the boundary closes that path.
"""
import json
import os

import pytest

POLICY = os.path.join(
    os.path.dirname(__file__), "..", "policies", "developer-permission-boundary.json"
)

# AWS quota for a customer-managed policy document.
MAX_MANAGED_POLICY_SIZE = 6144


@pytest.fixture(scope="session")
def boundary():
    with open(POLICY) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def denied_actions(boundary):
    out = set()
    for s in boundary["Statement"]:
        if s["Effect"] != "Deny":
            continue
        for a in s["Action"] if isinstance(s["Action"], list) else [s["Action"]]:
            out.add(a.lower())
    return out


def test_boundary_is_within_the_size_limit(boundary):
    size = len(json.dumps(boundary, separators=(",", ":")))
    assert size <= MAX_MANAGED_POLICY_SIZE, (
        f"{size} characters exceeds the {MAX_MANAGED_POLICY_SIZE} limit for a "
        "managed policy"
    )


def test_boundary_denies_the_classic_escalation_paths(denied_actions):
    """Each of these turns "can create roles" into "is an administrator".

    iam:CreateUser + CreateAccessKey - make a new principal outside the boundary.
    iam:AttachUserPolicy             - attach AdministratorAccess to yourself.
    iam:UpdateAssumeRolePolicy       - make an existing privileged role
                                       assumable by you.
    """
    for action in [
        "iam:createuser",
        "iam:createaccesskey",
        "iam:createloginprofile",
        "iam:attachuserpolicy",
        "iam:putuserpolicy",
        "iam:addusertogroup",
        "iam:updateassumerolepolicy",
    ]:
        assert action in denied_actions, f"{action} is not denied - escalation path open"


def test_boundary_cannot_be_removed_from_a_role(denied_actions):
    """The obvious bypass: create a role with the boundary, then detach it.

    Without these denials the boundary is advisory - a developer removes it
    from a role they control and the ceiling is gone.
    """
    for action in [
        "iam:deleterolepermissionsboundary",
        "iam:deleteuserpermissionsboundary",
    ]:
        assert action in denied_actions, f"{action} is not denied - the boundary is removable"


def test_boundary_cannot_be_rewritten(denied_actions):
    """The subtler bypass: leave the boundary attached and edit what it says.

    Creating a new policy version and setting it as default replaces the
    boundary's contents while every role still references the same ARN.
    """
    for action in [
        "iam:createpolicyversion",
        "iam:setdefaultpolicyversion",
        "iam:deletepolicyversion",
    ]:
        assert action in denied_actions, (
            f"{action} is not denied - the boundary can be edited rather than removed"
        )


def test_role_creation_requires_the_boundary_to_be_attached(boundary):
    """Delegation only works if a created role must carry the boundary too.

    Without the iam:PermissionsBoundary condition, a developer creates a role
    with no boundary and gives it whatever they like - and the new role is not
    bounded by anything.
    """
    creation = [
        s
        for s in boundary["Statement"]
        if s["Effect"] == "Allow"
        and any("createrole" in a.lower() for a in (s.get("Action") or []))
    ]
    assert creation, "the boundary does not allow role creation at all"

    for s in creation:
        cond = s.get("Condition", {}).get("StringEquals", {})
        assert "iam:PermissionsBoundary" in cond, (
            "iam:CreateRole is allowed without requiring iam:PermissionsBoundary - "
            "a developer can create an unbounded role"
        )
        assert "DeveloperPermissionBoundary" in cond["iam:PermissionsBoundary"], (
            "the required boundary is not this boundary"
        )


def test_role_creation_is_confined_to_a_path(boundary):
    """Scoping created roles to a path keeps them distinguishable from roles
    the platform team owns, and makes cleanup and auditing possible.
    """
    for s in boundary["Statement"]:
        if s["Effect"] != "Allow":
            continue
        actions = [a.lower() for a in (s.get("Action") or [])]
        if "iam:createrole" not in actions:
            continue
        resources = s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]]
        assert all(r != "*" for r in resources), (
            "role creation is allowed on * - created roles cannot be told apart "
            "from platform-owned ones"
        )


def test_boundary_denies_organization_level_control(denied_actions):
    """A workload account developer has no business touching Organizations,
    account settings, or Identity Center - those live in the management
    account and reach every other account.
    """
    for action in ["organizations:*", "account:*", "sso:*", "identitystore:*"]:
        assert action in denied_actions, f"{action} is not denied"


def test_boundary_denies_disabling_the_audit_trail(denied_actions):
    """Same reasoning as the SCP, applied one layer down.

    Defence in depth: the SCP stops it at the account level, the boundary stops
    it at the principal level. Either alone is a single point of failure.
    """
    for action in [
        "cloudtrail:stoplogging",
        "cloudtrail:deletetrail",
        "config:stopconfigurationrecorder",
        "guardduty:deletedetector",
    ]:
        assert action in denied_actions, f"{action} is not denied"


def test_boundary_still_permits_real_work(boundary):
    """A boundary that blocks everything is not a boundary, it is an outage.

    Developers must still be able to build - compute, storage, data, logs. If
    this list is empty the boundary would be trivially "secure" and useless.
    """
    allowed = set()
    for s in boundary["Statement"]:
        if s["Effect"] != "Allow":
            continue
        for a in s.get("Action") or []:
            allowed.add(a.lower())

    for action in ["ec2:*", "s3:*", "lambda:*", "dynamodb:*", "logs:*"]:
        assert action in allowed, (
            f"{action} is not permitted - developers could not do their job"
        )
