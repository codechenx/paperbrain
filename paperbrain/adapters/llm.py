import json
import re
from typing import Protocol

from paperbrain.adapters.openai_client import OpenAIClient
from paperbrain.utils import normalize_email, slugify


class LLMAdapter(Protocol):
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        ...

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        ...

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        ...


_THEME_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "can",
    "could",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "why",
    "with",
}


def _infer_theme_from_text(question: str, *, fallback: str = "research theme") -> str:
    text = " ".join(question.lower().split())
    if not text:
        return fallback

    has_microbiome = "microbiome" in text or "microbiota" in text
    has_gut = "gut" in text
    has_lung = "lung" in text
    has_cancer = "cancer" in text
    has_treatment = any(token in text for token in ("treatment", "therapy", "therapeutic"))
    has_infection = "infection" in text or "infectious" in text

    if has_gut and has_microbiome and has_lung and has_cancer:
        return "gut microbiome and lung cancer treatment"
    if has_lung and has_microbiome and has_infection:
        return "lung microbiome and lung infection"

    concepts: list[str] = []
    if has_gut and has_microbiome:
        concepts.append("gut microbiome")
    if has_lung and has_microbiome:
        concepts.append("lung microbiome")
    if has_lung and has_cancer:
        concepts.append("lung cancer treatment" if has_treatment else "lung cancer")
    if has_lung and has_infection:
        concepts.append("lung infection")
    if has_microbiome and "subspecies" in text:
        concepts.append("microbiome subspecies")
    if any(token in text for token in ("mash", "masld", "nash", "steatohepatitis")):
        concepts.append("metabolic liver disease")
    if "biomarker" in text and any(token in text for token in ("blood", "serum")):
        concepts.append("blood biomarkers")

    deduped_concepts: list[str] = []
    seen_concepts: set[str] = set()
    for concept in concepts:
        if concept in seen_concepts:
            continue
        seen_concepts.add(concept)
        deduped_concepts.append(concept)

    if len(deduped_concepts) >= 2:
        return f"{deduped_concepts[0]} and {deduped_concepts[1]}"
    if len(deduped_concepts) == 1:
        return deduped_concepts[0]

    sanitized = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in sanitized.split() if len(token) > 2 and token not in _THEME_STOPWORDS]
    if not tokens:
        return fallback
    return " ".join(tokens[:5])


def _extract_person_seeds(paper_cards: list[dict]) -> list[dict]:
    def _parse_author_seed(author_value: object) -> tuple[str, str, str]:
        if isinstance(author_value, dict):
            name = str(author_value.get("name", "")).strip()
            email = normalize_email(str(author_value.get("email", "")))
            affiliation = str(author_value.get("affiliation", "")).strip()
            if email and not name:
                name = email.split("@", 1)[0]
            return name, email, affiliation

        raw = str(author_value).strip()
        if not raw:
            return "", "", ""
        match = re.match(r"^\s*(.*?)\s*<\s*([^>]+)\s*>\s*$", raw)
        if match:
            name = match.group(1).strip()
            email = normalize_email(match.group(2))
            if email:
                return name or email.split("@", 1)[0], email, ""
        email = normalize_email(raw)
        if email:
            return email.split("@", 1)[0], email, ""
        return raw, "", ""

    cards_by_key: dict[str, dict] = {}
    for paper_card in paper_cards:
        paper_slug = str(paper_card.get("slug", "")).strip()
        authors = paper_card.get("corresponding_authors", [])
        if not isinstance(authors, list):
            continue
        for author in authors:
            name, email, affiliation = _parse_author_seed(author)
            identity = email or name
            if not identity:
                continue
            key = identity.casefold()
            inferred_affiliation = affiliation or (email.split("@", 1)[1] if email and "@" in email else "Unknown affiliation")
            card = cards_by_key.setdefault(
                key,
                {
                    "slug": f"people/{slugify(identity)}",
                    "type": "person",
                    "name": name,
                    "email": email,
                    "affiliation": inferred_affiliation,
                    "related_papers": [],
                },
            )
            if name and not card["name"]:
                card["name"] = name
            if email and not card["email"]:
                card["email"] = email
            if inferred_affiliation and (
                not card["affiliation"] or str(card["affiliation"]).strip().lower() == "unknown affiliation"
            ):
                card["affiliation"] = inferred_affiliation
            if paper_slug and paper_slug not in card["related_papers"]:
                card["related_papers"].append(paper_slug)
    return [cards_by_key[key] for key in sorted(cards_by_key)]


