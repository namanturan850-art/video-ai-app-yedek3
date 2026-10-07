"""Windows-reported paths with real adapters/mocked HTTP. Owner must test live."""
from contextlib import closing
import json
import sqlite3
import ssl

import httpx
import pytest

from test_provider_diagnostics import diagnostic, check, install_transport, KEY, OTHER_KEY, MODEL, NARRATION
from test_scripts import studio, run
from app.providers.base import ScriptProviderError
from app.providers.text_api import OllamaScriptProvider
from app.scripts.models import word_count
from app.scripts.review import SHORT_WARNING, CORRECTION_WARNING

PRIVATE = 'PRIVATE_REASONING_NEVER_DISPLAY_OR_SAVE'
RAW_REVIEW = "Der im 'blueprint' definierte Titel und die Struktur des Abschnitts. Der Tonfall ist passend."


def candidate(parts=None, reason='STOP', content=None):
    return {'candidates':[{'finishReason':reason,'content':content if content is not None else {'parts':parts if parts is not None else [{'text':'TEST_OK'}]}}]}


@pytest.mark.parametrize('body,category,stage', [
    ({'promptFeedback':{'blockReason':'SAFETY'}},'blocked_response','prompt_feedback'),
    ({'promptFeedback':None},'response_schema_mismatch','prompt_feedback'),
    ({},'no_candidates','candidates'),
    ({'candidates':[]},'no_candidates','candidates'),
    ({'candidates':None},'response_schema_mismatch','candidates'),
    ({'candidates':[None]},'malformed_candidate','candidates'),
    ({'candidates':[PRIVATE]},'malformed_candidate','candidates'),
    (candidate(reason='SAFETY'),'blocked_response','finish_reason'),
    (candidate(reason='MAX_TOKENS'),'output_limit','finish_reason'),
    (candidate(reason=KEY),'unexpected_finish_reason','finish_reason'),
    (candidate(reason=None),'response_schema_mismatch','finish_reason'),
    ({'candidates':[{'finishReason':'STOP','content':None}]},'malformed_content','content'),
    (candidate(content={}), 'malformed_parts','parts'),
    (candidate(content={'parts':None}), 'malformed_parts','parts'),
    (candidate(parts=[]),'empty_response','parts'),
    (candidate(parts=[None]),'malformed_parts','parts'),
    (candidate(parts=[{'text':None}]),'malformed_parts','parts'),
    (candidate(parts=[{'text':'   '}]),'empty_response','text'),
    (candidate(parts=[{'thought':True,'text':PRIVATE + KEY}]),'thought_only_response','text'),
    (candidate(parts=[{'thought':'true','text':PRIVATE}]),'response_schema_mismatch','parts'),
    (candidate(parts=[{'inlineData':{'mimeType':'image/png','data':PRIVATE}}]),'response_schema_mismatch','text'),
    ([], 'response_schema_mismatch','response_json'),
])
def test_gemini_known_response_failures_have_specific_stage_not_generic(diagnostic,body,category,stage,caplog):
    client, _, respond = diagnostic
    check(client,'gemini','settings');check(client,'gemini','connection')
    def faulty(request): return respond(request) if request.method=='GET' else httpx.Response(200,json=body)
    install_transport(client,httpx.MockTransport(faulty));caplog.set_level('INFO')
    view=check(client,'gemini','simple_generation')
    assert view['connection_status']=='Başarılı' and view['settings_status']=='Başarılı'
    assert view['safe_error_category']==category and category!='unexpected_backend'
    assert view['tests']['simple_generation']['stage']==stage
    assert view['tests']['simple_generation']['upstream_http_status']==200
    combined=json.dumps(view)+caplog.text
    for private in (KEY, OTHER_KEY, PRIVATE, 'Authorization', 'Traceback'):assert private not in combined
    assert 'stage='+stage in caplog.text and 'http_status=200' in caplog.text


def test_gemini_settings_connection_success_without_saved_model_no_longer_generic(diagnostic):
    client, calls, _ = diagnostic
    values=client.app.state.settings.store.read();values['gemini']['model']='';client.app.state.settings.store.write(values)
    assert check(client,'gemini','settings')['settings_status']=='Başarılı'
    connection=check(client,'gemini','connection')
    assert connection['connection_status']=='Başarılı' and 'model kaydedilmemiş' in connection['safe_message']
    count=len(calls);view=check(client,'gemini','simple_generation')
    assert view['safe_error_category']=='missing_model' and view['tests']['simple_generation']['stage']=='configuration'
    assert len(calls)==count and view['connection_status']=='Başarılı'


