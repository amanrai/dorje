#!/usr/bin/env bash
# External services for Dorje
# Run on the Mac Mini (M4, 32GB)
#
# Install: pip install vllm-mlx
# Or:      uv pip install git+https://github.com/waybarrios/vllm-mlx.git

# Embedding model — CodeRankEmbed (137M params)
# Served on port 34567
vllm-mlx serve nomic-ai/CodeRankEmbed \
    --host 0.0.0.0 \
    --port 34567 &

# LLM — SmolLM3-3B for query classification and diff summarization
# Served on port 34568
vllm-mlx serve HuggingFaceTB/SmolLM3-3B \
    --host 0.0.0.0 \
    --port 34568 &

wait