def _derive_person_cards(paper_cards: list[dict]) -> list[dict]:
    return _extract_person_seeds(paper_cards)


def _derive_topic_cards(person_cards: list[dict]) -> list[dict]:
    if not person_cards:
        return []

    def _as_list(value: object) -> list[str]:
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, list):
            output: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized = item.strip()
                else:
                    normalized = str(item).strip()
                if normalized:
                    output.append(normalized)
            return output
        return []

    def _collect_related_papers(person_card: dict) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for key in ("related_papers", "paper_slugs", "papers"):
            for slug in _as_list(person_card.get(key)):
                if slug in seen:
                    continue
                seen.add(slug)
                output.append(slug)
        return output

    def _merge_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            output.append(normalized)
        return output

    def _collect_big_questions(person_card: dict, related_papers: list[str]) -> list[dict]:
        raw = person_card.get("big_questions")
        questions: list[dict] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                if not question:
                    continue
                why = str(item.get("why_important", item.get("why", ""))).strip() or "(missing)"
                papers = _as_list(item.get("related_papers")) or list(related_papers)
                questions.append(
                    {
                        "question": question,
                        "why_important": why,
                        "related_papers": papers,
                    }
                )
        return questions

    topic_cards_by_slug: dict[str, dict] = {}
    for person_card in person_cards:
        person_slug = str(person_card.get("slug", "")).strip()
        related_papers = _collect_related_papers(person_card)
        questions = _collect_big_questions(person_card, related_papers)
        if not questions:
            fallback_areas = _as_list(person_card.get("focus_area")) + _as_list(person_card.get("focus_areas"))
            if fallback_areas:
                questions = [
                    {
                        "question": f"How can advances in {area} improve outcomes?",
                        "why_important": "Defines major open directions for the topic.",
                        "related_papers": list(related_papers),
                    }
                    for area in fallback_areas
                ]
            else:
                questions = [
                    {
                        "question": "How can this research theme advance the field?",
                        "why_important": "Defines major open directions for the topic.",
                        "related_papers": list(related_papers),
                    }
                ]

        for big_question in questions:
            fallback_area = (_as_list(person_card.get("focus_area")) + _as_list(person_card.get("focus_areas")) + ["research theme"])[0]
            theme = _infer_theme_from_text(str(big_question.get("question", "")), fallback=fallback_area)
            theme_slug = slugify(theme)
            if not theme_slug:
                continue
            topic_slug = f"topics/{theme_slug}"
            topic_card = topic_cards_by_slug.setdefault(
                topic_slug,
                {
                    "slug": topic_slug,
                    "type": "topic",
                    "topic": theme,
                    "related_big_questions": [],
                    "related_people": [],
                    "related_papers": [],
                },
            )
            if person_slug and person_slug not in topic_card["related_people"]:
                topic_card["related_people"].append(person_slug)
            question_papers = _as_list(big_question.get("related_papers")) or list(related_papers)
            for paper_slug in question_papers:
                if paper_slug not in topic_card["related_papers"]:
                    topic_card["related_papers"].append(paper_slug)
            entry = {
                "question": str(big_question.get("question", "")).strip() or "(missing)",
                "why_important": str(big_question.get("why_important", big_question.get("why", "(missing)"))).strip()
                or "(missing)",
                "related_papers": _collect_related_papers({"related_papers": question_papers}),
                "related_people": [person_slug] if person_slug else [],
            }
            question_key = entry["question"].strip().casefold()
            existing_entry: dict | None = None
            for item in topic_card["related_big_questions"]:
                if isinstance(item, dict) and str(item.get("question", "")).strip().casefold() == question_key:
                    existing_entry = item
                    break

            if existing_entry is None:
                topic_card["related_big_questions"].append(entry)
                continue

            existing_entry["related_papers"] = _merge_unique(
                _as_list(existing_entry.get("related_papers")) + _as_list(entry.get("related_papers"))
            )
            existing_entry["related_people"] = _merge_unique(
                _as_list(existing_entry.get("related_people")) + _as_list(entry.get("related_people"))
            )
            existing_why = str(existing_entry.get("why_important", "")).strip()
            if not existing_why or existing_why == "(missing)":
                existing_entry["why_important"] = entry["why_important"]

    return [topic_cards_by_slug[slug] for slug in sorted(topic_cards_by_slug)]


