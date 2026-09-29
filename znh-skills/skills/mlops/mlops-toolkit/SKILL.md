---
name: mlops-toolkit
description: "ML operations toolkit — model hub access, experiment tracking, benchmarking, and computer vision models."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mlops, huggingface, wandb, evaluation, benchmarking, segmentation, sam]
---

# MLOps Toolkit

## Overview

This umbrella covers the essential ML operations tools: downloading and sharing
models/datasets (HuggingFace Hub), tracking experiments (Weights & Biases),
benchmarking LLMs (lm-evaluation-harness), and zero-shot image segmentation
(Segment Anything Model).

## 1. HuggingFace Hub

Search, download, and upload models and datasets via the `hf` CLI.

```bash
# Search models
huggingface-cli search bert

# Download a model
huggingface-cli download meta-llama/Llama-2-7b-hf

# Login (needed for gated models or uploads)
huggingface-cli login
```

**Gated models:** Some models require accepting a license on the HuggingFace website
before the CLI can download them. If download fails with a 403, check the model
page for a "Request Access" or "Accept License" button.

## 2. Weights & Biases (W&B)

Experiment tracking, hyperparameter sweeps, and model registry.

**Quick start:**
```python
import wandb

wandb.init(project="my-project", config={"lr": 0.001})
# ... training ...
wandb.log({"loss": loss.item()})
wandb.finish()
```

**Key workflows:**
- **Sweeps:** Bayesian/random/grid search over hyperparameters. Define a `sweep_config`,
  call `wandb.sweep()`, then `wandb.agent()` to run trials.
- **Artifacts:** Version datasets and models with lineage tracking.
- **Model Registry:** Link artifacts to stages (staging, production).

See `references/weights-and-biases/sweeps.md` for full sweep configuration.
See `references/weights-and-biases/artifacts.md` for artifact patterns.
See `references/weights-and-biases/integrations.md` for PyTorch Lightning, Keras, etc.

## 3. LLM Evaluation (lm-evaluation-harness)

Benchmark LLMs on 60+ academic benchmarks (MMLU, GSM8K, HumanEval, HellaSwag).

**Quick start:**
```bash
lm_eval --model hf \
  --model_args pretrained=meta-llama/Llama-2-7b-hf \
  --tasks mmlu,gsm8k,hellaswag \
  --device cuda:0 \
  --batch_size 8
```

**Speed tips:**
- Use vLLM backend for 5-10× faster inference: `--model vllm`
- Reduce fewshot to 0 for quick checks: `--num_fewshot 0`
- Use subset tasks: `--tasks mmlu_stem`

**Common issues:**
- Out of memory → reduce `--batch_size` or use quantization
- Different results than paper → verify `--num_fewshot` matches the paper's setting
- HumanEval requires `--allow_code_execution` and `pip install human-eval`

See `references/lm-evaluation-harness/benchmark-guide.md` for task descriptions.
See `references/lm-evaluation-harness/custom-tasks.md` for domain-specific tasks.
See `references/lm-evaluation-harness/api-evaluation.md` for OpenAI/Anthropic API models.
See `references/lm-evaluation-harness/distributed-eval.md` for multi-GPU strategies.

## 4. Segment Anything Model (SAM)

Zero-shot image segmentation via points, boxes, or masks.

**Quick start:**
```python
from segment_anything import sam_model_registry, SamPredictor

sam = sam_model_registry["vit_h"](checkpoint="sam_vit_h.pth")
predictor = SamPredictor(sam)
predictor.set_image(image)
masks, scores, logits = predictor.predict(point_coords=input_point)
```

**Modes:**
- **Point prompt:** Click a point, get the object containing it.
- **Box prompt:** Draw a bounding box, get the object inside.
- **Mask prompt:** Provide a coarse mask, get a refined version.

See `references/segment-anything/advanced-usage.md` for batch processing and
multi-object selection.
See `references/segment-anything/troubleshooting.md` for checkpoint download and
CUDA memory issues.
