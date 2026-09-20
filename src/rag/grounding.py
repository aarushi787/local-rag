"""Conservative lexical checks, NOT semantic entailment or an accuracy score."""
from __future__ import annotations
import re

REFUSAL = "I couldn't find that information in the available documents."
_REFUSALS = {
    "i couldn't find that information in the available documents",
    "i don't know from the supplied documents",
    "i couldn't find enough evidence in the available documents to answer that reliably",
}
CITATION = re.compile(r"\[source\s+(\d+)\]", re.I)
_STOP = set("a an the is are was were be been being of to in on at for and it this that".split())
_NEGATION = re.compile(r"\b(?:not|no|never|neither|without|cannot|can't|isn't|wasn't|doesn't|didn't)\b", re.I)


def normalize(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split())


def is_refusal(answer: str) -> bool:
    # Match the entire answer, not a preamble followed by invented facts.
    return normalize(answer).strip(" .!\t\n") in _REFUSALS


def claims_in(answer: str) -> list[str]:
    text = re.sub(r"([.!?])\s*((?:\[source\s+\d+\]\s*)+)", r" \2\1 ", answer, flags=re.I)
    return [s.strip(" -*#\t") for s in re.split(r"(?<!\d)[.!?](?!\d)\s+|\n+", text)
            if s.strip(" -*#\t")]


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+(?:[-/.]\w+)*", normalize(text)) if t not in _STOP]


def support_score(statement: str, evidence: str) -> float:
    wanted = tokens(statement)
    if not wanted or not evidence.strip():
        return 0.0
    # Meaningful words must occur in order within ONE evidence statement.
    # Deliberately conservative: human evaluation is needed for paraphrases.
    for sentence in claims_in(evidence):
        if bool(_NEGATION.search(statement)) != bool(_NEGATION.search(sentence)):
            continue
        available = iter(tokens(sentence))
        if all(any(word == candidate for candidate in available) for word in wanted):
            return 1.0
    return 0.0


def validate_answer(answer: str, sources: list[dict], grounded: bool = True) -> dict:
    result = {"valid": False, "applicable": grounded, "support_rate": 0.0,
              "invalid_citations": [], "uncited_claims": [], "claims": [],
              "method": "ordered_lexical_v1_not_entailment", "refusal": is_refusal(answer)}
    if not grounded or result["refusal"]:
        result.update(valid=True, support_rate=1.0)
        return result
    evidence = {int(s.get("index", n)): str(s.get("evidence_text", s.get("quote", "")))
                for n, s in enumerate(sources, 1)}
    for claim in claims_in(answer):
        indexes = list(dict.fromkeys(int(i) for i in CITATION.findall(claim)))
        statement = CITATION.sub("", claim).strip(" .!?:*\t")
        if not statement:
            continue
        if not indexes:
            result["uncited_claims"].append(statement[:180])
        bad = [i for i in indexes if i not in evidence]
        result["invalid_citations"].extend(bad)
        scores = [support_score(statement, evidence.get(i, "")) for i in indexes]
        supported = bool(scores) and not bad and all(s == 1.0 for s in scores)
        result["claims"].append({"claim": statement, "supporting_sources": indexes,
                                 "support_score": min(scores, default=0.0), "supported": supported})
    claims = result["claims"]
    result["support_rate"] = sum(c["supported"] for c in claims) / len(claims) if claims else 0.0
    result["valid"] = bool(claims) and all(c["supported"] for c in claims)
    result["invalid_citations"] = sorted(set(result["invalid_citations"]))
    return result
