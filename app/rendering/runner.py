"""Own one subprocess at a time. Cancellation never looks up/kills another PID."""
import os
from pathlib import Path
import subprocess
from threading import Event,RLock
import time
from app.rendering.models import RenderError
from app.rendering.tools import nvenc_initialization_failure


class ProcessRunner:
    def __init__(self,event=None):
        self.event=event or Event();self.lock=RLock();self.process=None;self.commands=[]

    def cancel(self):
        self.event.set()
        with self.lock:
            child=self.process
            if child and child.poll() is None:
                try:child.terminate()
                except OSError:pass
        if child and child.poll() is None:
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:child.kill();child.wait(timeout=3)
                except (OSError,subprocess.TimeoutExpired):pass

    def run(self,arguments,cwd,callback=lambda seconds:None,*,encoder=''):
        if self.event.is_set():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
        # Stderr stays in a job-owned temp file and is NEVER copied to safe logs/API.
        error_path=Path(cwd)/'stderr.tmp'
        self.commands.append(list(arguments))
        try:
            with error_path.open('w+b') as errors:
                with self.lock:
                    if self.event.is_set():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
                    self.process=subprocess.Popen(arguments,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,
                        text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    child=self.process
                seconds=0.0
                try:
                    for line in child.stdout:
                        if self.event.is_set():self.cancel()
                        key,_,value=line.strip().partition('=')
                        if key in ('out_time_us','out_time_ms'):
                            try:seconds=max(seconds,int(value)/1_000_000);callback(seconds)
                            except ValueError:pass
                    child.wait()
                finally:
                    child.stdout.close()
                    if child.poll() is None:
                        child.terminate()
                        try:child.wait(timeout=3)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                    with self.lock:self.process=None
                if self.event.is_set():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
                if child.returncode:
                    errors.seek(0);details=errors.read(65536).decode('utf-8','replace')
                    if encoder=='h264_nvenc' and nvenc_initialization_failure(details):
                        raise RenderError('nvenc_failed','NVIDIA NVENC başlatılamadı. GPU sürücüsünü kontrol edin veya CPU seçin.')
                    raise RenderError('render_failed','FFmpeg video oluşturamadı. Yerel medya dosyalarını, boş alanı ve render günlüğündeki güvenli tanıyı kontrol edin.')
                return seconds
        except OSError:
            raise RenderError('local_storage','FFmpeg veya geçici render dosyası açılamadı. Yazma iznini ve boş alanı kontrol edin.',503) from None
        finally:error_path.unlink(missing_ok=True)
