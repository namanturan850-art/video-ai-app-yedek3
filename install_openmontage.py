"""Explicit, isolated optional installer. Never invoked by the normal launcher."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

class InstallerError(ValueError):
    pass


PIN='9327439db69021ab4b0e2776729bf3b58fdb5a87'
OFFICIAL='https://github.com/calesthio/OpenMontage.git'


def environment():
    names=('PATH','SystemRoot','WINDIR','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','HOME')
    return {**{n:os.environ[n] for n in names if n in os.environ},'PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1'}


def run(args,cwd=None,timeout=1800):
    # Dependency output can contain external URLs. Keep it out of UI/log files.
    r=subprocess.run(args,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                     encoding='utf-8',errors='replace',timeout=timeout,env=environment())
    if r.returncode:raise InstallerError('Kurulum adımı tamamlanamadı. İnterneti ve boş alanı kontrol edip bu dosyayı yeniden açın.')
    return r.stdout


def validate_root(root):
    if not root.is_absolute() or str(root).startswith(('\\\\','//')):raise InstallerError('Yerel kurulum klasörü gerekli.')
    for p in (root,*root.parents):
        if p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&0x400):raise InstallerError('Bağlantılı kurulum klasörü kullanılamaz.')
    if os.name=='nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(root.anchor)==4:raise InstallerError('Ağ sürücüsü kullanılamaz.')
    return root.resolve()


def target():
    default=Path(os.environ.get('LOCALAPPDATA',str(Path(__file__).parent/'data')))/'AI-Video-Studio'/'external'/'OpenMontage'
    cfg=Path(__file__).parent/'data'/'openmontage.json'
    if cfg.exists():
        value=json.loads(cfg.read_text(encoding='utf-8')).get('root')
        if value:default=Path(value)
    return validate_root(default)


def dependencies():
    if sys.version_info<(3,10):raise InstallerError('Python 3.10 veya yenisi gerekli: python.org')
    git=shutil.which('git');node=shutil.which('node');npm=shutil.which('npm')
    if not git:raise InstallerError('Git eksik. git-scm.com adresinden Git for Windows kurun ve tekrar çift tıklayın.')
    if not node or not npm:raise InstallerError('Node.js eksik. nodejs.org adresinden LTS kurun ve tekrar çift tıklayın.')
    version=run([node,'--version'],timeout=15)
    if not re.match(r'^v(\d+)',version) or int(version[1:].split('.')[0])<18:raise InstallerError('Node.js 18 veya yenisi gerekli: nodejs.org')
    npm_cli=Path(node).resolve().parent/'node_modules/npm/bin/npm-cli.js'
    if not npm_cli.is_file():npm_cli=Path(npm).resolve()
    if not npm_cli.is_file() or npm_cli.suffix.lower()!='.js':raise InstallerError('Node.js npm kurulumu doğrulanamadı. Node.js LTS kurulumunu onarın.')
    candidates=[shutil.which('ffmpeg')]
    if os.environ.get('LOCALAPPDATA'):candidates.append(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Links/ffmpeg.exe')
    ffmpeg=next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)
    if not ffmpeg or not run([ffmpeg,'-version'],timeout=15).startswith('ffmpeg version '):raise InstallerError('FFmpeg gerekli. Önce uygulamanın Ayarlar → FFmpeg bölümünde bulunduğunu kontrol edin.')
    return git,node,str(npm_cli),ffmpeg


def install(root,git,node,npm):
    root=validate_root(root);root.parent.mkdir(parents=True,exist_ok=True)
    if root.exists():
        origin=run([git,'remote','get-url','origin'],root,15).strip()
        if origin.removesuffix('.git')!=OFFICIAL.removesuffix('.git'):raise InstallerError('Bu klasör resmi OpenMontage kurulumu değil. Ayarlar bölümünde ayrı boş bir klasör seçin.')
        if run([git,'status','--porcelain','--untracked-files=no'],root,15).strip():raise InstallerError('OpenMontage kaynakları değiştirilmiş. Mevcut dosyalar silinmedi; ayrı boş bir klasör seçin.')
    else:
        print('1/5 Resmi OpenMontage ayrı klasöre indiriliyor…')
        run([git,'clone','--no-checkout',OFFICIAL,str(root)],timeout=600)
    print('2/5 İncelenen sürüm sabitleniyor…')
    run([git,'fetch','origin',PIN],root,600);run([git,'checkout','--detach',PIN],root,60)
    print('3/5 Ayrı Python ortamı hazırlanıyor…')
    run([sys.executable,'-m','venv','--copies',str(root/'.venv')],timeout=120)
    python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],root)
    print('4/5 Remotion hazırlanıyor…')
    run([node,npm,'ci','--ignore-scripts','--no-audit','--no-fund','--cache',str(root/'.npm-cache')],root/'remotion-composer')
    cli=root/'remotion-composer/node_modules/@remotion/cli/remotion-cli.js'
    run([node,str(cli),'versions'],root/'remotion-composer',30)
    print('5/5 Yerel render tarayıcısı hazırlanıyor…')
    run([node,str(cli),'browser','ensure'],root/'remotion-composer',600)
    if input('İsteğe bağlı büyük CLIP/semantik paketleri de kurulsun mu? (E/H; varsayılan H): ').strip().lower()=='e':
        run([str(python),'-m','pip','install','torch','transformers','opencv-python-headless'],root)


def main():
    print('OpenMontage isteğe bağlı harici motordur (GNU AGPL v3).')
    print('Resmi kaynak: '+OFFICIAL+'\nSabit sürüm: '+PIN)
    print('Ayrı Python/Node bağımlılıkları ve render tarayıcısı indirilir. Uygulamanın ortamı değişmez.')
    print('Remotion kendi lisans koşullarına tabidir: https://www.remotion.dev/docs/license')
    if input('Bu isteğe bağlı kurulumu başlatmak istiyor musunuz? (E/H): ').strip().lower()!='e':
        print('Kurulum yapılmadı. Yerel Adaptif motoru kullanılabilir.');return 0
    try:
        git,node,npm,ffmpeg=dependencies();root=target()
        # Canonical WinGet FFmpeg may be outside an older launcher's PATH.
        os.environ['PATH']=str(Path(ffmpeg).parent)+os.pathsep+os.environ.get('PATH','')
        install(root,git,node,npm)
        print('Kurulum tamamlandı. Uygulamada Ayarlar → OpenMontage → Durumu Yenile düğmesine basın.');return 0
    except InstallerError as e:
        print(str(e));return 1
    except (OSError,ValueError,subprocess.SubprocessError):
        print('Kurulum tamamlanamadı. Git, Node.js LTS, Python ve FFmpeg kurulumlarını; interneti ve boş alanı kontrol edin.')
        print('Mevcut projeler ve uygulama ortamı korunur. INSTALL_OPENMONTAGE.bat dosyasını tekrar açabilirsiniz.');return 1


if __name__=='__main__':sys.exit(main())
