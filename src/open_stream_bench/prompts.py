"""Benchmark-owned prompt wrappers copied from the current evaluator contract."""

from __future__ import annotations


def build_qa_prompt(question: str, options: list[str]) -> str:
    rendered_options = "\n".join(options)
    return (
        f"Question: {question}\n"
        f"Options:\n{rendered_options}\n\n"
        "Respond only with the letter corresponding to your chosen option "
        "(e.g., A, B, C). Do not include any additional text or explanation."
    )
