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


class OpenAISummaryAdapter:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self.client = client
        self.model = model

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
    def _coerce_year(value: object) -> int:
        if isinstance(value, int):
            return value if value > 0 else 0
        if isinstance(value, float):
            year = int(value)
            return year if year > 0 else 0
        if isinstance(value, str):
            years = [int(match) for match in re.findall(r"\b(19[5-9]\d|20\d{2})\b", value)]
            return max(years) if years else 0
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
    def _normalize_corresponding_author(value: object) -> str:
        raw = str(value).strip()
        if not raw:
            return ""
        match = re.match(r"^\s*(.*?)\s*<\s*([^>]+)\s*>\s*$", raw)
        if match:
            name = match.group(1).strip()
            email = normalize_email(match.group(2))
            if email:
                return f"{name} <{email}>" if name else email
        email = normalize_email(raw)
        if email:
            return email
        return raw

    @staticmethod
    def _normalize_title(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())

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

    def _infer_bibliographic_fields(self, *, title: str, first_two_pages_text: str) -> dict:
        prompt = (
            "Extract bibliographic metadata from the first-two-pages OCR/text\n"
            "Role: You are a precise scientific metadata extraction assistant.\n"
            "Objective: Extract bibliographic metadata from first-two-pages OCR/text.\n"
            "Evidence boundary: Use only the provided first-two-pages text.\n"
            "Rubric/checklist:\n"
            "- Title must match the paper title present in the provided text.\n"
            "- Authors must be actual author names found in the provided page text.\n"
            "- Journal must be the publication venue stated in the text.\n"
            "- Year must be the publication year as an integer.\n"
            "- Corresponding authors must be explicitly present in the provided text.\n"
            "- When both a corresponding author name and email are present, format as Name <email>; if only email is available, return the plain email string.\n"
            "Output contract: Return strict JSON object only with keys title (string), authors (array of strings), "
            "journal (string), year (integer), corresponding_authors (array of strings).\n"
            "Defaults/failure policy: If unknown, use title=\"\", authors=[], journal=\"\", year=0, corresponding_authors=[].\n\n"
            f"Seed title: {title}\n\n"
            f"{first_two_pages_text[:5000]}"
        )
        raw = self.client.summarize(prompt, model=self.model)
        parsed = self._extract_json_object(raw)
        return {
            "title": self._normalize_title(parsed.get("title", "")),
            "authors": self._as_string_list(parsed.get("authors")),
            "journal": str(parsed.get("journal", "")).strip(),
            "year": self._coerce_year(parsed.get("year")),
            "corresponding_authors": self._as_string_list(parsed.get("corresponding_authors")),
        }

    def _build_summary(self, *, title: str, paper_type: str, paper_text: str) -> tuple[str, str]:
        prompt = (
            "Create a concise structured summary of the paper using ONLY the provided text.\n"
            "Role: You are a senior reviewer for a top-tier scientific journal who evaluates scientific work for "
            "innovation, impact, and logical rigor.\n"
            "Objective: Produce a faithful, evidence-grounded summary with clear scientific reasoning.\n"
            "Evidence boundary: Use only the supplied paper text. No external facts, assumptions, or citations.\n"
            "Rubric/checklist:\n"
            "- Accurately identify the core scientific question or review goal.\n"
            "- Explain practical/scientific importance with evidence-grounded language.\n"
            "- Capture method-to-result coherence and logical flow of sections and experiments.\n"
            "- Include bullet points for key results with figure references (for example Figure 1, Figure 2).\n"
            "- Reflect realistic limitations without speculation.\n"
            "Output contract: Return strict JSON only.\n"
            "- For article papers, include keys: key_question_solved, why_important, method, findings_logical_flow, "
            "key_results_with_figures (array of objects with keys 'figure' and 'result'), limitations, and paper_type.\n"
            "- For review papers, include keys: key_goal, unsolved_questions, why_important, why_unsolved, and paper_type.\n"
            "- paper_type must be either 'article' or 'review'.\n"
            "Defaults/failure policy: If a field cannot be supported by the provided text, return empty strings/arrays "
            "for that field while preserving required keys.\n\n"
            f"Title: {title}\n\n"
            f"{paper_text}"
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
        if "focus_area" not in payload or payload.get("focus_area") != []:
            raise ValueError("focus_area must be present and equal to []")

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

    @staticmethod
    def _extract_json_array_strict(raw: str) -> list[object]:
        text = raw.strip()
        if not text:
            raise ValueError("empty topic payload")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("topic payload must be strict JSON array") from exc
        if not isinstance(parsed, list):
            raise ValueError("topic payload must be strict JSON array")
        return parsed

    @staticmethod
    def _topic_reference_index(person_cards: list[dict]) -> tuple[set[str], set[str], dict[str, dict]]:
        known_people: set[str] = set()
        known_papers: set[str] = set()
        questions: dict[str, dict] = {}

        for person_card in person_cards:
            person_slug = str(person_card.get("slug", "")).strip()
            if person_slug:
                known_people.add(person_slug)

            person_papers = OpenAISummaryAdapter._merge_unique(
                [str(value).strip() for value in OpenAISummaryAdapter._as_string_list(person_card.get("related_papers"))]
            )
            known_papers.update(person_papers)

            raw_questions = person_card.get("big_questions")
            if not isinstance(raw_questions, list):
                continue
            for entry in raw_questions:
                if not isinstance(entry, dict):
                    continue
                question = str(entry.get("question", "")).strip()
                if not question:
                    continue
                question_key = question.casefold()
                question_why = str(entry.get("why_important", "")).strip()
                question_papers = OpenAISummaryAdapter._merge_unique(
                    [
                        str(value).strip()
                        for value in OpenAISummaryAdapter._as_string_list(entry.get("related_papers")) or person_papers
                    ]
                )
                known_papers.update(question_papers)
                question_ref = questions.setdefault(
                    question_key,
                    {
                        "question": question,
                        "why_important": question_why,
                        "people": set(),
                        "papers": set(),
                        "pairs": set(),
                    },
                )
                if person_slug:
                    question_ref["people"].add(person_slug)
                question_ref["papers"].update(question_papers)
                if person_slug:
                    question_ref["pairs"].update((person_slug, paper_slug) for paper_slug in question_papers)
                if question_why and not question_ref["why_important"]:
                    question_ref["why_important"] = question_why

        return known_people, known_papers, questions

    @staticmethod
    def _validate_topic_cards_payload(payload: list[object], person_cards: list[dict]) -> list[dict]:
        known_people, known_papers, known_questions = OpenAISummaryAdapter._topic_reference_index(person_cards)
        if not payload:
            raise ValueError("empty topic payload")
        validated: list[dict] = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("topic entry must be an object")
            required = {
                "slug",
                "type",
                "topic",
                "related_big_questions",
                "related_people",
                "related_papers",
            }
            if any(key not in entry for key in required):
                raise ValueError("topic entry missing required fields")

            slug = str(entry.get("slug", "")).strip()
            topic_type = str(entry.get("type", "")).strip()
            topic = str(entry.get("topic", "")).strip()
            if not slug or not topic_type or not topic:
                raise ValueError("topic entry missing required string fields")
            if topic_type != "topic":
                raise ValueError("topic entry type must be topic")

            related_people_raw = entry.get("related_people")
            related_papers_raw = entry.get("related_papers")
            related_big_questions_raw = entry.get("related_big_questions")
            if not isinstance(related_people_raw, list) or not isinstance(related_papers_raw, list):
                raise ValueError("topic entry related_people/related_papers must be arrays")
            if not isinstance(related_big_questions_raw, list) or not related_big_questions_raw:
                raise ValueError("topic entry missing non-empty related_big_questions")

            related_people = OpenAISummaryAdapter._merge_unique(
                [str(value).strip() for value in related_people_raw if str(value).strip()]
            )
            related_papers = OpenAISummaryAdapter._merge_unique(
                [str(value).strip() for value in related_papers_raw if str(value).strip()]
            )
            if not related_people or not related_papers:
                raise ValueError("topic entry must have non-empty related_people and related_papers")
            if any(person_slug not in known_people for person_slug in related_people):
                raise ValueError("topic related_people must reference known person slugs")
            if any(paper_slug not in known_papers for paper_slug in related_papers):
                raise ValueError("topic related_papers must reference known paper slugs")

            validated_questions: list[dict] = []
            for question_entry in related_big_questions_raw:
                if not isinstance(question_entry, dict):
                    raise ValueError("related_big_questions entry must be an object")
                question = str(question_entry.get("question", "")).strip()
                why_important = str(question_entry.get("why_important", "")).strip()
                raw_question_people = question_entry.get("related_people")
                raw_question_papers = question_entry.get("related_papers")
                if (
                    not question
                    or not why_important
                    or not isinstance(raw_question_people, list)
                    or not isinstance(raw_question_papers, list)
                ):
                    raise ValueError("related_big_questions entry missing required fields")
                question_people = OpenAISummaryAdapter._merge_unique(
                    [str(value).strip() for value in raw_question_people if str(value).strip()]
                )
                question_papers = OpenAISummaryAdapter._merge_unique(
                    [str(value).strip() for value in raw_question_papers if str(value).strip()]
                )
                if not question_people or not question_papers:
                    raise ValueError("related_big_questions entry must have related_people and related_papers")
                if any(person_slug not in known_people for person_slug in question_people):
                    raise ValueError("related_big_questions people must reference known person slugs")
                if any(paper_slug not in known_papers for paper_slug in question_papers):
                    raise ValueError("related_big_questions papers must reference known paper slugs")
                if any(person_slug not in related_people for person_slug in question_people):
                    raise ValueError("related_big_questions people must exist in topic related_people")
                if any(paper_slug not in related_papers for paper_slug in question_papers):
                    raise ValueError("related_big_questions papers must exist in topic related_papers")

                question_ref = known_questions.get(question.casefold())
                if question_ref is None:
                    raise ValueError("related_big_questions question must reference known input big questions")
                if any(person_slug not in question_ref["people"] for person_slug in question_people):
                    raise ValueError("related_big_questions people do not match source big-question links")
                if any(paper_slug not in question_ref["papers"] for paper_slug in question_papers):
                    raise ValueError("related_big_questions papers do not match source big-question links")
                source_pairs = question_ref["pairs"]
                people_without_link = [
                    person_slug
                    for person_slug in question_people
                    if not any((person_slug, paper_slug) in source_pairs for paper_slug in question_papers)
                ]
                papers_without_link = [
                    paper_slug
                    for paper_slug in question_papers
                    if not any((person_slug, paper_slug) in source_pairs for person_slug in question_people)
                ]
                if people_without_link or papers_without_link:
                    raise ValueError(
                        "related_big_questions person/paper associations must match source big-question links"
                    )

                validated_questions.append(
                    {
                        "question": question_ref["question"],
                        "why_important": why_important,
                        "related_people": question_people,
                        "related_papers": question_papers,
                    }
                )

            validated.append(
                {
                    "slug": slug,
                    "type": topic_type,
                    "topic": topic,
                    "related_big_questions": validated_questions,
                    "related_people": related_people,
                    "related_papers": related_papers,
                }
            )
        return validated

    @staticmethod
    def _build_topic_prompt(person_cards: list[dict]) -> str:
        prompt_people: list[dict] = []
        for person_card in person_cards:
            slug = str(person_card.get("slug", "")).strip()
            related_papers = OpenAISummaryAdapter._merge_unique(
                [str(value).strip() for value in OpenAISummaryAdapter._as_string_list(person_card.get("related_papers"))]
            )
            big_questions: list[dict] = []
            raw_questions = person_card.get("big_questions")
            if isinstance(raw_questions, list):
                for item in raw_questions:
                    if not isinstance(item, dict):
                        continue
                    question = str(item.get("question", "")).strip()
                    why_important = str(item.get("why_important", "")).strip()
                    question_papers = OpenAISummaryAdapter._merge_unique(
                        [
                            str(value).strip()
                            for value in OpenAISummaryAdapter._as_string_list(item.get("related_papers")) or related_papers
                        ]
                    )
                    if question:
                        big_questions.append(
                            {
                                "question": question,
                                "why_important": why_important,
                                "related_papers": question_papers,
                            }
                        )
            prompt_people.append(
                {
                    "slug": slug,
                    "related_papers": related_papers,
                    "big_questions": big_questions,
                }
            )

        return (
            "Generate topic card JSON from all provided person cards and big questions.\n"
            "Role: You are a senior professor synthesizing coherent research themes from multiple researchers.\n"
            "Objective: Group related big questions into high-coherence topic cards with traceable provenance.\n"
            "Evidence boundary: Use only the provided person cards and their big questions.\n"
            "Rubric/checklist:\n"
            "- Themes must emerge directly from input big questions.\n"
            "- Grouping should maximize conceptual coherence.\n"
            "- Preserve traceable related_people and related_papers links for each grouped question.\n"
            "- Do not fabricate people, papers, topics, or question content.\n"
            "Output contract: Return strict JSON array only (no markdown/no prose).\n"
            "- Each topic card must include: slug, type, topic, related_big_questions, related_people, related_papers.\n"
            "- Set type to \"topic\".\n"
            "- Each related_big_questions entry must include: question, why_important, related_people, related_papers.\n"
            "- Use only person slugs and paper slugs from the input.\n"
            "- related_big_questions must be non-empty and reference the input big questions.\n"
            "Defaults/failure policy: If grouping is uncertain, return fewer high-confidence topics instead of inventing data.\n\n"
            f"Input person cards:\n{json.dumps(prompt_people, ensure_ascii=False)}"
        )

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
            "Role: You are a senior professor synthesizing long-horizon research agendas for an individual researcher.\n"
            "Objective: Infer high-value scientific big questions grounded in the linked paper evidence.\n"
            "Evidence boundary: Use only the provided person seed and linked paper evidence.\n"
            "Rubric/checklist:\n"
            "- Questions must be specific, scientific, and meaningful over a long-horizon timeline.\n"
            "- why_important must be strategic, concrete, and evidence-grounded.\n"
            "- related_papers must reference only linked paper slugs provided below.\n"
            "- no fabricated papers, entities, or unsupported claims.\n"
            "Output contract: Return strict JSON object only with keys focus_area (array) and big_questions (array of objects).\n"
            "- Set focus_area to [] exactly.\n"
            "- Each big_questions entry must include non-empty question, why_important, and related_papers.\n"
            f"- Each related_papers list must only use linked paper slugs: {json.dumps(linked_papers)}.\n"
            "Defaults/failure policy: If uncertain, return fewer high-confidence questions; never invent evidence.\n\n"
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
        person_slug = str(person_seed.get("slug", "")).strip() or "(unknown person)"
        detail = f": {last_error}" if last_error else ""
        raise ValueError(f"person generation failed after 2 attempts for {person_slug}{detail}")

    def summarize_paper(self, paper_text: str, metadata: dict) -> dict:
        seed_title = self._normalize_title(metadata.get("title", ""))
        paper_type = str(metadata.get("paper_type", "article")).strip().lower()
        if paper_type not in {"article", "review"}:
            paper_type = "review" if "review" in seed_title.casefold() else "article"

        inferred = self._infer_bibliographic_fields(title=seed_title, first_two_pages_text=paper_text[:5000])
        title = self._normalize_title(inferred.get("title")) or seed_title or "Untitled"
        authors = self._as_string_list(inferred.get("authors")) or []
        journal = str(inferred.get("journal", "")).strip() or "Unknown"
        year = self._coerce_year(inferred.get("year"))
        corresponding_authors = self._merge_unique(
            [
                self._normalize_corresponding_author(author)
                for author in self._as_string_list(inferred.get("corresponding_authors"))
            ]
        )

        summary, paper_type = self._build_summary(title=title, paper_type=paper_type, paper_text=paper_text)

        return {
            "slug": metadata["slug"],
            "type": "article",
            "paper_type": paper_type,
            "title": title,
            "authors": authors,
            "journal": journal,
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
        if not person_cards:
            return []

        prompt = self._build_topic_prompt(person_cards)
        last_error: Exception | None = None
        for _ in range(2):
            raw = self.client.summarize(prompt, model=self.model)
            try:
                payload = self._extract_json_array_strict(raw)
                return self._validate_topic_cards_payload(payload, person_cards)
            except ValueError as exc:
                last_error = exc
        detail = f": {last_error}" if last_error else ""
        raise ValueError(f"topic generation failed after 2 attempts{detail}")
