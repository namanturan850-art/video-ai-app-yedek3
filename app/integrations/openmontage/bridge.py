import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4
from app.projects import linked
from app.rendering.models import RenderError
from app.rendering.runner import ProcessRunner
from app.integrations.openmontage.frames_process import FramesError

PIN='9327439db69021ab4b0e2776729bf3b58fdb5a87'
OFFICIAL='https://github.com/calesthio/OpenMontage.git'
MESSAGE='OpenMontage ana montaj motoru olarak seçildi ancak kurulmamış. INSTALL_OPENMONTAGE.bat ile kurulumu tamamlayın veya Yerel Adaptif motorunu seçin.'
WORKER=Path(__file__).with_name('worker.py')


def trusted_root(value):
    if not isinstance(value,str) or not value or value.startswith(('\\\\','//')) or '://' in value:raise RenderError('openmontage_path','Güvenli, yerel bir OpenMontage klasörü seçin.',422)
    p=Path(value)
    if not p.is_absolute() or any(linked(q) for q in (p,*p.parents)):raise RenderError('openmontage_path','OpenMontage klasörü yerel olmalı ve dış konuma bağlanmamalı.',422)
    if os.name=='nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(p.anchor)==4:raise RenderError('openmontage_path','Ağ sürücüsündeki OpenMontage kullanılamaz.',422)
    return p.resolve()


