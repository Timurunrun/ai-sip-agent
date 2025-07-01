#!/usr/bin/env bash
###############################################################################
# build_pjsua2.sh
#
# Скрипт собирает и устанавливает PJSIP/PJSUA2 в локальный
# префикс + кладёт python-обёртку в virtualenv проекта.
#
#   ./build_pjsua2.sh           # запустить из каталога pjsip_build
#
# Каталог pjsip_build/ ─┬─ build_pjsua2.sh   (этот файл)
#                       ├─ venv/             (будет создан)
#                       ├─ pjproject/        (исходники PJSIP)
#                       └─ local/            (готовые .so, .a, headers)
#
# Проверено на Ubuntu 22.04 x86-64.
###############################################################################
set -euo pipefail

PJ_VERSION_DEFAULT="2.15.1"
PJ_VERSION="${PJ_VERSION:-$PJ_VERSION_DEFAULT}"

VENV_DIR="venv"
PREFIX_DIR="local"
SRC_DIR="pjproject"

NPROC="$(nproc)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()  { echo -e "\e[1;32m[+] $*\e[0m"; }
warn() { echo -e "\e[1;33m[!] $*\e[0m"; }
err()  { echo -e "\e[1;31m[✗] $*\e[0m"; exit 1; }

install_apt_deps() {
  log "Установка системных зависимостей..."
  sudo apt-get update
  sudo apt-get install -y \
    build-essential git autoconf libtool pkg-config \
    swig python3-dev python3-venv \
    libasound2-dev libssl-dev libopus-dev \
    libv4l-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
    libavformat-dev libavcodec-dev libavdevice-dev \
    libavfilter-dev libx264-dev \
    libopencore-amrwb-dev libopencore-amrnb-dev libvo-amrwbenc-dev
}

create_venv() {
  if [[ -d "$VENV_DIR" ]]; then
    log "Virtualenv $VENV_DIR уже существует, пропускаем создание."
  else
    log "Создаём virtualenv ($VENV_DIR)..."
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
  pip install -U pip setuptools wheel
}

clone_pjsip() {
  if [[ -d "$SRC_DIR" ]]; then
    warn "Каталог $SRC_DIR уже существует, пропускаем clone."
  else
    log "Клонируем pjproject v$PJ_VERSION..."
    git clone --branch "$PJ_VERSION" --depth 1 https://github.com/pjsip/pjproject.git "$SRC_DIR"
  fi
}

build_pjsip() {
  log "Сборка PJSIP (prefix=$SCRIPT_DIR/$PREFIX_DIR)..."
  cd "$SRC_DIR"

  # Ниже укажите нужные вам параметры
  ./configure \
    --prefix="$SCRIPT_DIR/$PREFIX_DIR" \
    --enable-shared \
    --disable-video --disable-audio --disable-v4l2 --disable-sdl \
    --with-opus \
    CFLAGS="$(python3-config --includes)"

  make dep
  make -j"$NPROC"
  make install # без sudo, пишет в $PREFIX_DIR

  cd "$SCRIPT_DIR"
}

patch_activate() {
  ACT_FILE="$VENV_DIR/bin/activate"
  MARKER="# >>> PJSIP LD_LIBRARY_PATH >>>"
  if ! grep -q "$MARKER" "$ACT_FILE"; then
    log "Прописываем LD_LIBRARY_PATH в activate..."
    cat >> "$ACT_FILE" <<EOF

$MARKER
export LD_LIBRARY_PATH="\$VIRTUAL_ENV/../$PREFIX_DIR/lib:\${LD_LIBRARY_PATH:-}"
# <<< PJSIP LD_LIBRARY_PATH <<<
EOF
  fi
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
}

build_python_module() {
  log "Сборка и установка pjsua2..."
  cd "$SRC_DIR/pjsip-apps/src/swig/python"

  make
  # Установка в текущий активный virtualenv
  pip install .

  cd "$SCRIPT_DIR"
}

test_import() {
  log "Тестируем импорт pjsua2..."
  python - <<'PY'
import pjsua2, sys, pathlib
print("✔ pjsua2 импортирован. Расположение:", pathlib.Path(pjsua2.__file__).resolve())
e = pjsua2.Endpoint()
e.libCreate()
print("✔ Endpoint создан успешно")
e.libDestroy()
PY
}

###############################################################################
# Основной сценарий
###############################################################################
log "PJSUA2 build script запущен (директория: $SCRIPT_DIR)"

install_apt_deps
create_venv
clone_pjsip
build_pjsip
patch_activate
build_python_module
test_import

log "Готово!"
