"""File conversion shared by the Windows desk and its smoke tests."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections import deque
from pathlib import Path
from heif import save_still

IMAGES = "JPG PNG WEBP HEIC AVIF TIFF BMP GIF ICO JXL JP2 TGA PSD".split()
VIDEOS = "MP4 MOV MKV WEBM AVI M4V MPG WMV GIF".split()
IMAGE_INPUTS = set(IMAGES + "JPEG JPE HEIF HIF TIF J2K JFIF DIB DDS EXR HDR PPM PGM PBM QOI PCX".split())
VIDEO_INPUTS = set(VIDEOS + "MPEG MTS M2TS TS FLV VOB 3GP 3G2 OGV ASF M2V".split())
LOSSY = {"JPG", "WEBP", "HEIC", "AVIF", "JXL", "JP2"}


class Cancelled(Exception):
    pass


def extension(path):
    return path.suffix[1:].upper()


def tool(name):
    found = shutil.which(name + ".exe")
    if found:
        return found
    programs = Path(os.environ["ProgramFiles"])
    if name == "magick":
        candidates = sorted(programs.glob("ImageMagick-*/magick.exe"), reverse=True)
    else:
        winget = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet"
        candidates = [winget / "Links" / (name + ".exe")]
        candidates.extend(winget.glob("Packages/Gyan.FFmpeg_*/ffmpeg*/bin/" + name + ".exe"))
    for path in candidates:
        if path.is_file():
            return str(path)
    package = "ImageMagick" if name == "magick" else "FFmpeg"
    raise RuntimeError(f"Install {package} using Set up.cmd, then reopen actual converter.")


def run(name, args, cancel, progress=None):
    if cancel.is_set():
        raise Cancelled()
    # Read diagnostics concurrently so cancellation also works while an encoder is silent.
    with subprocess.Popen([tool(name), *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW) as proc:
        tail = deque(maxlen=18)

        def read():
            duration = 0
            last = -1
            for line in proc.stderr:
                line = line.strip()
                match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", line)
                if match:
                    h, m, s = map(float, match.groups())
                    duration = 3600 * h + 60 * m + s
                if line.startswith("out_time_us=") and duration and progress:
                    value = line.partition("=")[2]
                    if value.lstrip("-").isdigit():
                        percent = min(99, max(0, int(int(value) / (duration * 10000))))
                        if percent != last:
                            progress(percent)
                            last = percent
                if line and not re.match(r"^[\w.]+=", line):
                    tail.append(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            while proc.poll() is None:
                if cancel.wait(0.08):
                    proc.kill()
                    break
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            reader.join()
            proc.stderr.close()
        if cancel.is_set():
            raise Cancelled()
        if proc.returncode:
            raise RuntimeError("\n".join(tail) or f"{name} exited with code {proc.returncode}.")


def photo(source, output, quality, cancel):
    fmt = extension(output)
    args = ["-limit", "thread", "2", str(source) + "[0]", "-auto-orient"]
    if fmt in {"JPG", "BMP", "JP2"}:
        args += ["-colorspace", "sRGB", "-background", "white", "-alpha", "remove", "-alpha", "off"]
    if fmt == "ICO":
        args += ["-thumbnail", "256x256>", "-background", "none", "-gravity", "center",
                 "-extent", "256x256", "-define", "icon:auto-resize=256,128,64,48,32,16"]
    if fmt == "PNG":
        args += ["-define", "png:compression-level=3"]
    if fmt in LOSSY:
        args += ["-quality", str(quality)]
    run("magick", [*args, output], cancel)


FF_INPUT = ["-nostdin", "-hide_banner", "-protocol_whitelist", "file,pipe"]


def heic(source, output, work, quality, cancel):
    # The Windows ImageMagick package includes a HEIC decoder only.
    bitmap = work / "heic-input.png"
    run("magick", ["-limit", "thread", "2", str(source) + "[0]", "-auto-orient", "-colorspace", "sRGB",
                   "-background", "white", "-alpha", "remove", "-alpha", "off", "-depth", "8", bitmap], cancel)
    with bitmap.open("rb") as handle:
        handle.seek(16)
        width = int.from_bytes(handle.read(4), "big")
        height = int.from_bytes(handle.read(4), "big")
    stream = work / "still.mp4"
    run("ffmpeg", [*FF_INPUT, "-loglevel", "error", "-i", bitmap, "-frames:v", "1",
                   "-c:v", "libx265", "-preset", "fast", "-crf", str({95: 17, 85: 23, 72: 29}[quality]),
                   "-vf", "scale=out_color_matrix=bt709,pad='max(16,ceil(iw/2)*2)':'max(16,ceil(ih/2)*2)'",
                   "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-color_primaries", "bt709",
                   "-color_trc", "iec61966-2-1", "-colorspace", "bt709",
                   "-x265-params", "log-level=error:pools=2", stream], cancel)
    save_still(stream, output, width, height)


def movie(source, output, still, quality, copy, cancel, progress):
    fmt = extension(output)
    args = [*FF_INPUT, "-nostats", "-progress", "pipe:2"]
    if still:
        args += ["-loop", "1", "-framerate", "25"]
    args += ["-i", source, "-map", "0:V:0"]
    if still:
        args += ["-t", "5"]
    if fmt != "GIF":
        args += ["-map", "0:a:0?"]
    if copy:
        if still or fmt == "GIF":
            raise ValueError("Choose Balanced to encode this file. Stream copy requires a video and a compatible video container.")
        args += ["-c", "copy"]
    elif fmt == "GIF":
        args += ["-vf", "fps=12,scale='min(720,iw)':-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse", "-loop", "0"]
    else:
        args += ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p"]
        if fmt == "WEBM":
            args += ["-c:v", "libvpx-vp9", "-row-mt", "1", "-deadline", "realtime", "-cpu-used", "6",
                     "-b:v", "0", "-crf", str({95: 26, 85: 32, 72: 38}[quality]), "-c:a", "libopus"]
        elif fmt in {"WMV", "AVI", "MPG"}:
            video, audio = {"WMV": ("wmv2", "wmav2"), "AVI": ("mpeg4", "libmp3lame"), "MPG": ("mpeg2video", "mp2")}[fmt]
            args += ["-c:v", video, "-q:v", str({95: 2, 85: 4, 72: 8}[quality]),
                     "-c:a", audio, "-ar", "48000", "-ac", "2"]
        else:
            args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str({95: 18, 85: 22, 72: 28}[quality]),
                     "-c:a", "aac", "-b:a", "160k"]
    if fmt in {"MP4", "MOV", "M4V"}:
        args += ["-movflags", "+faststart"]
    run("ffmpeg", [*args, output], cancel, progress)


def convert(source, directory, fmt, motion=False, preset="Balanced", cancel=None, progress=None):
    source = Path(source).resolve()
    directory = Path(directory).resolve()
    if not source.is_file() or extension(source) not in IMAGE_INPUTS | VIDEO_INPUTS:
        raise ValueError("Choose a supported local image or video.")
    if fmt not in (VIDEOS if motion else IMAGES):
        raise ValueError("Unknown output format.")
    cancel = cancel or threading.Event()
    quality = {"High quality": 95, "Smaller file": 72}.get(preset, 85)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = "." + fmt.lower()
    partial = directory / (".actual-" + uuid.uuid4().hex + suffix)
    try:
        with tempfile.TemporaryDirectory(prefix="actual-") as scratch:
            work = Path(scratch)
            bridge = work / "frame.png"
            still = extension(source) in IMAGE_INPUTS
            if motion:
                still = still and extension(source) != "GIF"
                if still:
                    photo(source, bridge, quality, cancel)
                movie(bridge if still else source, partial, still, quality, preset == "Copy streams", cancel, progress)
            else:
                if not still:
                    run("ffmpeg", [*FF_INPUT, "-loglevel", "error", "-i", source, "-map", "0:V:0", "-frames:v", "1", "-update", "1", bridge], cancel)
                if fmt == "HEIC":
                    heic(source if still else bridge, partial, work, quality, cancel)
                else:
                    photo(source if still else bridge, partial, quality, cancel)
        if cancel.is_set():
            raise Cancelled()
        if not partial.is_file() or partial.stat().st_size == 0:
            raise OSError("The encoder produced an empty file.")
        number = 0
        while True:
            tag = f" ({number})" if number else ""
            dest = directory / (source.stem + tag + suffix)
            try:
                # Windows rename is atomic and refuses to replace an existing destination.
                partial.rename(dest)
                return dest
            except FileExistsError:
                number += 1
    finally:
        partial.unlink(missing_ok=True)
