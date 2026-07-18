# Complete 768-token smoke comparison

Open `blinded_human_review_packet.html` for the easiest review. It contains all
eight smoke questions and four anonymous answers per question: local Qwen with
gold evidence, local Qwen with retrieved evidence, GPT-4o with gold evidence,
and GPT-4o with retrieved evidence.

Keep blind mode enabled for the first pass. Judge scientific correctness,
coverage of required points, grounding in the displayed evidence, citation
accuracy, and student-friendly clarity. Open `blinded_answer_key.json` only
after recording decisions.

The online result is a merge of the ten complete answers from the original
384-token run and six selective 768-token retries. Later retry rows override
only the matching truncated rows; no successful original answer was regenerated.

The automatic unsupported-claim screen flags two concepts in both online
modes. Manual inspection shows these are lexical false positives: the meiosis
answer correctly assigns genetic identity to mitosis, and the Ohm's-law answer
correctly places the voltmeter in parallel. Treat the HTML review—not that
token-overlap flag—as authoritative.
