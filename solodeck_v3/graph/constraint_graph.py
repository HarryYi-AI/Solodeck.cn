from __future__ import annotations


def derive_constraints_from_kg(kg_context: dict) -> dict:
    forbidden = []
    confounders = []
    for edge in kg_context.get("edges", []):
        if edge.get("type") == "may_confound":
            confounders.append(edge["source"].replace("Column:", ""))
        if edge.get("type") == "forbidden_direction":
            forbidden.append([edge["source"], edge["target"]])
    forbidden.extend([["revenue", "platform"], ["conversions", "title_style"], ["consultations", "topic"]])
    return {"candidate_confounders": sorted(set(confounders)), "forbidden_edges": forbidden}