def child_env(root,keys=None):
    names=('PATH','SystemRoot','WINDIR','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','HOME','LANG')
    env={n:os.environ[n] for n in names if n in os.environ}
    env.update(PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1')
    env.update(keys or {})
    return env


class Bridge:
    def __init__(self,projects,settings):
        self.projects,self.settings=projects,settings;self.cache=None;self.cache_time=0
        self.config_file=projects.storage/'openmontage.json'
        self.semantic_error=False
        from app.integrations.openmontage.frames_process import FramesProcess
        self.frames = FramesProcess()

    def close(self):
        self.frames.close()

    def config(self):
        if linked(self.config_file):raise RenderError('openmontage_path','OpenMontage ayar dosyası güvenli değil.',409)
        if not self.config_file.exists():return {'root':'','media_search':False,'reuse_stock_keys':False,'matching':'fast'}
        try:return json.loads(self.config_file.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise RenderError('openmontage_config','OpenMontage ayarları okunamadı; dosyaları silmeden Ayarlar bölümünü kontrol edin.') from None

    def root(self):
        value=self.config().get('root')
        if not value:
            value=str(Path(os.environ['LOCALAPPDATA'])/'AI-Video-Studio'/'external'/'OpenMontage') if os.name=='nt' and os.environ.get('LOCALAPPDATA') else str(self.projects.storage/'external-tools'/'OpenMontage')
        return trusted_root(value)

    def save(self,payload):
        if not isinstance(payload,dict) or set(payload)-{'root','media_search','reuse_stock_keys','matching','visual_analysis'}:raise RenderError('input_invalid','OpenMontage ayarlarını kontrol edin.',422)
        value=self.config()
        if 'root' in payload:
            if not isinstance(payload['root'],str):raise RenderError('input_invalid','Kurulum klasörü geçersiz.',422)
            if payload['root']:trusted_root(payload['root'])
        for name in ('media_search','reuse_stock_keys','visual_analysis'):
            if name in payload and type(payload[name]) is not bool:raise RenderError('input_invalid','OpenMontage seçimlerini kontrol edin.',422)
        if 'matching' in payload and payload['matching'] not in ('fast','semantic'):raise RenderError('input_invalid','Hızlı veya Semantik eşleştirme seçin.',422)
        value.update(payload);temp=self.config_file.with_name('.openmontage-'+uuid4().hex)
        self.settings_guard(value)
        try:
            with temp.open('x',encoding='utf-8') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.config_file)
        finally:temp.unlink(missing_ok=True)
        self.cache=None;return self.status(True)

    @staticmethod
    def _run(args,cwd):
        return subprocess.run(args,cwd=cwd,shell=False,env=child_env(cwd),stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)

    def status(self,refresh=False):
        if self.cache and not refresh and time.monotonic()-self.cache_time<30:return dict(self.cache)
        cfg=self.config();r={'ready':False,'status':'Kurulu değil','message':MESSAGE,'commit':'','semantic_ready':False,'sources':[],
                           'media_search':cfg.get('media_search',False),'reuse_stock_keys':cfg.get('reuse_stock_keys',False),'matching':cfg.get('matching','fast'),'custom_path':bool(cfg.get('root')),
                           'visual_analysis':cfg.get('visual_analysis',False),'semantic_status':'Hata' if self.semantic_error else 'Kurulum gerekli','semantic_model_version':''}
        try:
            root=self.root()
            if root.exists():
                r['status']='Kurulum gerekli'
                git=shutil.which('git')
                if not git:raise ValueError()
                head=self._run([git,'rev-parse','HEAD'],root)
                origin=self._run([git,'remote','get-url','origin'],root)
                if head.returncode or head.stdout.strip()!=PIN or origin.stdout.strip().removesuffix('.git')!=OFFICIAL.removesuffix('.git'):
                    r['message']='OpenMontage sürümü doğrulanamadı. INSTALL_OPENMONTAGE.bat ile sabitlenmiş kurulumu tamamlayın.';raise ValueError()
                dirty=self._run([git,'diff','--quiet',PIN,'--'],root)
                if dirty.returncode:r['message']='OpenMontage kaynak dosyaları değişmiş. Doğrulanmış ayrı kurulumu kullanın.';raise ValueError()
                python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
                cli=root/'remotion-composer'/'node_modules'/'@remotion'/'cli'/'remotion-cli.js'
                if not python.is_file() or not cli.is_file() or not shutil.which('node'):raise ValueError()
                if not python.resolve().is_relative_to(root) or not cli.resolve().is_relative_to(root):raise ValueError()
                doctor=self._run([str(python),str(WORKER),str(root),'doctor'],root)
                d=json.loads(doctor.stdout)
                if doctor.returncode or not d.get('success'):raise ValueError()
                r.update(ready=True,status='Hazır',message='Ayrı yerel OpenMontage motoru hazır.',commit=PIN[:7],semantic_ready=bool(d.get('semantic_ready')),sources=d.get('sources',[]))
                r.update(semantic_model_version=d.get('semantic_model_version',''),semantic_status='Hata' if self.semantic_error else 'Hazır' if d.get('semantic_ready') else 'Kurulum gerekli')
        except (OSError,ValueError,KeyError,subprocess.SubprocessError,RenderError):pass
        self.cache,self.cache_time=dict(r),time.monotonic();return r

    def call(self,operation,inputs,folder,runner=None,progress=lambda fraction:None):
        status=self.status()
        if not status['ready']:raise RenderError('openmontage_unavailable',status['message'])
        root=self.root();folder=Path(folder).resolve();request=folder/('om-input-'+uuid4().hex+'.json');response=folder/('om-result-'+uuid4().hex+'.json')
        # Never put secrets into the interchange, argv, diagnostics or files.
        self.settings_guard(inputs)
        request.write_text(json.dumps({'operation':operation,'inputs':inputs,'result_path':str(response)},ensure_ascii=False),encoding='utf-8')
        env=child_env(root)
        from app.rendering.tools import discover
        tool=discover()
        if tool.get('ffmpeg'):env['PATH']=str(Path(tool['ffmpeg']).parent)+os.pathsep+env.get('PATH','')
        if operation in ('search','semantic') and self.config().get('reuse_stock_keys'):
            for name,var in (('pexels','PEXELS_API_KEY'),('pixabay','PIXABAY_API_KEY')):
                key=self.settings.stock_config(name).get('api_key')
                if key:env[var]=key
        python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        try:
            args=[str(python),str(WORKER),str(root),str(request)]
            if operation == 'frames':
                result=self.frames.call([str(python),str(WORKER),str(root),'--serve-frames'],root,env,inputs)
                self.settings_guard(result)
                return result.get('data', {})
            if operation == 'visual':
                # Bounded model inference; raw output never reaches diagnostics.
                checked=subprocess.run(args,cwd=folder,shell=False,env=env,stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180 if operation=='visual' else 120)
                if checked.returncode:raise ValueError()
            else:(runner or ProcessRunner()).run(args,folder,callback=progress,phase='openmontage',env=env)
            if linked(response) or response.stat().st_size>2_000_000:raise ValueError()
            result=json.loads(response.read_text(encoding='utf-8'));self.settings_guard(result)
            if result.get('success') is not True:raise ValueError()
            return result.get('data',{})
        except FramesError as error:
            # CLIP side process: keep the real technical cause for the diagnostics file (never a secret).
            from app.scripts.engine import SecretGuard
            detail=SecretGuard(self.settings.secret_values()).clean(error.detail)
            raise RenderError('openmontage_failed',f'CLIP süreci çalışmadı ({error.reason}): {detail}'.strip()) from None
        except RenderError as error:
            if error.category=='render_cancelled':raise
            raise RenderError('openmontage_failed','OpenMontage kullanılamadı. Yerel Adaptif motorunu seçerek tekrar deneyin; önceki video korundu.') from None
        except (OSError,ValueError,TypeError,subprocess.SubprocessError):raise RenderError('openmontage_failed','OpenMontage kullanılamadı. Yerel Adaptif motorunu seçerek tekrar deneyin; önceki video korundu.') from None
        finally:request.unlink(missing_ok=True);response.unlink(missing_ok=True)

    def settings_guard(self,value):
        from app.scripts.engine import SecretGuard
        SecretGuard(self.settings.secret_values()).validate(value)
