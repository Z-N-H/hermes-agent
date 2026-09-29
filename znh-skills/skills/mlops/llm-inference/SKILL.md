---
name: llm-inference
description: "LLM inference and serving: local GGUF (llama.cpp) and high-throughput server (vLLM)."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [llm, inference, serving, llama.cpp, vllm, gguf, quantization, pagedattention, openai-api]
    related_skills: [huggingface-hub, evaluating-llms-harness, weights-and-biases]
---

# LLM Inference

Run and serve LLMs locally or in production. Two primary paths: **llama.cpp** for local/edge GGUF inference, and **vLLM** for high-throughput server deployment.

---

## Local / Edge: llama.cpp + GGUF

Run local models on CPU, Apple Silicon, CUDA, ROCm, or Intel GPUs.

### Model Discovery

1. Search Hub for llama.cpp-ready models: `https://huggingface.co/models?apps=llama.cpp&sort=trending`
2. Open repo with local-app view: `https://huggingface.co/<repo>?local-app=llama.cpp`
3. Copy the exact `llama-server` or `llama-cli` command from the snippet.

### Quick Start

```bash
llama-cli -m ./models/Llama-3-8B-Q4_K_M.gguf -p "Explain quantum computing" -n 256
```

```bash
llama-server -m ./models/Llama-3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8080
# Then curl: curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

### Quantization Guide

| Quant | Size | Quality | Use Case |
|-------|------|---------|----------|
| Q4_K_M | ~4.5GB (8B) | Good | RAM-constrained, fast inference |
| Q5_K_M | ~5.5GB (8B) | Better | Balanced quality/size |
| Q6_K | ~6.5GB (8B) | Best | Quality-first, sufficient RAM |
| IQ4_XS | ~4GB (8B) | Good | Newer, competitive with Q4_K_M |

Rule of thumb: target ~60-80% of available RAM/VRAM. See `references/llama-cpp-quantization.md` for the full matrix.

### Key Parameters

- `-ngl 999` — offload all layers to GPU (Apple Silicon / CUDA / ROCm)
- `--ctx-size 32768` — context window
- `-t 8` — CPU threads
- `-b 512` — batch size
- `--mirostat 2` — adaptive sampling (reduces repetition)

### Multi-GPU / Cross-Platform

| Platform | Key Flag |
|----------|----------|
| Apple Silicon | `-ngl 999` (Metal) |
| NVIDIA CUDA | `-ngl 999` (cuBLAS) |
| AMD ROCm | `-ngl 999` (hipBLAS) |
| Intel Arc | `--gpu-arch intel` |
| CPU only | omit `-ngl` |

See `references/llama-cpp-advanced-usage.md` for speculative decoding, grammar constraints, and embedding extraction.

---

## Server: vLLM

High-throughput LLM serving with PagedAttention, continuous batching, and OpenAI-compatible API.

### Quick Start

```bash
pip install vllm
```

```python
from vllm import LLM, SamplingParams

llm = LLM(model="meta-llama/Llama-3-8B-Instruct")
sampling = SamplingParams(temperature=0.7, max_tokens=256)
outputs = llm.generate(["Explain quantum computing"], sampling)
```

### Serve with OpenAI-compatible API

```bash
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3-8B-Instruct \
  --tensor-parallel-size 2 \
  --quantization awq
```

### Key Features

- **PagedAttention:** Block-based KV cache reduces memory fragmentation → 24x throughput vs standard transformers.
- **Continuous Batching:** Mixes prefill and decode requests dynamically.
- **Tensor Parallelism:** `--tensor-parallel-size N` for multi-GPU.
- **Quantization:** AWQ, GPTQ, FP8, SqueezeLLM support.
- **Speculative Decoding:** Draft model for 1.5-3x speedup.

### When to use vLLM vs llama.cpp

| Scenario | Recommendation |
|----------|----------------|
| Single-user, local, edge, CPU | llama.cpp |
| Multi-user API server | vLLM |
| Limited GPU memory | vLLM (quantization + paging) |
| Apple Silicon / AMD / Intel GPU | llama.cpp |
| HuggingFace Hub integration | Both (vLLM auto-downloads; llama.cpp needs GGUF) |

See `references/vllm-optimization.md` and `references/vllm-server-deployment.md` for production tuning.

---

## Troubleshooting

### llama.cpp
- **"CUDA out of memory"** → Reduce `-ngl` or use smaller quant (Q4_K_M → IQ4_XS).
- **Slow CPU inference** → Increase `-t` to core count; use Q4_K_M.
- **Apple Silicon Metal errors** → Update macOS; ensure llama.cpp built with `-DLLAMA_METAL=ON`.

### vLLM
- **OOM during prefill** → Reduce `--max-model-len` or enable chunked prefill.
- **Low throughput** → Increase `--max-num-seqs`; enable prefix caching.
- **Model not loading** → Verify HuggingFace token (`huggingface-cli login`) if gated model.

Full troubleshooting guides: `references/llama-cpp-troubleshooting.md` and `references/vllm-troubleshooting.md`.

---

## Related Skills

- `huggingface-hub` — Search, download, upload models and datasets.
- `evaluating-llms-harness` — Benchmark LLMs after inference setup.
- `weights-and-biases` — Log experiments and model registry.
