# Article-Only Person/Topic Generation Design

## Problem statement

Person cards and topic cards should be generated using only content from paper cards where `paper_type == "article"`. Review-paper content should not contribute to person big questions or topic grouping.

## Scope

In scope:
1. Filter person-card generation input to article paper cards only.
2. Keep topic-card generation based on the resulting article-derived person set.
3. Add regression tests for mixed and review-only inputs.

Out of scope:
1. Changes to paper-card generation and storage (all papers still get paper cards).
2. Prompt rewrites or adapter redesign.
3. Schema changes.

## Approved design

### 1. Architecture/components

1. Keep `SummarizeService.run` as the integration boundary for this rule.
2. After collecting `paper_cards`, derive:
   - `article_paper_cards = [card for card in paper_cards if card.get("paper_type") == "article"]`
3. Call `derive_person_cards(article_paper_cards)` only.
4. Call `derive_topic_cards(person_cards)` from that article-derived person set.
5. Strict behavior: missing/invalid `paper_type` is treated as non-article.

### 2. Data flow

1. Summarize all papers into paper cards (unchanged).
2. Filter to article paper cards before person derivation.
3. Build person cards from article-only evidence.
4. Build topic cards from article-derived person cards only.

### 3. Testing

1. Mixed input test: article + review paper cards → person/topic calls receive article-only set.
2. Review-only test: person/topic outputs are empty while paper cards still exist.
3. Preserve existing summary stats and persistence behavior for paper cards.

## Acceptance criteria

1. Review-paper cards no longer influence person big questions.
2. Topic cards are based only on person cards derived from article papers.
3. Existing paper-card generation remains unchanged.
