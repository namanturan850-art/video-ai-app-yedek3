import json
import math
import subprocess
from app.rendering.models import RenderError


def metadata(probe,path):
    if not probe:return None
    try:
        result=subprocess.run([probe,'-v','error','-show_streams','-show_format','-of','json',str(path)],shell=False,
                              stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        if result.returncode or len(result.stdout)>2_000_000:raise ValueError()
        value=json.loads(result.stdout)
        if not isinstance(value,dict) or not isinstance(value.get('streams'),list):raise ValueError()
        return value
    except (OSError,ValueError,subprocess.SubprocessError):
        raise RenderError('input_invalid','Yerel medya dosyası okunamadı veya geçersiz. Dosyayı değiştirmeden kontrol edin.') from None


def validate(probe,path,duration):
    if not path.is_file() or path.stat().st_size<512:raise RenderError('output_invalid','Oluşan video eksik veya boş; önceki video korundu.')
    with path.open('rb') as stream:
        if stream.read(12)[4:8]!=b'ftyp':raise RenderError('output_invalid','Oluşan MP4 doğrulanamadı; önceki video korundu.')
    if not probe:return None
    try:
        data=metadata(probe,path)
        video=next(s for s in data['streams'] if s.get('codec_type')=='video')
        audio=next(s for s in data['streams'] if s.get('codec_type')=='audio')
        value=float(data['format']['duration']);a,b=video['avg_frame_rate'].split('/');fps=float(a)/float(b)
        if (not math.isfinite(value) or value<=0 or abs(value-duration)>.04
                or video.get('width')!=1920 or video.get('height')!=1080 or video.get('codec_name')!='h264'
                or video.get('pix_fmt')!='yuv420p' or abs(fps-30)>.001
                or audio.get('codec_name')!='aac' or int(audio.get('sample_rate',0))!=48000 or audio.get('channels')!=2):raise ValueError()
        return {'duration':value,'width':1920,'height':1080,'fps':30,'video_codec':'h264','audio_codec':'aac','validation_method':'ffprobe'}
    except (RenderError,KeyError,ValueError,TypeError,StopIteration,ZeroDivisionError):
        raise RenderError('output_invalid','Oluşan video biçimi veya süresi hedefle eşleşmiyor; önceki video aktif kaldı.') from None
