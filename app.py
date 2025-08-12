import streamlit as st
from pathlib import Path
from PIL import Image
from fpdf import FPDF
from PyPDF2 import PdfMerger
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, concatenate_videoclips
import tempfile
import io

st.set_page_config(page_title="th3 c0ncat3nat0r", page_icon="🔗")

st.title("th3 c0ncat3nat0r")
st.write("Combine multiple media files into a single output.")

uploaded_files = st.file_uploader("Upload files", accept_multiple_files=True)


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
            pdf.set_font("Arial", size=12)
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
        t.close()
        Path(t.name).unlink(missing_ok=True)
    output.seek(0)
    return output


def combine_audio(files):
    combined = None
    for f in files:
        segment = AudioSegment.from_file(f)
        combined = segment if combined is None else combined + segment
    output = io.BytesIO()
    combined.export(output, format="mp3")
    output.seek(0)
    return output


def combine_video(files):
    clips = []
    temp_paths = []
    for f in files:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix)
        tmp.write(f.read())
        tmp.flush()
        temp_paths.append(tmp.name)
        clips.append(VideoFileClip(tmp.name))
    final_clip = concatenate_videoclips(clips, method="compose")
    out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    final_clip.write_videofile(out_tmp.name, logger=None)
    for clip in clips:
        clip.close()
    final_clip.close()
    for p in temp_paths:
        Path(p).unlink(missing_ok=True)
    output = io.BytesIO(Path(out_tmp.name).read_bytes())
    Path(out_tmp.name).unlink(missing_ok=True)
    output.seek(0)
    return output

if uploaded_files:
    media_type = detect_type(uploaded_files)
    st.write(f"Detected media type: {media_type}")
    if media_type == "mixed":
        st.error("Please upload only one type of media at a time.")
    elif st.button("Combine"):
        try:
            if media_type == "document":
                result = combine_documents(uploaded_files)
                st.download_button("Download PDF", data=result, file_name="combined.pdf", mime="application/pdf")
            elif media_type == "audio":
                result = combine_audio(uploaded_files)
                st.audio(result)
                st.download_button("Download Audio", data=result, file_name="combined.mp3", mime="audio/mpeg")
            elif media_type == "video":
                result = combine_video(uploaded_files)
                st.video(result)
                st.download_button("Download Video", data=result, file_name="combined.mp4", mime="video/mp4")
        except Exception as e:
            st.error(f"Error while combining files: {e}")
else:
    st.info("Upload files to begin.")
