#!/usr/bin/env bash
# Build Search and Track as a self-contained x86_64 AppImage.
#
#   tools/build_appimage.sh        ->  dist/SearchAndTrack-<version>-x86_64.AppImage (+ .sha256)
#
# The image carries its own Python (python-build-standalone), pygame-ce and numpy, and the
# game's code, data and fonts. Nothing is installed on the build machine; downloads are
# pinned and cached in build/appimage/cache. Needs bash, curl, tar, file and
# desktop-file-validate (objdump, if present, reports the oldest glibc the image runs on).
#
# Environment:
#   VERSION       version in the file name (default: pyproject.toml)
#   PYTHON_DIR    use an unpacked python-build-standalone tree instead of downloading one
#   APPDIR_ONLY=1 stop after assembling and smoke-testing the AppDir (no appimagetool)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${BUILD_DIR:-$ROOT/build/appimage}"
DIST="${DIST_DIR:-$ROOT/dist}"
CACHE="$BUILD/cache"
APPDIR="$BUILD/SearchAndTrack.AppDir"
ARCH=x86_64

# ---------------------------------------------------------------- pinned downloads
PY_VERSION=3.12.13
PBS_RELEASE=20260718
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/cpython-${PY_VERSION}%2B${PBS_RELEASE}-${ARCH}-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA256=5854aa6ec71cad00334d5065633c210b2e7feb40956767a59a91791cadcf0b79
TOOL_VERSION=1.9.1
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${TOOL_VERSION}/appimagetool-${ARCH}.AppImage"
TOOL_SHA256="${TOOL_SHA256:-}"
RUNTIME_VERSION=20251108
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/${RUNTIME_VERSION}/runtime-${ARCH}"
RUNTIME_SHA256="${RUNTIME_SHA256:-}"

VERSION="${VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -n 1)}"
OUT="$DIST/SearchAndTrack-${VERSION}-${ARCH}.AppImage"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
note() {   # a fact worth keeping: printed, and an annotation on the GitHub Actions run
    echo "$1: $2"
    if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::notice title=$1::$2"; fi
}
fetch() {  # fetch URL FILE [SHA256]
    local url=$1 file=$2 want=${3:-} got
    if [ ! -s "$file" ]; then
        log "download $(basename "$file")"
        curl -fsSL --retry 3 --retry-delay 5 -o "$file.part" "$url"
        mv "$file.part" "$file"
    fi
    got=$(sha256sum "$file" | cut -d' ' -f1)
    if [ -n "$want" ] && [ "$got" != "$want" ]; then
        echo "checksum mismatch for $(basename "$file"): expected $want, got $got" >&2
        rm -f "$file"
        exit 1
    fi
    if [ -z "$want" ]; then note "sha256 $(basename "$file")" "$got"; fi
}

need=(curl tar sha256sum)
[ "${APPDIR_ONLY:-0}" = 1 ] || need+=(file desktop-file-validate)    # appimagetool insists on both
for cmd in "${need[@]}"; do
    command -v "$cmd" >/dev/null || { echo "missing $cmd (desktop-file-validate: package desktop-file-utils)" >&2; exit 1; }
done

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr" "$CACHE" "$DIST"

# ---------------------------------------------------------------- 1. Python
if [ -n "${PYTHON_DIR:-}" ]; then
    log "python from $PYTHON_DIR"
    cp -a "$PYTHON_DIR" "$APPDIR/usr/python"
else
    fetch "$PY_URL" "$CACHE/cpython-$PY_VERSION-$PBS_RELEASE-$ARCH.tar.gz" "$PY_SHA256"
    tar -xzf "$CACHE/cpython-$PY_VERSION-$PBS_RELEASE-$ARCH.tar.gz" -C "$APPDIR/usr"    # -> usr/python
fi
PY="$APPDIR/usr/python/bin/python3"
PYVER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
STDLIB="$APPDIR/usr/python/lib/python$PYVER"
SITE="$STDLIB/site-packages"
rm -f "$STDLIB/EXTERNALLY-MANAGED"
"$PY" -m pip --version >/dev/null 2>&1 || "$PY" -m ensurepip --default-pip >/dev/null

# ---------------------------------------------------------------- 2. pygame-ce and numpy
# Only manylinux2014 wheels: the same glibc 2.17 baseline as the bundled Python.
log "install $(grep -o '^[A-Za-z0-9_.-]*==[0-9.]*' "$ROOT/packaging/appimage/requirements.txt" | tr '\n' ' ')"
"$PY" -m pip install --quiet --no-cache-dir --no-compile --disable-pip-version-check \
    --only-binary=:all: --platform manylinux2014_x86_64 --target "$SITE" --upgrade \
    -r "$ROOT/packaging/appimage/requirements.txt"
