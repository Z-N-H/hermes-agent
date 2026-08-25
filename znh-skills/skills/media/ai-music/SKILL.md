---
name: ai-music
description: "AI music generation, audio analysis, and songwriting craft: HeartMuLa, AudioCraft/MusicGen, Suno prompts, and spectrogram analysis."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [music, audio, generation, ai, audiocraft, heartmula, suno, songwriting, spectrogram]
    related_skills: [comfyui, llama-cpp]
---

# AI Music

Generate music and sound with AI, analyze audio, and craft effective prompts. Covers open-source models (HeartMuLa, AudioCraft), prompt engineering for Suno, and audio visualization.

---

## Audio Generation Models

### HeartMuLa (Open-Source, Apache-2.0)

Family of music foundation models that generate full songs from lyrics + tags. Comparable to Suno for open-source.

```bash
git clone https://github.com/HeartMuLa/heartlib.git
cd heartlib
uv venv --python 3.10 .venv && . .venv/bin/activate
uv pip install -e .
# Fix dependencies: uv pip install --upgrade datasets transformers
# Patch source for transformers 5.x (see heartlib docs)
```

**Quick generation:**
```bash
python ./examples/run_music_generation.py \
  --model_path=./ckpt --version="3B" \
  --lyrics="./assets/lyrics.txt" --tags="./assets/tags.txt" \
  --save_path="./assets/output.mp3" --lazy_load true
```

**Key parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--max_audio_length_ms` | 240000 | Max length in ms (240s = 4 min) |
| `--topk` | 50 | Top-k sampling |
| `--temperature` | 1.0 | Sampling temperature |
| `--cfg_scale` | 1.5 | Classifier-free guidance |
| `--lazy_load` | false | Load/unload models on demand |

**Pitfalls:**
- Do NOT use bf16 for HeartCodec — use fp32 for quality.
- Tags may be ignored (known issue #90). Lyrics dominate; experiment with tag ordering.
- Triton not available on macOS — Linux/CUDA only for GPU acceleration.
- RTX 5080 incompatibility reported upstream.

### AudioCraft (Meta)

Text-to-music and text-to-sound generation with MusicGen, AudioGen, and EnCodec.

```bash
pip install audiocraft
```

**Text-to-music:**
```python
from audiocraft.models import MusicGen
import torchaudio

model = MusicGen.get_pretrained("facebook/musicgen-medium")
model.set_generation_params(duration=30, top_k=250, temperature=1.0, cfg_coef=3.0)
wav = model.generate(["epic orchestral soundtrack with strings and brass"])
torchaudio.save("output.wav", wav[0].cpu(), sample_rate=32000)
```

**Model variants:**
| Model | Size | Use Case |
|-------|------|----------|
| `musicgen-small` | 300M | Quick generation |
| `musicgen-medium` | 1.5B | Balanced quality |
| `musicgen-large` | 3.3B | Best quality |
| `musicgen-melody` | 1.5B | Melody conditioning |
| `musicgen-stereo-*` | Varies | Stereo output |
| `audiogen-medium` | 1.5B | Sound effects |

**Melody conditioning:**
```python
model = MusicGen.get_pretrained("facebook/musicgen-melody")
melody, sr = torchaudio.load("melody.wav")
wav = model.generate_with_chroma(["acoustic guitar folk song"], melody, sr)
```

---

## Songwriting & Prompt Engineering

### Song Structure

Common skeletons:
- **ABABCB** — Verse/Chorus/Verse/Chorus/Bridge/Chorus (most pop/rock)
- **AABA** — Verse/Verse/Bridge/Verse (jazz standards, ballads)
- **ABAB** — Verse/Chorus alternating (simple, direct)

Six building blocks: Intro, Verse, Pre-Chorus, Chorus, Bridge, Outro.

### Rhyme & Meter

- **Perfect rhyme:** lean/mean
- **Assonance:** had/glass (same vowels)
- **Consonance:** scene/when (similar endings)
- **Internal rhyme:** within a line, not just at ends
- **Meter:** stressed syllables matter more than total count

### Suno AI Prompt Engineering

**Style field formula:**
```
Genre + Mood + Era + Instruments + Vocal Style + Production + Dynamics
```

**Bad:** `"sad rock song"`
**Good:** `"Cinematic orchestral spy thriller, 1960s Cold War era, smoky sultry female vocalist, big band jazz, brass section with trumpets and french horns, sweeping strings, minor key, vintage analog warmth"`

**Key tips:**
- V4.5+ supports up to 1,000 chars in Style field — use them
- NO artist names or trademarks — describe the sound
- Describe the dynamic JOURNEY: "Begins as a haunting whisper... builds to full orchestra... strips back to silence"
- Use Custom Mode for serious work (separate Style + Lyrics)
- Add structural metatags: `[Intro] [Verse] [Chorus] [Bridge] [Outro]`
- Vocal performance tags: `[Whispered] [Belted] [Falsetto] [Harmonies]`
- 5-8 tags per section max; don't contradict yourself

**Phonetic tricks for AI singers:**
- Spell words as they sound: "through" -> "thru"
- Hyphenate to guide syllables: "Re-search", "bio-engineering"
- ALL CAPS = louder, more intense
- Vowel extension: "lo-o-o-ove" = sustained/melisma
- Always test proper nouns in a short 30-second clip first

**Workflow:**
1. Write concept/hook first
2. Map original structure if adapting
3. Generate raw material freely, then structure
4. Draft lyrics, read/sing aloud
5. Build Suno style description (paint the dynamic journey)
6. Add metatags for performance direction
7. Generate 3-5 variations minimum
8. Extend/Continue the most promising takes

---

## Audio Analysis

### songsee (Spectrograms & Features)

Generate spectrograms and multi-panel audio visualizations from audio files.

```bash
go install github.com/steipete/songsee/cmd/songsee@latest
songsee track.mp3 -o spectrogram.png
songsee track.mp3 --viz spectrogram,mel,chroma,hpss,selfsim,loudness,tempogram,mfcc,flux
songsee track.mp3 --start 12.5 --duration 8 -o slice.jpg
```

**Visualization types:** `spectrogram`, `mel`, `chroma`, `hpss` (harmonic/percussive separation), `selfsim` (self-similarity), `loudness`, `tempogram`, `mfcc`, `flux` (spectral flux).

Use `vision_analyze` on the output images for automated audio analysis.

---

## When to Use What

| Tool | Best For |
|------|----------|
| **HeartMuLa** | Local/offline generation, open-source, lyrics + tags |
| **AudioCraft** | Quick prototyping, HuggingFace ecosystem, melody conditioning |
| **Suno** | Commercial quality, no setup, fastest iteration |
| **songsee** | Audio debugging, comparing outputs, documenting pipelines |

## Related Skills

- `comfyui` — For ComfyUI-based audio workflows
- `llama-cpp` — For local LLM-based lyric generation
