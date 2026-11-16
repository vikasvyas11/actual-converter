"""Windows integration checks. Pass an optional external HEIC sample on the command line."""
import json
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from converter import Cancelled, IMAGES, VIDEOS, convert, tool


def inspect_image(path):
    size = subprocess.check_output([tool("magick"), "identify", "-format", "%w %h", str(path) + "[0]"], text=True)
    return tuple(map(int, size.split()))


def streams(path):
    return json.loads(subprocess.check_output([tool("ffprobe"), "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", path]))


def check(directory, sample=None):
    start = perf_counter()
    png = directory / "photo [1] 50%.png"
    subprocess.run([tool("magick"), "-size", "101x79", "gradient:#28754a-#e8f7bb", png], check=True)
    original = png.read_bytes()
    for fmt in IMAGES:
        out = convert(png, directory, fmt)
        size = inspect_image(out)
        assert size == ((256, 256) if fmt == "ICO" else (101, 79)), (fmt, size)
        if fmt == "HEIC":
            encoded = out
        print("Image output", fmt, flush=True)
    assert png.read_bytes() == original
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda _: convert(png, directory, "JPG"), range(2)))
    assert len(set(paths)) == 2 and all(path.is_file() for path in paths)
    for src in (encoded, sample) if sample else (encoded,):
        for fmt in ("JPG", "PNG"):
            out = convert(src, directory, fmt)
            assert inspect_image(src) == inspect_image(out)
            print("HEIC to", fmt, inspect_image(out), flush=True)
    video = directory / "test video.mp4"
    subprocess.run([tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.6", "-c:v", "libx264", "-c:a", "aac", video], check=True)
    for fmt in VIDEOS:
        out = convert(video, directory, fmt, motion=True)
        info = streams(out)
        types = {s["codec_type"] for s in info["streams"]}
        assert types == ({"video"} if fmt == "GIF" else {"audio", "video"}), (fmt, types)
        assert int(info["streams"][0]["width"]) == 128
        print("Video output", fmt, flush=True)
    copied = convert(video, directory, "MKV", motion=True, preset="Copy streams")
    assert [s["codec_name"] for s in streams(copied)["streams"]] == ["h264", "aac"]
    assert inspect_image(convert(video, directory, "HEIC")) == (128, 96)
    clip = convert(png, directory, "MP4", motion=True)
    assert abs(float(streams(clip)["format"]["duration"]) - 5) < .1
    broken = directory / "invalid.heic"
    broken.write_text("invalid fixture")
    try:
        convert(broken, directory, "JPG")
    except RuntimeError:
        assert not (directory / "invalid.jpg").exists()
    else:
        raise AssertionError("Invalid HEIC accepted")
    stop = threading.Event()
    timer = threading.Timer(.05, stop.set)
    timer.start()
    try:
        convert(video, directory, "WEBM", motion=True, cancel=stop)
    except Cancelled:
        pass
    else:
        raise AssertionError("Cancelled conversion completed")
    finally:
        timer.cancel()
    assert not list(directory.glob(".actual-*"))
    print(f"Passed in {perf_counter()-start:.1f} s")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="actual-tests-") as folder:
        check(Path(folder), Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None)
