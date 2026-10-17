import json
from pathlib import Path

import pytest

from app.secret_store import SettingsStore
from app.settings import SettingsInputError, SettingsService
from app.stock.models import normalized_media


def test_retired_provider_credential_is_removed_without_touching_other_settings(tmp_path):
    store=SettingsStore(tmp_path/'secrets')
    store.write({'magnific':{'api_key':'retired-secret','enabled':True},'pixabay':{'api_key':'keep-me'}})
    service=SettingsService(store)
    saved=store.read()
    assert 'magnific' not in saved
    assert saved['pixabay']['api_key']=='keep-me'
    assert 'magnific' not in service.safe_view()


def test_retired_provider_cannot_be_configured_or_searched(tmp_path):
    service=SettingsService(SettingsStore(tmp_path/'secrets'))
    with pytest.raises(SettingsInputError): service.stock_config('magnific')
    with pytest.raises(SettingsInputError): service.save('magnific',{'api_key':'nope'})


def test_historical_media_schema_stays_readable_for_local_projects():
    media=normalized_media({'provider':'magnific','media_id':'legacy1','media_type':'video','source_url':'','page_url':'',
        'creator_name':'Tarihsel kayıt','creator_url':'','width':1920,'height':1080,'duration':8,
        'preview_url':'','download_url':'','query_used':'eski','description':'','source_metadata':{'license':'Tarihsel lisans'}})
    assert media['provider']=='magnific'
    assert media['source_metadata']['license']=='Tarihsel lisans'


def test_no_active_premium_client_or_frontend_setting_remains():
    root=Path(__file__).parents[1]
    assert not (root/'app/stock/magnific.py').exists()
    runtime='\n'.join((root/path).read_text(encoding='utf-8') for path in (
        'app/main.py','app/stock/service.py','app/stock/director_media.py','app/stock/providers.py',
        'app/static/settings.js','app/static/settings-http.js'))
    assert 'magnific' not in runtime.casefold()
    assert 'freepik' not in runtime.casefold()


def test_zadiaq_shell_and_real_editor_controls_are_present():
    root=Path(__file__).parents[1]
    html=(root/'app/static/index.html').read_text(encoding='utf-8')
    editor=(root/'app/static/editor.js').read_text(encoding='utf-8')
    for label in ('Üretim','Kurgu','Ayarlar','shell-project','naman-logo.png'):
        assert label in html
    for behavior in ('Medyayı yeniden seç','Klip başlangıcı','Değişiklikleri kaydet','audio.play','Sığdır','↶ 5 sn'):
        assert behavior in editor
