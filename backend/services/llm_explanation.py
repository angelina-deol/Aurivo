"""
LLM-generated explanation for a completed investigation (Phase 6).

Deliberately grounded ONLY in data the pipeline actually has: the AASIST
prediction/confidence/fraud_score, audio metadata (duration, sample rate,
channels), and — when available — the attention-derived salient time
regions from ml/inference/aasist_wrapper.py. The prompt explicitly forbids
inventing specific technical claims beyond that data. This matters because
it would be easy (and dishonest) to have an LLM produce confident-sounding
but fabricated detail like "spectral artifacts detected at 2.3s" when no
such per-timestamp analysis actually happened for a given investigation.

Failure here is a soft failure, same as spectrogram generation: an
investigation that got a real AASIST prediction should still complete even
if explanation generation fails or no API key is configured. In that case,
a template-based fallback explanation is used instead of leaving the field
empty — this is worse than an LLM-written one but still informative.
"""
from dataclasses import dataclass

from backend.config import get_settings

settings = get_settings()


@dataclass
class ExplanationInput:
    prediction: str  # "real" | "ai_generated"
    confidence: float  # 0..1
    fraud_score: float  # 0..100
    duration_seconds: float
    sample_rate: int
    channels: int
    attention_regions: list[dict] | None = None  # [{"start": float, "end": float, "salience": float}]


def _template_fallback(data: ExplanationInput) -> str:
    """Used when no ANTHROPIC_API_KEY is configured, or the API call fails.
    Deliberately plain and mechanical rather than trying to sound like a
    generated explanation — no reason to pretend a template is an LLM
    summary."""
    verdict = "AI-generated" if data.prediction == "ai_generated" else "authentic (human) speech"
    confidence_pct = round(data.confidence * 100)
    lines = [
        f"AASIST classified this recording as {verdict} with {confidence_pct}% confidence "
        f"(fraud score: {round(data.fraud_score)}/100).",
        f"Analysis was run on a {data.duration_seconds:.1f}s, {data.sample_rate}Hz, "
        f"{data.channels}-channel clip.",
    ]
    if data.attention_regions:
        top = max(data.attention_regions, key=lambda r: r["salience"])
        lines.append(
            f"The model's attention was most concentrated around "
            f"{top['start']:.1f}s-{top['end']:.1f}s."
        )
    lines.append(
        "(Template-based summary - set ANTHROPIC_API_KEY for a natural-language explanation.)"
    )
    return " ".join(lines)


def _build_prompt(data: ExplanationInput) -> str:
    verdict = "AI-generated" if data.prediction == "ai_generated" else "real (human) speech"
    region_note = ""
    if data.attention_regions:
        top_regions = sorted(data.attention_regions, key=lambda r: -r["salience"])[:3]
        region_desc = "; ".join(f"{r['start']:.1f}s-{r['end']:.1f}s" for r in top_regions)
        region_note = (
            f"\nThe model's internal attention mechanism was most concentrated on these "
            f"time regions (most to least salient): {region_desc}. You may reference these "
            f"as the regions the model focused on, but do not invent what specific artifact "
            f"exists there - the pipeline does not know that, only that attention was higher."
        )

    return (
        "You are writing a brief, plain-language explanation for a voice fraud detection "
        "report. Below is the ONLY data available about this analysis. Do not invent, guess, "
        "or imply any additional technical detail (no specific frequencies, no named artifact "
        "types, no claims about what generated the audio) beyond what is given.\n\n"
        f"- AASIST model verdict: {verdict}\n"
        f"- Confidence: {round(data.confidence * 100)}%\n"
        f"- Fraud score: {round(data.fraud_score)}/100\n"
        f"- Clip duration: {data.duration_seconds:.1f} seconds\n"
        f"- Sample rate: {data.sample_rate} Hz\n"
        f"- Channels: {data.channels}"
        f"{region_note}\n\n"
        "Write 2-3 sentences, plain language, suitable for a non-technical investigator. "
        "State the verdict and confidence level plainly. If confidence is low or middling, "
        "say so honestly rather than overstating certainty."
    )


def generate_explanation(data: ExplanationInput) -> str:
    if not settings.ANTHROPIC_API_KEY:
        return _template_fallback(data)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": _build_prompt(data)}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        explanation = "".join(text_blocks).strip()
        return explanation or _template_fallback(data)
    except Exception:
        return _template_fallback(data)
