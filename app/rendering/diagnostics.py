"""Reduce local FFmpeg failures to an allowlist. Never copy stderr fragments."""
import re

PHASES={
    'adaptive_layout':'Uyarlanabilir görsel düzen',
    'ffmpeg':'FFmpeg işlemi', 'input_preflight':'Stok medya ön kontrolü',
    'subtitle_preflight':'Altyazı ön kontrolü', 'slot_render':'Medya işleme',
    'crossfade':'Sahne geçişi', 'final_assembly':'Son birleştirme',
    'output_decode_validation':'Video dekod doğrulaması', 'output_validation':'Video doğrulaması',
    'smart_motion':'Akıllı kamera hareketi', 'smart_transition':'Akıllı sahne geçişi', 'emphasis_render':'Vurgu yazısı',
}
SUMMARIES={
    'adaptive_layout_failed':'Görsel düzen uygulanamadı; B-roll ve ses zamanlaması korundu.',
    'input_decode_failed':'Stok medya dosyalarından biri FFmpeg tarafından okunamadı.',
    'filter_graph_failed':'FFmpeg filtre işlemi başarısız oldu.',
    'filter_option_unsupported':'FFmpeg bu filtre komutu seçeneğini desteklemiyor.',
    'scale_filter_failed':'Stok medyanın boyutlandırılması başarısız oldu.',
    'subtitle_filter_failed':'Altyazı filtresi başarısız oldu.',
    'concat_failed':'Video parçalarının birleştirilmesi başarısız oldu.',
    'audio_mix_failed':'Son ses karışımı başarısız oldu.',
    'encoder_failed':'Video encoder başlatılamadı.',
    'nvenc_failed':'NVIDIA NVENC başlatılamadı. GPU sürücüsünü kontrol edin veya CPU seçin.',
    'output_mux_failed':'Son video dosyasının yazılması başarısız oldu. Boş alanı kontrol edin.',
    'output_validation_failed':'Oluşan videonun biçimi veya süresi doğrulanamadı; önceki video korundu.',
    'unknown_ffmpeg_error':'FFmpeg işlemi başarısız oldu; hata türü belirlenemedi.',
    'smart_motion_failed':'Akıllı hareket uygulanamadı; normal kadraj kullanıldı.',
    'smart_transition_failed':'Akıllı geçiş uygulanamadı; temiz kesme kullanıldı.',
    'emphasis_render_failed':'Vurgu yazısı uygulanamadı; altyazı ve video korunarak atlandı.',
}


def safe_diagnostic(value):
    """Rebuild even persisted diagnostics from controlled fields, not arbitrary text."""
    if not isinstance(value,dict):return None
    phase=value.get('phase');code=value.get('safe_error_code')
    if not isinstance(phase,str) or not isinstance(code,str) or phase not in PHASES or code not in SUMMARIES:return None
    result={'phase':phase,'operation':phase,'encoder':value.get('encoder') if value.get('encoder') in ('libx264','h264_nvenc') else '',
            'safe_error_code':code,'safe_error_summary':SUMMARIES[code],'phase_label':PHASES[phase]}
    for key in ('slot_index','slot_count'):
        item=value.get(key)
        if type(item) is int and 0<=item<=100000:result[key]=item
    if result.get('slot_count',0)>result.get('slot_index',100000):
        result['phase_label']=f"{PHASES[phase]}: Medya {result['slot_index']+1}/{result['slot_count']}"
    slot_id=value.get('slot_id')
    if isinstance(slot_id,str) and re.fullmatch(r'[0-9a-f]{32}',slot_id):result['slot_id']=slot_id
    if value.get('media_type') in ('image','video'):result['media_type']=value['media_type']
    rc=value.get('return_code')
    if type(rc) is int and -(2**32)<=rc<2**32:result['return_code']=rc
    return result


def diagnostic(code,**context):
    phase=context.get('phase','ffmpeg')
    if not isinstance(phase,str) or phase not in PHASES:phase='ffmpeg'
    return safe_diagnostic({**context,'phase':phase,'safe_error_code':code})


def classify(stderr,*,encoder='',phase='ffmpeg'):
    # Text is local and bounded by the runner. Output is a fixed code only.
    from app.rendering.tools import nvenc_initialization_failure
    text=stderr.lower()
    if encoder=='h264_nvenc' and nvenc_initialization_failure(text):return 'nvenc_failed'
    if 'filter_complex_script' in text and ('unrecognized option' in text or 'option not found' in text):return 'filter_option_unsupported'
    failure=any(s in text for s in ('error','failed','cannot','could not','no such filter','unable','impossible'))
    if phase=='subtitle_preflight' and (failure or 'no such file' in text):return 'subtitle_filter_failed'
    if failure and re.search(r'\[concat\s*@|\bparsed_concat_\d+\b|\bconcat (?:demuxer|filter)\b',text):return 'concat_failed'
    if any(s in text for s in ('could not write header','error writing trailer','error muxing','muxer','muxing a packet','av_interleaved_write_frame','no space left on device')):return 'output_mux_failed'
    if any(s in text for s in ('error opening encoder','error while opening encoder','cannot open encoder','unknown encoder')):return 'encoder_failed'
    if any(s in text for s in ('no such file or directory','invalid data found when processing input','error opening input','error during demuxing','error while decoding','matches no streams')):return 'input_decode_failed'
    # Filter names alone are not failures: successful libass/version banners occur in stderr.
    if failure:
        if phase=='subtitle_preflight' or re.search(r'\b(?:ass|libass|subtitles|parsed_ass_\d+)\b',text):return 'subtitle_filter_failed'
        if re.search(r'\b(?:amix|aresample|sidechaincompress|afade|alimiter|parsed_(?:amix|aresample|sidechaincompress|afade|alimiter)_\d+)\b',text) and phase=='final_assembly':return 'audio_mix_failed'
        if re.search(r'\b(?:scale|parsed_scale_\d+)\b',text):return 'scale_filter_failed'
    if any(s in text for s in ('error while filtering','error reinitializing filters','failed to configure output pad','no such filter','error parsing filter','error initializing filter','error applying option','error binding filtergraph')):return 'filter_graph_failed'
    return 'unknown_ffmpeg_error'
