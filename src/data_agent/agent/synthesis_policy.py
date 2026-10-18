"""Presentation guidance; factual authority belongs to host deliveries and claims."""
from dataclasses import asdict, dataclass
from html import escape
from typing import Any

@dataclass(frozen=True)
class SynthesisPolicy:
    answer_mode: str
    insight_depth: str
    business_translation: str
    risk_boundary: str
    required_moves: list[str]
    suppressed_moves: list[str]
    wording_style: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



def derive_synthesis_policy(intent=None, state=None, user_input="", data_profile=None,
        tool_error_count=0, user_requirements=None, proficiency=None,
        analysis_spec=None, evidence_records=None, current_request_id=None, **_):
    def get(obj,key,default=None):
        return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)
    route=get(intent,"intent_type","")
    requirements=get(state,"answer_requirements",[]) or []
    from .publication.requirements import presentation_applies
    if current_request_id is None:
        current_request_id = next((r.get("source_message_ref") for r in reversed(requirements) if r.get("source_message_ref")), None)
    active=[r for r in requirements if r.get("lifecycle_status")=="active" and presentation_applies(r,current_request_id)]
    conditional=any(r.get("semantic_kind")=="conditional_action" or "conditional_action" in r.get("purposes",[]) for r in active)
    consultation=route in {"simple_response","knowledge_qa","analysis_consultation","intent_negotiation","data_requirement"}
    direct=route in {"simple_response","data_operation"}
    plan=get(state,"analysis_plan",{}) or {}
    depth="none" if direct else "detailed" if plan.get("depth")=="comprehensive" else "standard"
    styles=[r for r in active if r.get("presentation_role")=="style" and r.get("presentation_style")]
    current_styles=[r for r in styles if r.get("presentation_scope")=="turn"]
    style=next((r["presentation_style"] for r in reversed(current_styles or styles)),None)
    style=style or {"beginner":"plain_language","novice":"plain_language","advanced":"technical_concise","expert":"technical_concise"}.get(proficiency,"balanced")
    return SynthesisPolicy(answer_mode="direct" if direct else "consultation" if consultation else "advisory" if conditional else "analytical",
        insight_depth=depth,business_translation="not_applicable" if consultation or direct else "cautious",
        risk_boundary="host_claims",required_moves=["core_answer"] if direct else ["core_answer","method_note","limitation","next_step"],
        suppressed_moves=[],wording_style=style,
        reason="Original requirements choose presentation; verified host deliveries choose factual coverage. Evidence labels and prose do not grant or suppress facts.")


def build_synthesis_instruction(policy):
    attributes=" ".join(key+'="'+escape(str(getattr(policy,key)),quote=True)+'"' for key in
        ("answer_mode","insight_depth","business_translation","risk_boundary","wording_style"))
    return ('<synthesis_policy '+attributes+'><required_moves>'+escape(",".join(policy.required_moves))+'</required_moves><reason>'+escape(policy.reason)+'</reason></synthesis_policy>'
        '<answer_discipline>Follow the original business goals, expression preferences and constraints. '
        'Use the current host catalogue and claim IDs for data facts, preserving source, unit, window and limitations. '
        'Explain supported results professionally, including competing explanations and the evidence needed to distinguish them. '
        'Keep requested actions conditional on their complete trigger and stop conditions. '
        'Knowledge consultation may use illustrative examples without uploading data. '
        'The existing single local semantic audit checks open explanations; research confidence labels do not approve facts. '
        'Declare necessary typed deliveries before execution using record_analysis_plan; do not read raw data during synthesis. '
        'Return answer_bindings.v2; host rendering supplies verified values and explicit gaps.</answer_discipline>')