rm -rf "$SITE/bin"

# ---------------------------------------------------------------- 3. the game
log "copy the game"
GAME="$APPDIR/usr/share/searchtrack"
mkdir -p "$GAME"
cp -a "$ROOT/src" "$ROOT/data" "$ROOT/assets" "$GAME/"
cp "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/CHANGELOG.md" "$GAME/"
find "$GAME" \( -name '__pycache__' -o -name '*.egg-info' \) -prune -exec rm -rf {} +
# the bundled Python finds the game through a path relative to its site-packages
echo "../../../../share/searchtrack/src" > "$SITE/searchtrack.pth"

# ---------------------------------------------------------------- 4. slim it down
log "prune"
"$PY" -m pip uninstall --quiet --yes pip >/dev/null 2>&1 || true
rm -rf "$STDLIB"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3,pydoc_data} "$STDLIB"/lib-dynload/_tkinter*.so \
       "$SITE"/{setuptools,pkg_resources,_distutils_hack,distutils-precedence.pth,wheel}* \
       "$APPDIR"/usr/python/lib/{tcl,tk,itcl,thread,Tix,libtcl,libtk}* "$APPDIR/usr/python/lib/pkgconfig" \
       "$APPDIR/usr/python/include" "$APPDIR/usr/python/share" \
       "$APPDIR"/usr/python/bin/{idle3,pydoc3,2to3,pip}* \
       "$SITE"/numpy/{tests,*/tests,*/*/tests} "$SITE"/pygame/{tests,examples,docs}
find "$APPDIR" -name '__pycache__' -prune -exec rm -rf {} +

# ---------------------------------------------------------------- 5. bytecode
# The image is read-only, so compile now; unchecked-hash .pyc files ignore timestamps.
log "compile bytecode"
"$PY" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$APPDIR/usr/python/lib" "$GAME/src" >/dev/null \
    || log "some files did not compile (they could not be imported either)"

# ---------------------------------------------------------------- 6. desktop integration
log "AppRun, desktop entry, icon"
install -m 755 "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
install -m 644 "$ROOT/packaging/appimage/searchtrack.desktop" "$APPDIR/searchtrack.desktop"
install -m 644 "$ROOT/assets/icons/searchtrack.png" "$APPDIR/searchtrack.png"
ln -sf searchtrack.png "$APPDIR/.DirIcon"
install -Dm 644 "$APPDIR/searchtrack.desktop" "$APPDIR/usr/share/applications/searchtrack.desktop"
install -Dm 644 "$APPDIR/searchtrack.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/searchtrack.png"

if command -v objdump >/dev/null; then
    GLIBC=$({ find "$APPDIR/usr" -type f \( -name '*.so*' -o -name 'python3.*' \) -exec objdump -T {} + 2>/dev/null \
              || true; } | grep -o 'GLIBC_[0-9][0-9.]*' | sort -Vu | tail -n 1)
    note "minimum glibc" "${GLIBC#GLIBC_}"
fi
note "AppDir size" "$(du -sh "$APPDIR" | cut -f1)"

# ---------------------------------------------------------------- 7. smoke test: a watch, headless
smoke() {  # smoke LAUNCHER SCENARIO PNG
    log "smoke test: $2"
    rm -f "$3"
    env SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy XDG_DATA_HOME="$BUILD/home" APPIMAGE_EXTRACT_AND_RUN=1 \
        "$1" --screenshot "$3" --scenario "$2" --seconds 90
    test -s "$3"
}
smoke "$APPDIR/AppRun" us_training_intercept "$BUILD/smoke-appdir.png"

if [ "${APPDIR_ONLY:-0}" = 1 ]; then
    log "AppDir ready: $APPDIR"
    exit 0
fi

# ---------------------------------------------------------------- 8. pack
TOOL="$CACHE/appimagetool-$TOOL_VERSION-$ARCH.AppImage"
RUNTIME="$CACHE/runtime-$RUNTIME_VERSION-$ARCH"
fetch "$TOOL_URL" "$TOOL" "$TOOL_SHA256"
fetch "$RUNTIME_URL" "$RUNTIME" "$RUNTIME_SHA256"
chmod +x "$TOOL"
log "appimagetool $TOOL_VERSION"
rm -f "$OUT" "$OUT.sha256"
ARCH=$ARCH APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$OUT"
(cd "$DIST" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256")

smoke "$OUT" su_training_guidance "$BUILD/smoke-appimage.png"
note "AppImage" "$(basename "$OUT") $(du -h "$OUT" | cut -f1)"
