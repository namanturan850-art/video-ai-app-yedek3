"""Disposable Windows diagnostics. No user projects, providers or long render.

Default checks Windows/Python/FFmpeg and a 0.2 s CPU encode. --webview2 adds
native window checks on a disposable Spanish fixture. --nvenc explicitly
tries 0.2 s on installed hardware; encoder listing alone is not a pass.
"""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--webview2',action='store_true');parser.add_argument('--nvenc',action='store_true');parser.add_argument('--output',default='windows-editor-report.json');args=parser.parse_args()
    report={'platform':platform.platform(),'python':platform.python_version(),'windows':platform.system()=='Windows',
            'webview2':'not_run','nvenc':'not_run','openmontage_remotion':'not_run','native_file_picker':'manual_required','audio_device':'manual_required','os_dpi_125_150':'manual_required'}
    if not report['windows']:
        report['status']='unsupported_environment';Path(args.output).write_text(json.dumps(report,indent=2));print(json.dumps(report));return 2
    ffmpeg=shutil.which('ffmpeg');report['ffmpeg']=bool(ffmpeg);ok=bool(ffmpeg)
    with tempfile.TemporaryDirectory(prefix='naman-windows-check-') as scratch:
        if ffmpeg:
            for encoder in ['libx264']+(['h264_nvenc'] if args.nvenc else []):
                output=Path(scratch)/f'{encoder}.mp4'
                try:
                    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i','color=c=blue:s=1920x1080:r=30:d=0.2','-c:v',encoder,'-threads','1','-frames:v','6',str(output)],check=True,capture_output=True,timeout=30)
                    subprocess.run([ffmpeg,'-v','error','-i',str(output),'-f','null','-'],check=True,capture_output=True,timeout=15)
                    report['cpu_encode' if encoder=='libx264' else 'nvenc']='passed'
                except (OSError,subprocess.SubprocessError):
                    report['cpu_encode' if encoder=='libx264' else 'nvenc']='failed_or_unavailable';ok=False
        if args.webview2:
            try:
                sys.path.insert(0,str(ROOT/'tests'))
                from test_manual_first import install_manual_example
                from app.main import create_app
                from fastapi.testclient import TestClient
                storage=Path(scratch)/'data'
                with TestClient(create_app(storage)) as client:pid=install_manual_example(client.app)['pid']
                result=subprocess.run([sys.executable,str(ROOT/'scripts/webview2_editor_smoke.py'),pid,str(storage)],capture_output=True,text=True,encoding='utf-8',timeout=150,cwd=ROOT)
                report['webview2']='passed' if result.returncode==0 else 'failed'
                report['webview2_result']=result.stdout[-12000:];ok=ok and result.returncode==0
            except (ImportError,OSError,subprocess.SubprocessError):report['webview2']='failed_or_unavailable';ok=False
    report['status']='passed_accessible_checks' if ok else 'failed';Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())
