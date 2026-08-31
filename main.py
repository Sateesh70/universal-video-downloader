import os
import tempfile
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI(title="Social Media Video & Audio Downloader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = os.path.join(tempfile.gettempdir(), "downloader_media")
os.makedirs(TEMP_DIR, exist_ok=True)

class VideoRequest(BaseModel):
    url: str

def remove_file(path: str):
    """Cleanup temporary file after download completes"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

@app.post("/api/extract")
def extract_media(req: VideoRequest):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
            if 'entries' in info and info['entries']:
                info = info['entries'][0]

            platform = info.get('extractor_key', 'Social Media')
            title = info.get('title') or f"{platform}_Media"
            thumbnail = info.get('thumbnail')
            
            return {
                "platform": platform,
                "title": title,
                "thumbnail": thumbnail,
                "url": req.url
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download")
def download_media(url: str, format_type: str = "mp4", background_tasks: BackgroundTasks = None):
    """
    Downloads and converts media:
    - format_type="mp4": Merges best video and audio to MP4.
    - format_type="mp3": Extracts audio and converts to 192kbps MP3 via FFmpeg.
    """
    file_id = str(uuid.uuid4())[:8]
    output_template = os.path.join(TEMP_DIR, f"{file_id}.%(ext)s")
    
    if format_type == "mp3":
        ydl_opts = {
            'outtmpl': output_template,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        target_ext = "mp3"
        media_type = "audio/mpeg"
    else:
        ydl_opts = {
            'outtmpl': output_template,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        target_ext = "mp4"
        media_type = "video/mp4"

    ydl_opts['http_headers'] = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if 'entries' in info and info['entries']:
                info = info['entries'][0]

            final_file = os.path.join(TEMP_DIR, f"{file_id}.{target_ext}")
            
            # Fallback search if extension modified during postprocessing
            if not os.path.exists(final_file):
                for f in os.listdir(TEMP_DIR):
                    if f.startswith(file_id):
                        final_file = os.path.join(TEMP_DIR, f)
                        break

            if not os.path.exists(final_file):
                raise HTTPException(status_code=500, detail="Failed to process requested media format.")

            safe_title = "".join([c if c.isalnum() or c in "._- " else "_" for c in (info.get('title') or 'media')])[:40]
            download_filename = f"{safe_title}.{target_ext}"

            if background_tasks:
                background_tasks.add_task(remove_file, final_file)

            return FileResponse(
                path=final_file,
                filename=download_filename,
                media_type=media_type
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")