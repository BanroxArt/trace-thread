"""Link a payment's legs across rails and test recall and hold policies on a model."""

from .link import Link, Options, Thread, identifier_links, inferred_links, threads
from .model import Case, Leg, LegError, case_from, load_case
from .policy import PolicyError, load_policy, policy_from
from .taint import InstPolicy, Result, Scenario, SimError, simulate

__all__ = [
    "Case",
    "InstPolicy",
    "Leg",
    "LegError",
    "Link",
    "Options",
    "PolicyError",
    "Result",
    "Scenario",
    "SimError",
    "Thread",
    "case_from",
    "identifier_links",
    "inferred_links",
    "load_case",
    "load_policy",
    "policy_from",
    "simulate",
    "threads",
]
__version__ = "0.1.0"
