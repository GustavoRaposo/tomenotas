#!/bin/bash
# training/setup.sh — prepara o ambiente de treino do wake word "Tomenotas".
# Roda UMA vez. Requer: GPU NVIDIA + driver, git, wget, ~5GB (deps/repos).
# Uso:  ./setup.sh [WORKDIR]   (padrão: ~/tomenotas-wakeword-training)
set -e

WORKDIR="${1:-$HOME/tomenotas-wakeword-training}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$WORKDIR"
cd "$WORKDIR"
echo "==> Diretório de trabalho: $WORKDIR"

echo "==> Criando venv de treino..."
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install -q --upgrade pip

echo "==> Instalando PyTorch (CUDA) — pode baixar ~2.5GB..."
# wheel padrão já vem com CUDA; serve para a GTX 1650
pip install -q torch

echo "==> Clonando e instalando o openWakeWord (instalação completa p/ treino)..."
[ -d openwakeword ] || git clone --depth 1 https://github.com/dscripka/openwakeword
pip install -q -e ./openwakeword
pip install -q piper-phonemize webrtcvad mutagen==1.47.0 datasets scipy pyyaml tqdm numpy onnx

echo "==> Clonando o piper-sample-generator + baixando o modelo gerador..."
[ -d piper-sample-generator ] || git clone --depth 1 https://github.com/rhasspy/piper-sample-generator
mkdir -p piper-sample-generator/models
[ -f piper-sample-generator/models/en_US-libritts_r-medium.pt ] || \
  wget -q -O piper-sample-generator/models/en_US-libritts_r-medium.pt \
    "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt"

echo "==> Baixando os modelos base do openWakeWord (melspec + embedding)..."
mkdir -p openwakeword/openwakeword/resources/models
for m in melspectrogram.onnx embedding_model.onnx; do
  dst="openwakeword/openwakeword/resources/models/$m"
  [ -f "$dst" ] || wget -q -O "$dst" \
    "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/$m"
done

echo "==> Copiando o config do treino..."
cp "$HERE/tomenotas.yml" "$WORKDIR/tomenotas.yml"

echo ""
echo "==================================================="
echo " Setup pronto em $WORKDIR"
echo " Próximo passo:  ./download_data.sh \"$WORKDIR\""
echo " (baixa RIRs, ruído de fundo e ~2000h de features negativas — vários GB)"
echo "==================================================="
