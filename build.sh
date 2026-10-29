#!/bin/bash
set -e
pip install -r requirements.txt
# Kronos-mini weights (~32MB) from Hugging Face
mkdir -p models/mini models/mini-tok
for f in config.json model.safetensors; do
  curl -sL --retry 3 --max-time 600 -o models/mini/$f \
    "https://huggingface.co/NeoQuasar/Kronos-mini/resolve/main/$f"
done
for f in config.json model.safetensors; do
  curl -sL --retry 3 --max-time 600 -o models/mini-tok/$f \
    "https://huggingface.co/NeoQuasar/Kronos-Tokenizer-2k/resolve/main/$f"
done
ls -la models/mini models/mini-tok