@pytest.mark.parametrize('message,category,status', [
    ('This model does not support generateContent', 'model_unsupported', 'Model uyumsuz'),
    ('Invalid request payload', 'invalid_request', 'Hata'),
])
def test_gemini_400_request_vs_model_failure_preserves_connection(diagnostic,message,category,status):
    client,_,respond=diagnostic
    check(client,'gemini','settings');check(client,'gemini','connection')
    def response(request):
        return respond(request) if request.method=='GET' else httpx.Response(400,json={'error':{'message':message+' '+KEY+PRIVATE}})
    install_transport(client,httpx.MockTransport(response))
    view=check(client,'gemini','simple_generation')
    result=view['tests']['simple_generation']
    assert result['safe_error_category']==category and result['status']==status
    assert result['stage']=='http_status' and result['upstream_http_status']==400
    assert view['connection_status']=='Başarılı' and view['settings_status']=='Başarılı'
    assert KEY not in json.dumps(view) and PRIVATE not in json.dumps(view)


@pytest.mark.parametrize('exception,category', [(httpx.ReadTimeout,'gemini_timeout'),(httpx.ProxyError,'no_internet'),(ssl.SSLError,'network_error'),(RuntimeError,'unexpected_backend')])
def test_gemini_native_exceptions_log_only_class_stage_category(diagnostic,exception,category,caplog):
    client,_,_=diagnostic;check(client,'gemini','settings')
    def fail(request):raise exception(KEY+PRIVATE+' Authorization raw response')
    install_transport(client,httpx.MockTransport(fail));caplog.set_level('INFO')
    view=check(client,'gemini','simple_generation')
    result=view['tests']['simple_generation']
    assert view['safe_error_category']==category
    assert result['exception_class']==exception.__name__ and result['stage']=='http_request'
    for private in (KEY,PRIVATE,'Authorization','raw response'):assert private not in json.dumps(view)+caplog.text
    assert 'exception_class='+exception.__name__ in caplog.text


@pytest.mark.parametrize('kind',['invalid_json','wrong_error_schema','too_deep','huge_retry_header'])
def test_gemini_429_is_always_quota_even_when_error_details_unreadable(diagnostic,kind):
    client,_,_=diagnostic;check(client,'gemini','settings')
    def respond(request):
        content=b'not JSON' if kind=='invalid_json' else b'['*1100+b'0'+b']'*1100 if kind=='too_deep' else b'{"error":[]}'
        return httpx.Response(429,content=content,headers={'Retry-After':'9'*5000 if kind=='huge_retry_header' else '1'})
    install_transport(client,httpx.MockTransport(respond))
    view=check(client,'gemini','simple_generation')
    assert view['simple_generation_status']=='Kota sınırı' and view['safe_error_category']=='quota_limit'
    assert view['tests']['simple_generation']['upstream_http_status']==429


def test_gemini_discards_thought_and_uses_actual_final_response(diagnostic,caplog):
    client,_,_=diagnostic;check(client,'gemini','settings')
    install_transport(client,httpx.MockTransport(lambda request:httpx.Response(200,json=candidate(parts=[{'thought':True,'text':PRIVATE+KEY},{'text':'TEST_OK'}]))))
    caplog.set_level('INFO');view=check(client,'gemini','simple_generation')
    assert view['simple_generation_status']=='Başarılı'
    assert PRIVATE not in json.dumps(view)+caplog.text


@pytest.mark.parametrize('model',['qwen3.5:9b','normal-installed-model'])
@pytest.mark.parametrize('test,text',[('simple_generation','TEST_OK'),('json','```json\n{"status":"ok"}\n```'),('script_pipeline',NARRATION)])
def test_ollama_valid_final_channel_with_thinking_runs_all_diagnostics(diagnostic,model,test,text,caplog):
    client,_,_=diagnostic
    client.app.state.settings.save('ollama',{'model':model});check(client,'ollama','settings')
    def respond(request):
        body=json.loads(request.content)
        assert body['model']==model and body['stream'] is False and body['think'] is False
        assert 'think' not in body.get('options',{}) and body['system']
        return httpx.Response(200,json={'done':True,'response':text,'thinking':PRIVATE+OTHER_KEY})
    install_transport(client,httpx.MockTransport(respond));caplog.set_level('INFO')
    view=check(client,'ollama',test)
    assert view[test+'_status']=='Başarılı'
    assert PRIVATE not in json.dumps(view)+caplog.text


def words(count):return ' '.join('Wort'+str(index) for index in range(1,count+1))


