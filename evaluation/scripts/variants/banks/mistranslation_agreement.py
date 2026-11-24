"""Shared requirement for grammatical companions to a factual substitution."""

POLICY = """
Written gender agreement is REQUIRED, not a nonblocking contradiction flag. When a substitution
explicitly makes a referent female or male, every pronoun clearly referring to that same entity
in the displayed context must agree (e.g. 女儿…她, female-only 女儿们…她们). A definite mismatch
fails gender_agreement when that check exists, otherwise fluent. Mark uncertain only when the
referent itself cannot be resolved sufficiently to judge. Do not infer gender from proper names
or outside Bible knowledge, change pronouns referring to other people, or reject ordinary Chinese
implicit subjects. An explicitly different actor later in the passage is not automatically the
same referent. Wrong facts and ambiguous references may still be flagged separately.
The writer must bundle a gender-changing substitution with its necessary grammatical companions.
In a nested ladder they must enter at the SAME dose and persist together at every higher dose;
do not postpone a required companion until a later level. Count every companion's source span
in the dose. If a coherent nested combination cannot fit the dose, hold it instead of approving
the mismatch. Review actual wording; never silently assume a missing pronoun has been repaired.
"""
