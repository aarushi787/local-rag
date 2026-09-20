# MCCIA archive: training preparation status

Prepared on 7 September 2026. **No model weights were trained or changed.**

## What was prepared

The Google Drive connector confirmed the supplied folder and its dashboard snapshot.
The review pack uses the **existing local 27 August 2026 snapshot**, not a fresh full
download. Its files have recorded SHA-256 hashes, but have not been byte-compared
against the live Drive files. It covers `records.json` and `clippings.json` only;
it does not extract the ZIP archives, native spreadsheet, or full newspaper pages.

Private outputs (ignored by Git):

- `training-data/mccia-drive-review-20260907/source_review.jsonl`
- `training-data/mccia-drive-review-20260907/manifest.json`

| Check | Result |
| --- | ---: |
| Media records | 2,934 |
| Clipping records | 1,488 |
| Total review candidates, not training examples | 4,422 |
| Unverified / partially verified media records | 1,144 / 436 |
| Low-quality clipping images | 376 |
| Clippings without an OCR excerpt in this JSON snapshot | 1,149 |
| Missing or invalid dates across both inputs | 319 |
| Dates later than 7 September 2026 | 2 |
| Approved training examples | 0 |

Counts of warnings overlap. A missing OCR excerpt here does not prove that no text
exists elsewhere in the archive or RAG database. Source verification labels are
inherited metadata, not an independent verification or training approval.

Each candidate contains selected source evidence, source file hash, Drive URL,
JSON-array position, review warnings, and blank question/answer/evidence fields.
Every candidate is pending review and has `training_approved: false`.
No source content is treated as an instruction to the assistant or executed.

## Next steps before training

1. Confirm which material you are permitted to use for training and who may use the
   resulting model. Access to a Drive folder is not itself a training license.
2. Review privacy and sharing. At inspection the root folder was readable by anyone
   with the link. No sharing permissions were changed. Local review outputs retain
   source text and may contain personal data; they are **not redacted**. Do not publish
   them, put them in Git, or upload them to a training provider without approval.
3. Start with a small representative batch of verified articles. Correct OCR against
   the original images, resolve dates, and remove duplicates and unsuitable material.
4. Write questions and short answers supported by explicit evidence spans. Keep source
   IDs and provenance. Include English/Marathi examples only after language-competent
   review. Do not use a broken OCR headline or search snippet as a verified answer.
5. Group all versions of the same article/event, including translations and linked
   clipping records. Hold out entire groups for validation/test before creating more
   examples. The suggested group field is only a starting point, not leak-proof dedup.
6. Obtain human approval of every example and its permitted use. Editing review fields
   does **not** trigger export or training. This pack is not in the training runner's
   reviewed-data directory and is not an SFT `messages` dataset.
7. Pass the project's retrieval/evaluation gates before attempting fine-tuning. Keep
   document facts and access controls in RAG; use a separately evaluated fine-tune
   only for a defined behavior such as evidence-based answer structure. Do not train
   a shared model on documents that only some of its users are allowed to access.
8. Select an isolated training machine and resource budget. During preparation this
   laptop had 7.33 GiB total RAM and only 0.58 GiB available. Training was not started.
   Do not run it alongside production Tally, lower its safety guard, or install the
   optional training dependencies into the running app's environment.

Model training, evaluation, approval, and deployment remain separate stages. No
latency or accuracy improvement has been measured from this preparation.

## Reproduce preparation only

From the project directory in PowerShell, choose a **new** output folder each time:

```powershell
.\.venv-rag\Scripts\python.exe -m unittest training.test_prepare_drive_review
.\.venv-rag\Scripts\python.exe training\prepare_drive_review.py --output training-data\mccia-drive-review-next
```

The command refuses an existing output directory or a CLI output path outside
`training-data`. A completed pack has `manifest.json`; a failed, partial run does
not. Do not consume partial outputs. Exact duplicate selected-evidence rows are
skipped within each source file; semantic duplicates still require review.

This tool uses the standard Python library, reads bounded JSON files, and makes no
network, model, or database calls. It does not alter the existing RAG index, app
configuration, model files, or source cache. Four focused offline tests passed.