def short_ollama(studio,initial=184,expanded=385,fail_review=False):
    client,project,fake,_=studio
    client.patch('/api/projects/'+project['id'],json={'target_duration_minutes':3,'script_engine':'ollama'})
    original=fake.generate_script;failed=[False]
    def generate(prompt):
        task=prompt.splitlines()[0].removeprefix('TASK: ')
        data=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
        if task=='expand_duration':
            fake.calls.append((task,data,prompt))
            assert data['target_word_min']==375 and data['target_word_max']==435
            assert data['language']=='de' and data['source_text']==words(initial)
            if isinstance(expanded,Exception):raise expanded
            return words(expanded) if isinstance(expanded,int) else expanded
        result=original(prompt)
        if task=='section':return words(initial)
        if task=='review':
            if fail_review and not failed[0]:failed[0]=True;raise ScriptProviderError('safe failed review',category='invalid_response')
            return json.dumps({'consistent':True,'issues':[RAW_REVIEW]})
        return result
    fake.generate_script=generate
    return fake


@pytest.mark.parametrize('expanded',[385,210])
def test_184_word_3_minute_script_corrected_once_metrics_from_final(studio,expanded):
    client,project,_,data=studio;fake=short_ollama(studio,expanded=expanded)
    view=run(studio,{'provider':'ollama'});current=view['current']
    assert current and current['text']==words(expanded)
    assert sum(task=='expand_duration' for task,_,_ in fake.calls)==1
    report=current['report']
    assert current['word_count']==report['word_count']==word_count(current['text'])==expanded
    assert report['target_word_min']==375 and report['target_word_max']==435
    assert (SHORT_WARNING in report['issues'])==(expanded<375)
    assert RAW_REVIEW not in json.dumps(view)
    with closing(sqlite3.connect(data/'app.db')) as db:
        row=db.execute('SELECT text,word_count,estimated_minutes,report_json FROM script_versions WHERE id=?',(current['id'],)).fetchone()
    assert row[1]==word_count(row[0])==expanded
    assert row[2]==current['estimated_minutes']==report['estimated_minutes']
    assert json.loads(row[3])['word_count']==expanded
    assert word_count((data/'projects'/project['id']/'script'/'script_v1.txt').read_text())==expanded
    expansion_prompt=next(prompt for task,_,prompt in fake.calls if task=='expand_duration')
    assert 'filler' in expansion_prompt and 'facts' in expansion_prompt


def test_385_words_in_375_435_range_has_no_duration_warning_or_extra_call(studio):
    _,_,_,_=studio;fake=short_ollama(studio,initial=385)
    current=run(studio,{'provider':'ollama'})['current']
    assert current['word_count']==current['report']['word_count']==385
    assert current['estimated_minutes']==2.85
    assert SHORT_WARNING not in current['report']['issues']
    assert not any('hedef süre' in issue or 'Kelime sayısı' in issue for issue in current['report']['issues'])
    assert not any(task=='expand_duration' for task,_,_ in fake.calls)


@pytest.mark.parametrize('expanded,estimated_minutes',[(400,2.96),(360,2.67)])
def test_340_words_always_expand_once_toward_midpoint_and_measure_final(studio,expanded,estimated_minutes):
    client,project,_,data=studio
    fake=short_ollama(studio,initial=340,expanded=expanded)
    view=run(studio,{'provider':'ollama'});current=view['current']
    expansions=[(inputs,prompt) for task,inputs,prompt in fake.calls if task=='expand_duration']
    assert len(expansions)==1
    inputs,prompt=expansions[0]
    assert inputs['target_words']==405 and inputs['target_word_min']==375 and inputs['target_word_max']==435
    assert inputs['topic']=='Technikvergleich' and inputs['blueprint']['content_type']==current['content_type']
    assert inputs['source_text']==words(340) and inputs['language']=='de'
    for instruction in ('facts','section structure','tone','target language','useful content','content type','filler','repeat paragraphs'):
        assert instruction in prompt
    assert current['text']==words(expanded)
    assert current['word_count']==current['report']['word_count']==word_count(current['text'])==expanded
    assert current['estimated_minutes']==current['report']['estimated_minutes']==estimated_minutes
    for messages in (current['report']['issues'],current['report']['review_messages']):
        assert (SHORT_WARNING in messages)==(expanded<375)
    assert current['report']['target_word_min']==375 and current['report']['target_word_max']==435
    assert view['job']['progress']['duration_correction']['attempted'] is True
    assert view['job']['progress']['duration_correction']['applied'] is True
    with closing(sqlite3.connect(data/'app.db')) as db:
        row=db.execute('SELECT text,word_count,estimated_minutes,report_json FROM script_versions WHERE id=?',(current['id'],)).fetchone()
    assert row[0]==current['text'] and row[1]==expanded and row[2]==estimated_minutes
    assert json.loads(row[3])==current['report']
    assert (data/'projects'/project['id']/'script'/'script_v1.txt').read_text()==current['text']


