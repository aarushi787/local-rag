# Optional Gemma customization

For the supplied MCCIA Drive archive, see [MCCIA_DATA_REVIEW.md](MCCIA_DATA_REVIEW.md).
Its source-review pack is not yet an approved fine-tuning dataset.

## Level A: prompt profile

This is the recommended customization for the current CPU-only laptop. It does
not train or modify model weights.

```powershell
ollama create local-rag-gemma -f .\models\Modelfile.gemma-rag
ollama run local-rag-gemma
```

After testing, set `CHAT_MODEL=local-rag-gemma` in `.env` and restart FastAPI.
The profile uses a 2048-token context, low temperature, repetition controls,
grounded-answer rules, and explicit refusal when evidence is insufficient.

## Level B: optional CPU LoRA preparation

Never train the quantized Ollama Q4/QAT model. Use the original
`google/gemma-3-1b-it` Hugging Face checkpoint and the settings in
`training/lora_cpu_config.json`. On this CPU-only machine, even a small LoRA run
may take many hours or days.

1. In the administrator interface, approve only conversations that a person has
   reviewed and is allowed to use for training.
2. Optionally create a private text file containing names or other terms that
   must be removed, one per line. Keep that file outside Git.
3. Export to the review area:

   ```powershell
   python .\export_lora_dataset.py --redact-terms "C:\private\redact-terms.txt"
   ```

4. Manually inspect every record. The exporter removes common credentials,
   database URLs, email addresses, phone numbers, IP addresses, and the supplied
   private terms, but automated redaction cannot guarantee that all personal
   information was detected.
5. Only after review, copy approved files from `training-data\review` to
   `training-data\reviewed`. The training process is deliberately not connected
   to the production server and never starts automatically.

Use rank 8 (or 4 for lower memory), batch size 1, sequence length 384, gradient
accumulation 16, and one initial epoch. Keep a held-out test split and compare
it with the unmodified model before deployment.

After training, merge the adapter with the exact original base checkpoint in
the training framework. Convert the merged Hugging Face directory with
`llama.cpp\convert_hf_to_gguf.py`, then quantize that high-precision GGUF with
`llama-quantize` to `Q4_K_M`. Finally create an Ollama model whose Modelfile uses
`FROM` with the resulting GGUF path. Never apply an adapter to a different base
model; incompatible bases can produce invalid behavior.

Primary references:

- [Google Gemma fine-tuning](https://ai.google.dev/gemma/docs/tune)
- [Ollama model import](https://docs.ollama.com/import)
- [Ollama Modelfile reference](https://docs.ollama.com/modelfile)
- [llama.cpp quantization](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md)
