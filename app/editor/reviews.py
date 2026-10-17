"""Read-only Gemini evidence and local, version-scoped finding dispositions."""
from contextlib import closing
import json
from uuid import uuid4

from app.editor.models import EditorError
from app.editor.service import VIDEO_REVIEW_VERSION
from app.projects import now


class Reviews:
    def __init__(self,editor):self.editor=editor;self.projects=editor.projects

    def get(self,pid):
        with closing(self.projects._connection()) as c:
            self.projects._row(c,pid)
            rows=c.execute('SELECT sha256,result_json FROM archive_analysis_cache WHERE project_id=? AND analyzer_version=? ORDER BY rowid DESC',(pid,VIDEO_REVIEW_VERSION)).fetchall()
            events=c.execute("SELECT payload_json FROM editorial_events WHERE project_id=? AND kind='review_finding' ORDER BY id",(pid,)).fetchall()
        statuses={}
        for row in events:
            item=json.loads(row[0]);statuses[(item['render_version_id'],item['finding_id'])]=item['status']
        reports=[]
        for row in rows:
            report=json.loads(row['result_json']);report['source_sha256']=row['sha256']
            for index,issue in enumerate(report['issues']):
                issue['id']=str(index);issue['status']=statuses.get((report['render_version_id'],str(index)),'open')
                issue.setdefault('confidence','Belirtilmedi');issue.setdefault('basis',report['basis'])
            reports.append(report)
        return {'analysis_scope':'sample_frames','max_frames':8,'max_output_tokens':900,'reports':reports,
                'notice':'Yalnız örnek kareler incelenir. Ses seviyesi ve tarih/coğrafya bulguları ölçüm veya bağımsız doğrulama olmadan kesin değildir. Tam video gönderimi etkin değildir.',
                'cost_notice':'Gemini sağlayıcı/model kotası kullanılır; kesin ücret burada hesaplanamaz. En fazla 8 küçük kare ve 900 çıktı tokeni. Açık veri paylaşımı ve maliyet onayı gereklidir.'}

    def request(self,pid,payload):
        if set(payload)!={'confirmed','data_sharing_confirmed','cost_confirmed'} or any(payload[k] is not True for k in payload):
            raise EditorError('confirmation_required','Örnek kare paylaşımı ve olası maliyeti ayrı ayrı onaylayın.')
        return self.editor.video_review(pid,{'confirm':True})

    def status(self,pid,rid,fid,payload):
        if set(payload)!={'status'} or payload['status'] not in ('open','ignored','resolved'):raise EditorError('invalid_status','Bulgu durumu geçersiz.')
        reports=self.get(pid)['reports']
        report=next((r for r in reports if r['render_version_id']==rid),None)
        if not report or not any(i['id']==fid for i in report['issues']):raise EditorError('review_missing','Bu projeye ait video bulgusu bulunamadı.',404)
        plan=self.editor._active(pid)
        with closing(self.projects._connection()) as c,c:
            c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',
                      (pid,plan['plan_id'],'review_finding',json.dumps({'render_version_id':rid,'finding_id':fid,'status':payload['status']}),now()))
        return self.get(pid)
