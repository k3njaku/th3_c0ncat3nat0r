import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image
from fpdf import FPDF
from PyPDF2 import PdfMerger
from pydub import AudioSegment

# ---------------- UI ----------------
st.set_page_config(page_title="th3 c0ncat3nat0r", page_icon="🔗")
st.title("th3 c0ncat3nat0r")
st.write("Combine multiple media files into a single output.")
uploaded_files = st.file_uploader("Upload files", accept_multiple_files=True)

# -------------- Helpers -------------
def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def detect_type(files):
    """Detect if uploaded files are documents, audio or video."""
    types = set()
    for f in files:
        mime = (f.type or '').split('/')
        primary = mime[0] if mime else ''
        ext = Path(f.name).suffix.lower()
        if primary in {"audio", "video", "image"}:
            types.add(primary)
        elif ext in {".pdf", ".txt"}:
            types.add("document")
        else:
            types.add("document")
    if types == {"audio"}:
        return "audio"
    if types == {"video"}:
        return "video"
    if types.issubset({"image", "document"}):
        return "document"
    return "mixed"

# -------- Document combine ----------
def combine_documents(files):
    merger = PdfMerger()
    tmp_files = []
    for f in files:
        ext = Path(f.name).suffix.lower()
        if ext in {".png", ".jpg", ".jpeg"}:
            img = Image.open(f).convert("RGB")
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            img.save(tmp.name, "PDF")
            tmp_files.append(tmp)
            merger.append(tmp.name)
        elif ext == ".txt":
            text = f.read().decode("utf-8")
            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.set_font("helvetica", size=12)  # safer than "Arial"
            for line in text.splitlines():
                pdf.multi_cell(0, 10, line)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(tmp.name)
            tmp_files.append(tmp)
            merger.append(tmp.name)
        else:  # treat as pdf
            merger.append(f)
    output = io.BytesIO()
    merger.write(output)
    merger.close()
    for t in tmp_files:
        try:
            t.close()
            Path(t.name).unlink(missing_ok=True)
        except Exception:
            pass
    output.seek(0)
    return output

# ---------- Audio combine -----------
def combine_audio(files):
    # Requires system ffmpeg for many formats
    combined = AudioSegment.silent(duration=0)
    for f in files:
        seg = AudioSegment.from_file(f).set_frame_rate(44100).set_channels(2)
        combined += seg
    output = io.BytesIO()
    combined.export(output, format="mp3", bitrate="192k")
    output.seek(0)
    return output

# ---------- Video combine (FFmpeg) ----------
def _run(cmd):
    """Run a subprocess command and raise a readable error if it fails."""
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "FFmpeg failed")
    return proc

def _normalize_to_mp4(src_path: str, dst_path: str, width: int = 1280, fps: int = 30):
    """
    Transcode any input to a consistent MP4 (H.264/AAC) so concat works
    regardless of original codec/resolution/fps.
    """
    ffmpeg = shutil.which("ffmpeg")
    vf = f"scale='min({width},iw)':'-2',fps={fps},format=yuv420p"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", src_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        dst_path
    ]
    _run(cmd)

def combine_video_ffmpeg(files):
    """
    Save uploads -> normalize each to MP4 (H.264/AAC) -> concat demuxer (stream copy).
    Works for "every kind" by re-encoding to a common format first.
    """
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg not found. Install with: sudo apt-get install -y ffmpeg")

    # 1) Persist uploads to disk
    temp_sources = []
    for f in files:
        src = tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix)
        src.write(f.read())
        src.flush(); src.close()
        temp_sources.append(src.name)

    # 2) Normalize each to a common format
    normalized = []
    try:
        for src in temp_sources:
            norm = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            norm.close()
            _normalize_to_mp4(src, norm.name, width=1280, fps=30)
            normalized.append(norm.name)

        # 3) Concat via demuxer (no re-encode)
        listfile = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        listfile.write("\n".join([f"file '{p}'" for p in normalized]).encode("utf-8"))
        listfile.flush(); listfile.close()

        out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        out_tmp.close()

        ffmpeg = shutil.which("ffmpeg")
        concat_cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", listfile.name,
            "-c", "copy", "-movflags", "+faststart",
            out_tmp.name
        ]
        _run(concat_cmd)

        # 4) Return bytes
        data = io.BytesIO(Path(out_tmp.name).read_bytes())
        data.seek(0)
        return data
    finally:
        # cleanup
        for p in temp_sources:
            Path(p).unlink(missing_ok=True)
        for p in normalized:
            Path(p).unlink(missing_ok=True)
        try:
            Path(listfile.name).unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass
        try:
            Path(out_tmp.name).unlink(missing_ok=True)  # type: ignore
        except Exception:
            pass

# ----------------- App flow -----------------
if uploaded_files:
    media_type = detect_type(uploaded_files)
    st.write(f"Detected media type: {media_type}")

    # Hints if system requirements are missing
    if media_type in ("audio", "video") and not have_ffmpeg():
        st.error("`ffmpeg` is required. Install with: `sudo apt-get install -y ffmpeg`.")
    elif media_type == "mixed":
        st.error("Please upload only one type of media at a time.")
    elif st.button("Combine"):
        try:
            with st.spinner("Combining..."):
                if media_type == "document":
                    result = combine_documents(uploaded_files)
                    st.download_button("Download PDF", data=result, file_name="combined.pdf",
                                       mime="application/pdf")
                elif media_type == "audio":
                    result = combine_audio(uploaded_files)
                    st.audio(result)
                    st.download_button("Download Audio", data=result, file_name="combined.mp3",
                                       mime="audio/mpeg")
                elif media_type == "video":
                    result = combine_video_ffmpeg(uploaded_files)
                    st.video(result)
                    st.download_button("Download Video", data=result, file_name="combined.mp4",
                                       mime="video/mp4")
        except Exception as e:
            st.error(f"Error while combining files: {e}")
else:
    st.info("Upload files to begin.")