class OpenAISummaryAdapter:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self.client = client
        self.model = model

    @staticmethod
    def _extract_corresponding_authors_from_text(text: str) -> list[str]:
        email_pattern = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
        candidates: list[str] = []
        seen: set[str] = set()
        for line in text.splitlines():
            lowered = line.casefold()
            if "correspond" not in lowered and "e-mail" not in lowered and "email" not in lowered:
                continue
            for email in email_pattern.findall(line):
                normalized = email.strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    candidates.append(normalized)
        if candidates:
            return candidates

        # Fallback: when corresponding labels are absent, use first-page emails.
        for email in email_pattern.findall(text):
            normalized = email.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)
        return candidates

    @staticmethod
    def _parse_authors_response(raw: str) -> list[str]:
        value = raw.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            output: list[str] = []
            seen: set[str] = set()
            for item in parsed:
                normalized = str(item).strip().lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    output.append(normalized)
            if output:
                return output
        return OpenAISummaryAdapter._extract_corresponding_authors_from_text(value)

    @staticmethod
    def _as_string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        return []

    @staticmethod
    def _extract_json_object(raw: str) -> dict:
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _extract_year(text: str) -> int:
        years = [int(value) for value in re.findall(r"\b(19[5-9]\d|20\d{2})\b", text)]
        return max(years) if years else 0

    @staticmethod
    def _extract_journal(text: str) -> str:
        for line in text.splitlines():
            normalized = " ".join(line.strip().split())
            if not normalized:
                continue
            if re.search(r"(journal|nature|science|cell|proceedings|review|communications|letters)", normalized, flags=re.IGNORECASE):
                return normalized
        return ""

    @staticmethod
    def _extract_authors(text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        name_pattern = re.compile(r"[A-Z][a-zA-Z'`\-]+(?:\s+[A-Z](?:\.)?)?(?:\s+[A-Z][a-zA-Z'`\-]+)+")
        for line in lines[:20]:
            candidate = re.sub(r"\b\d+\b", " ", line)
            candidate = " ".join(candidate.split())
            if len(candidate) < 8 or len(candidate) > 240:
                continue
            if "@" in candidate or "http" in candidate.casefold():
                continue
            names = [name.strip() for name in name_pattern.findall(candidate)]
            deduped: list[str] = []
            seen: set[str] = set()
            for name in names:
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(name)
            if len(deduped) >= 2:
                return deduped
        return []

    @staticmethod
    def _coerce_year(value: object) -> int:
        if isinstance(value, int):
            return value if value > 0 else 0
        if isinstance(value, float):
            year = int(value)
            return year if year > 0 else 0
        if isinstance(value, str):
            return OpenAISummaryAdapter._extract_year(value)
        return 0

    @staticmethod
    def _merge_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output

    @staticmethod
    def _normalize_figure_label(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return "Figure ?"
        match = re.search(r"(?i)(?:figure|fig\.?)\s*([a-z]?\d+[a-z]?)", normalized)
        if match:
            return f"Figure {match.group(1).upper()}"
        if re.match(r"(?i)^(?:figure|fig\.?)\s+", normalized):
            suffix = re.sub(r"(?i)^(?:figure|fig\.?)\s+", "", normalized).strip()
            return f"Figure {suffix}" if suffix else "Figure ?"
        return f"Figure {normalized}"

    @staticmethod
    def _extract_figure_caption_results(text: str, *, max_items: int = 8) -> list[tuple[str, str]]:
        cleaned_text = text.strip()
        if not cleaned_text:
            return []

        def _clean_segment(value: str) -> str:
            cleaned = (
                value.replace("<!-- image -->", " ")
                .replace("##", " ")
                .replace("Resource", " ")
                .replace("Clinical and Translational Report", " ")
            )
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" :-|.")
            sentence_end = re.search(r"[.!?](?:\s|$)", cleaned)
            if sentence_end and sentence_end.end() >= 35:
                cleaned = cleaned[: sentence_end.end()].strip()
            if len(cleaned) > 240:
                cleaned = cleaned[:237].rstrip() + "..."
            return cleaned

        results: list[tuple[str, str]] = []
        seen_figures: set[str] = set()
        mention_pattern = re.compile(r"(?i)\b(?:figure|fig\.?)\s*([a-z]?\d+[a-z]?)\b")
        header_pattern = re.compile(r"(?i)^\s*(?:figure|fig\.?)\s*([a-z]?\d+[a-z]?)\s*[:.\-|\)]?\s*(.*)$")
        lines = [" ".join(line.strip().split()) for line in cleaned_text.splitlines()]

        index = 0
        while index < len(lines):
            line = lines[index]
            if not line:
                index += 1
                continue
            match = header_pattern.match(line)
            if not match:
                index += 1
                continue

            figure = f"Figure {match.group(1).upper()}"
            caption = match.group(2).strip(" :-|.")
            if not caption and index + 1 < len(lines):
                next_line = lines[index + 1]
                if next_line and not header_pattern.match(next_line):
                    caption = next_line.strip(" :-|.")
                    index += 1
            next_figure = mention_pattern.search(caption)
            if next_figure:
                caption = caption[: next_figure.start()].strip(" :-|.")
            caption = _clean_segment(caption)

            if caption:
                figure_key = figure.casefold()
                if figure_key not in seen_figures:
                    seen_figures.add(figure_key)
                    results.append((figure, caption))
                    if len(results) >= max_items:
                        return results
            index += 1

        flat_text = " ".join(cleaned_text.split())
        mentions = list(mention_pattern.finditer(flat_text))
        for idx, mention in enumerate(mentions):
            figure = f"Figure {mention.group(1).upper()}"
            figure_key = figure.casefold()
            if figure_key in seen_figures:
                continue

            start = mention.end()
            end = mentions[idx + 1].start() if idx + 1 < len(mentions) else len(flat_text)
            segment = flat_text[start:end].strip(" :-–—,.;")
            segment = _clean_segment(segment)
            if not segment:
                continue

            seen_figures.add(figure_key)
            results.append((figure, segment))
            if len(results) >= max_items:
                break
        return results

    def _infer_bibliographic_fields(self, *, title: str, first_page_text: str) -> dict:
        prompt = (
            "Extract bibliographic metadata from the first-page OCR/text. "
            "Return strict JSON with keys: authors (array of strings), journal (string), year (integer). "
            "Use empty array/string/0 when unknown.\n\n"
            f"Title: {title}\n\n"
            f"{first_page_text[:5000]}"
        )
        raw = self.client.summarize(prompt, model=self.model)
        parsed = self._extract_json_object(raw)
        return {
            "authors": self._as_string_list(parsed.get("authors")),
            "journal": str(parsed.get("journal", "")).strip(),
            "year": self._coerce_year(parsed.get("year")),
        }

    def _build_summary(self, *, title: str, paper_type: str, paper_text: str) -> tuple[str, str]:
        prompt = (
            "Create a concise structured summary of the paper using ONLY the provided text. "
            "Return strict JSON. "
            "For article papers, include keys: key_question_solved, why_important, method, "
            "findings_logical_flow, key_results_with_figures (array of objects with keys 'figure' and 'result'), limitations. "
            "For review papers, include keys: key_goal, unsolved_questions, why_important, why_unsolved. "
            "For article papers, key findings and flow must describe the logical flow of sections and experiments, "
            "plus bullet points for key results with figure references (for example Figure 1, Figure 2). "
            f"Also include paper_type as either 'article' or 'review'.\n\nTitle: {title}\n\n"
            f"{paper_text[:10000]}"
        )
        raw = self.client.summarize(prompt, model=self.model)
        parsed = self._extract_json_object(raw)
        effective_type = str(parsed.get("paper_type", paper_type)).strip().lower()
        if effective_type not in {"article", "review"}:
            effective_type = paper_type

        if effective_type == "review":
            mapping = [
                ("Key goal of the review", "key_goal"),
                ("Key unsolved questions", "unsolved_questions"),
                ("Why these unsolved questions are important", "why_important"),
                ("Why these unsolved questions are still unsolved", "why_unsolved"),
            ]
        else:
            raw_logical_flow = parsed.get("findings_logical_flow", parsed.get("findings", ""))
            logical_flow_lines: list[str] = []
            if isinstance(raw_logical_flow, list):
                logical_flow_lines = [str(item).strip() for item in raw_logical_flow if str(item).strip()]
            elif isinstance(raw_logical_flow, str):
                logical_flow = raw_logical_flow.strip()
                if logical_flow.startswith("[") and logical_flow.endswith("]"):
                    try:
                        parsed_flow = json.loads(logical_flow)
                    except json.JSONDecodeError:
                        parsed_flow = None
                    if isinstance(parsed_flow, list):
                        logical_flow_lines = [str(item).strip() for item in parsed_flow if str(item).strip()]
                if not logical_flow_lines and logical_flow:
                    logical_flow_lines = [logical_flow]
            elif raw_logical_flow is not None:
                normalized = str(raw_logical_flow).strip()
                if normalized:
                    logical_flow_lines = [normalized]

            if len(logical_flow_lines) > 1:
                logical_flow_block = "\n".join(f"{index}. {line}" for index, line in enumerate(logical_flow_lines, start=1))
            elif logical_flow_lines:
                logical_flow_block = logical_flow_lines[0]
            else:
                logical_flow_block = "(missing)"
            key_results = parsed.get("key_results_with_figures", parsed.get("key_results", []))
            key_results_by_figure: dict[str, str] = {}
            if isinstance(key_results, list):
                for item in key_results:
                    if isinstance(item, dict):
                        figure = self._normalize_figure_label(str(item.get("figure", "")))
                        result = str(item.get("result", "")).strip()
                        if result and figure not in key_results_by_figure:
                            key_results_by_figure[figure] = result
                    else:
                        text = str(item).strip()
                        if text:
                            figure_match = re.search(r"(?i)\b(?:figure|fig\.?)\s*(\d+[a-z]?)\b", text)
                            figure = self._normalize_figure_label(figure_match.group(0)) if figure_match else "Figure ?"
                            result = re.sub(r"(?i)^\s*(?:figure|fig\.?)\s*\d+[a-z]?\s*[:.\-]?\s*", "", text).strip()
                            if result and figure not in key_results_by_figure:
                                key_results_by_figure[figure] = result

            for figure, result in self._extract_figure_caption_results(paper_text):
                if figure not in key_results_by_figure:
                    key_results_by_figure[figure] = result

            key_result_lines = [f"- {figure}: {result}" for figure, result in key_results_by_figure.items()]

            findings_value = (
                "Logical flow of sections and experiments:\n"
                f"{logical_flow_block}\n\n"
                "Key results with figure references:\n"
                + ("\n".join(key_result_lines) if key_result_lines else "- Figure ?: (missing)")
            )
            mapping = [
                ("Key question solved", "key_question_solved"),
                ("Why this question is important", "why_important"),
                ("How the paper solves this question", "method"),
                ("Key findings and flow", "__formatted_findings__"),
                ("Limitations of the paper", "limitations"),
            ]

        lines: list[str] = []
        for output_key, json_key in mapping:
            if json_key == "__formatted_findings__":
                value = findings_value
            else:
                value = str(parsed.get(json_key, "")).strip()
                if not value:
                    value = "(missing)"
            lines.append(f"{output_key}: {value}")
        return "\n".join(lines), effective_type

    @staticmethod
    def _validate_person_big_questions(payload: dict, allowed_papers: set[str]) -> list[dict]:
        big_questions = payload.get("big_questions")
        if not isinstance(big_questions, list) or not big_questions:
            raise ValueError("missing non-empty big_questions")

        validated: list[dict] = []
        for entry in big_questions:
            if not isinstance(entry, dict):
                raise ValueError("big_questions entry must be an object")
            question = str(entry.get("question", "")).strip()
            why_important = str(entry.get("why_important", "")).strip()
            related_papers_raw = entry.get("related_papers")
            if not question or not why_important or not isinstance(related_papers_raw, list) or not related_papers_raw:
                raise ValueError("big_questions entry missing required fields")
            related_papers = OpenAISummaryAdapter._merge_unique(
                [str(value).strip() for value in related_papers_raw if str(value).strip()]
            )
            if not related_papers:
                raise ValueError("big_questions entry has empty related_papers")
            if any(slug not in allowed_papers for slug in related_papers):
                raise ValueError("related_papers must be a subset of linked papers")
            validated.append(
                {
                    "question": question,
                    "why_important": why_important,
                    "related_papers": related_papers,
                }
            )
        return validated

    def _generate_person_big_questions(self, person_seed: dict, paper_cards_by_slug: dict[str, dict]) -> list[dict]:
        linked_papers = [str(slug).strip() for slug in person_seed.get("related_papers", []) if str(slug).strip()]
        linked_papers_set = set(linked_papers)
        evidence_lines: list[str] = []
        for paper_slug in linked_papers:
            paper_card = paper_cards_by_slug.get(paper_slug, {})
            title = str(paper_card.get("title", "")).strip() or "(missing)"
            summary = str(paper_card.get("summary", "")).strip() or "(missing)"
            evidence_lines.append(f"- slug: {paper_slug}\n  title: {title}\n  summary: {summary}")
        prompt = (
            "Generate person card JSON for the researcher below.\n"
            "Return strict JSON object with keys: focus_area (array), big_questions (array of objects).\n"
            "Each big_questions entry must include non-empty question, why_important, and related_papers.\n"
            "Set focus_area to [] exactly.\n"
            f"Each related_papers list must only use linked paper slugs: {json.dumps(linked_papers)}.\n\n"
            f"Person seed:\n{json.dumps(person_seed, ensure_ascii=False)}\n\n"
            "Linked paper evidence:\n"
            + ("\n".join(evidence_lines) if evidence_lines else "- (none)")
        )

        last_error: Exception | None = None
        for _ in range(2):
            raw = self.client.summarize(prompt, model=self.model)
            payload = self._extract_json_object(raw)
            try:
                return self._validate_person_big_questions(payload, linked_papers_set)
            except ValueError as exc:
                last_error = exc
        detail = f": {last_error}" if last_error else ""
        raise ValueError(f"person generation failed after 2 attempts{detail}")

    def _infer_corresponding_authors(self, paper_text: str, title: str) -> list[str]:
        first_page_text = paper_text[:4000]
        extracted = self._extract_corresponding_authors_from_text(first_page_text)
        if extracted:
            return extracted
        prompt = (
            "Extract corresponding author email addresses from the first-page OCR/text below. "
            "Return JSON array only.\n\n"
            f"Title: {title}\n\n"
            f"{first_page_text}"
        )
        raw = self.client.summarize(prompt, model=self.model)
        return self._parse_authors_response(raw)

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        title = metadata.get("title", "Untitled")
        paper_type = str(metadata.get("paper_type", "article")).strip().lower()
        if paper_type not in {"article", "review"}:
            paper_type = "review" if "review" in title.casefold() else "article"
        first_page_text = str(metadata.get("first_page_text", "")).strip() or paper_text[:4000]

        authors = self._as_string_list(metadata.get("authors"))
        journal = str(metadata.get("journal", "")).strip()
        year = self._coerce_year(metadata.get("year"))

        if not authors:
            authors = self._extract_authors(first_page_text)
        if not journal:
            journal = self._extract_journal(first_page_text)
        if not year:
            year = self._extract_year(first_page_text)

        if not authors or not journal or not year:
            inferred = self._infer_bibliographic_fields(title=title, first_page_text=first_page_text)
            if not authors:
                authors = inferred["authors"]
            if not journal:
                journal = inferred["journal"]
            if not year:
                year = inferred["year"]

        summary, paper_type = self._build_summary(title=title, paper_type=paper_type, paper_text=paper_text)
        corresponding_authors = list(metadata.get("corresponding_authors", []))
        if not corresponding_authors:
            corresponding_authors = self._infer_corresponding_authors(paper_text, title)
        corresponding_authors = self._merge_unique([normalize_email(author) or str(author).strip() for author in corresponding_authors])

        return {
            "slug": metadata["slug"],
            "type": "article",
            "paper_type": paper_type,
            "title": title,
            "authors": authors,
            "journal": journal or "Unknown",
            "year": year,
            "summary": summary,
            "corresponding_authors": corresponding_authors,
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        person_seeds = _extract_person_seeds(paper_cards)
        if not person_seeds:
            return []
        paper_cards_by_slug = {str(card.get("slug", "")).strip(): card for card in paper_cards}
        person_cards: list[dict] = []
        for seed in person_seeds:
            card = dict(seed)
            card["focus_area"] = []
            card["big_questions"] = self._generate_person_big_questions(seed, paper_cards_by_slug)
            person_cards.append(card)
        return person_cards

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        return _derive_topic_cards(person_cards)


class DeterministicLLMAdapter:
    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        title = metadata.get("title", "Untitled")
        prompt_excerpt = paper_text[:200].strip()
        summary = (
            f"Key question solved: {title}\n"
            f"Why this question is important: Supports corpus-level discovery.\n"
            f"How the paper solves this question: Deterministic scaffold summary.\n"
            f"Key findings and flow: {prompt_excerpt or 'No text content available.'}\n"
            f"Limitations of the paper: Needs full LLM integration for richer synthesis."
        )
        return {
            "slug": metadata["slug"],
            "type": "article",
            "paper_type": "article",
            "title": title,
            "authors": OpenAISummaryAdapter._as_string_list(metadata.get("authors")),
            "journal": str(metadata.get("journal", "")).strip() or "Unknown",
            "year": OpenAISummaryAdapter._coerce_year(metadata.get("year")),
            "summary": summary,
            "corresponding_authors": metadata.get("corresponding_authors", []),
        }

    def derive_person_cards(self, paper_cards: list[dict]) -> list[dict]:
        return _derive_person_cards(paper_cards)

    def derive_topic_cards(self, person_cards: list[dict]) -> list[dict]:
        return _derive_topic_cards(person_cards)