@pytest.mark.parametrize('initial,expected_calls',[(374,1),(375,0),(435,0),(436,0)])
def test_duration_expansion_uses_exact_minimum_boundary(studio,initial,expected_calls):
    fake=short_ollama(studio,initial=initial,expanded=405)
    current=run(studio,{'provider':'ollama'})['current']
    assert sum(task=='expand_duration' for task,_,_ in fake.calls)==expected_calls
    assert current['word_count']==(405 if expected_calls else initial)
    assert SHORT_WARNING not in current['report']['issues']


@pytest.mark.parametrize('result',[184,ScriptProviderError(KEY+' private error',category='generation_timeout'),RuntimeError(KEY+PRIVATE),words(150)+'\n\n'+words(150)])
def test_correction_failure_or_repetition_keeps_script_and_warns_once(studio,result,caplog):
    fake=short_ollama(studio,expanded=result);caplog.set_level('INFO')
    view=run(studio,{'provider':'ollama'})
    assert view['current']['text']==words(184) and view['job']['status']=='draft'
    assert SHORT_WARNING in view['current']['report']['issues'] and CORRECTION_WARNING in view['current']['report']['issues']
    assert sum(task=='expand_duration' for task,_,_ in fake.calls)==1
    assert KEY not in caplog.text and PRIVATE not in caplog.text


@pytest.mark.parametrize('initial,expanded',[(184,385),(340,360)])
def test_resume_after_corrected_script_does_not_expand_again(studio,initial,expanded):
    client,project,_,_=studio;fake=short_ollama(studio,initial=initial,expanded=expanded,fail_review=True)
    view=run(studio,{'provider':'ollama'})
    assert view['job']['status']=='error' and word_count(view['job']['partial_text'])==expanded
    response=client.post(f'/api/projects/{project["id"]}/script/jobs/{view["job"]["id"]}/resume',json={'confirm_replace_approved':False})
    assert response.status_code==202;client.app.state.scripts.futures[view['job']['id']].result(timeout=5)
    current=client.get(f'/api/projects/{project["id"]}/script').json()['current']
    assert current['word_count']==expanded and sum(task=='expand_duration' for task,_,_ in fake.calls)==1
    assert (SHORT_WARNING in current['report']['issues'])==(expanded<375)


def test_real_ollama_adapter_keeps_reasoning_and_raw_review_out_of_all_storage(studio,caplog):
    client,_,_,data=studio;fake=short_ollama(studio)
    def respond(request):
        body=json.loads(request.content);assert body['think'] is False and body['stream'] is False
        return httpx.Response(200,json={'done':True,'response':fake.generate_script(body['prompt']),'thinking':PRIVATE})
    client.app.state.scripts.provider_factory=lambda name,settings:OllamaScriptProvider('http://localhost:11434','qwen3.5:9b',transport=httpx.MockTransport(respond))
    caplog.set_level('INFO');view=run(studio,{'provider':'ollama'})
    assert view['current']['word_count']==385
    with closing(sqlite3.connect(data/'app.db')) as db:dump='\n'.join(db.iterdump())
    stored=''.join(path.read_text() for path in (data/'projects').rglob('*') if path.is_file())
    for private in (PRIVATE,RAW_REVIEW):assert private not in json.dumps(view)+caplog.text+dump+stored


def test_legacy_review_and_stale_warning_filtered_without_changing_records(studio):
    client,project,_,data=studio;short_ollama(studio,initial=385);current=run(studio,{'provider':'ollama'})['current']
    report={**current['report'],'issues':[RAW_REVIEW,'Kelime sayısı hedef süre aralığının dışında. Kaliteyi ve tahmini süreyi inceleyin; gerekirse metni düzenleyin.']}
    with closing(sqlite3.connect(data/'app.db')) as db,db:
        db.execute('UPDATE script_versions SET report_json=? WHERE id=?',(json.dumps(report),current['id']))
        before='\n'.join(db.iterdump())
    view=client.get(f'/api/projects/{project["id"]}/script').json()
    assert RAW_REVIEW not in json.dumps(view) and SHORT_WARNING not in view['current']['report']['issues']
    assert view['current']['word_count']==view['current']['report']['word_count']==385
    with closing(sqlite3.connect(data/'app.db')) as db:assert '\n'.join(db.iterdump())==before
