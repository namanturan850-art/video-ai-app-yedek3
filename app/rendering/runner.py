"""Own one subprocess at a time. Cancellation never looks up/kills another PID."""
import os
from pathlib import Path
import subprocess
import signal
from threading import Event,RLock,Thread
import time
from app.rendering.models import RenderError
from app.rendering.diagnostics import classify,diagnostic


class ProcessRunner:
    def __init__(self,event=None,*,diagnostic_callback=lambda value:None,stall_seconds=300):
        self.event=event or Event();self.lock=RLock();self.process=None;self.commands=[]
        self.diagnostic_callback=diagnostic_callback;self.process_tree=False
        self.parent=None;self.children=[]
        self.stall_seconds=stall_seconds

    def spawn(self):
        """Independent runner for one parallel piece: own process, shared command log,
        cancelled together with this runner (its own cancel never touches the parent)."""
        child=ProcessRunner(diagnostic_callback=lambda value:self.diagnostic_callback(value),stall_seconds=self.stall_seconds)
        child.parent=self;child.commands=self.commands
        with self.lock:self.children.append(child)
        return child

    def cancelled(self):
        return self.event.is_set() or (self.parent is not None and self.parent.cancelled())

    def _stop(self,child,force=False):
        # An external renderer owns Python -> Node -> browser/FFmpeg children.
        # Target ONLY the still-live process we created, never a name or glob.
        if self.process_tree:
            if os.name=='nt' and child.poll() is None:
                executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'taskkill.exe'
                try:subprocess.run([str(executable),'/PID',str(child.pid),'/T','/F'],shell=False,stdin=subprocess.DEVNULL,capture_output=True,timeout=5)
                except (OSError,subprocess.SubprocessError):pass
            elif os.name!='nt':
                try:os.killpg(child.pid,signal.SIGKILL if force else signal.SIGTERM)
                except (OSError,ProcessLookupError):pass
        if child.poll() is None:
            try:child.kill() if force else child.terminate()
            except OSError:pass

    def cancel(self):
        self.event.set()
        for piece in list(self.children):piece.cancel()
        with self.lock:
            child=self.process
            if child and child.poll() is None:
                self._stop(child)
        if child and child.poll() is None:
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:self._stop(child,True);child.wait(timeout=3)
                except (OSError,subprocess.TimeoutExpired):pass

    def run(self,arguments,cwd,callback=lambda seconds:None,*,encoder='',phase='ffmpeg',slot_index=None,slot_id=None,media_type=None,slot_count=None,env=None):
        if self.cancelled():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
        # Stderr stays in a job-owned temp file and is NEVER copied to safe logs/API.
        error_path=Path(cwd)/('stderr.tmp' if self.parent is None else f'stderr-{id(self)}.tmp')  # parallel pieces share one folder
        self.commands.append(list(arguments))
        finished=Event();watchdog=None;activity={'at':time.monotonic(),'stalled':False}
        try:
            with error_path.open('w+b') as errors:
                with self.lock:
                    if self.cancelled():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
                    self.process_tree=phase=='openmontage'
                    self.process=subprocess.Popen(arguments,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,env=env,
                        start_new_session=self.process_tree and os.name!='nt',
                        text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    child=self.process
                def watch():
                    while not finished.wait(min(1.,self.stall_seconds/4)):
                        if child.poll() is not None:return
                        if self.cancelled():self._stop(child,True);return
                        if time.monotonic()-activity['at']>self.stall_seconds:
                            activity['stalled']=True;self._stop(child,True);return
                watchdog=Thread(target=watch,daemon=True,name='render-watchdog');watchdog.start()
                seconds=0.0
                try:
                    for line in child.stdout:
                        if self.cancelled():self.cancel()
                        key,_,value=line.strip().partition('=')
                        if key in ('out_time_us','out_time_ms'):
                            try:
                                current=int(value)/1_000_000
                                if current>seconds:activity['at']=time.monotonic()
                                seconds=max(seconds,current);callback(seconds)
                            except ValueError:pass
                    child.wait()
                finally:
                    child.stdout.close()
                    if child.poll() is None:
                        self._stop(child)
                        try:child.wait(timeout=3)
                        except subprocess.TimeoutExpired:self._stop(child,True);child.wait()
                    with self.lock:self.process=None;self.process_tree=False
                if self.cancelled():raise RenderError('render_cancelled','Render iptal edildi; kaynak dosyalar korunuyor.')
                if activity['stalled']:raise RenderError('render_stalled','Render ilerleme göstermediği için durduruldu. Kaynaklar korundu; yeniden deneyin.')
                if child.returncode:
                    errors.seek(0);details=errors.read(65536).decode('utf-8','replace')
                    code=classify(details,encoder=encoder,phase=phase)
                    safe=diagnostic(code,phase=phase,encoder=encoder,slot_index=slot_index,slot_id=slot_id,media_type=media_type,slot_count=slot_count,return_code=child.returncode)
                    self.diagnostic_callback(safe)
                    raise RenderError('nvenc_failed' if code=='nvenc_failed' else 'render_failed',safe['safe_error_summary'],diagnostic=safe)
                return seconds
        except OSError:
            safe=diagnostic('unknown_ffmpeg_error',phase=phase,encoder=encoder,slot_index=slot_index,slot_id=slot_id,media_type=media_type,slot_count=slot_count)
            raise RenderError('local_storage','FFmpeg veya geçici render dosyası açılamadı. Yazma iznini ve boş alanı kontrol edin.',503,diagnostic=safe) from None
        finally:
            finished.set()
            if watchdog:watchdog.join(2)
            error_path.unlink(missing_ok=True)
