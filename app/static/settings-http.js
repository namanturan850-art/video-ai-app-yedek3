/* Request timing and failure classification shared by the Settings screen. */
async function settingsRequest(url, method = 'GET', body) {
  const gemini = /^\/api\/settings\/(gemini|images\/gemini)\/(models|test)$/.test(url);
  const openai = ['/api/settings/openai/test', '/api/settings/images/openai/test'].includes(url);
  const ai33=['/api/settings/ai33/test','/api/settings/ai33/voices','/api/settings/ai33/tasks/diagnose','/api/settings/ai33/task/diagnose'].includes(url);
  const stock = ['/api/settings/pexels/test','/api/settings/pixabay/test'].includes(url);
  const mapbox = url === '/api/settings/mapbox/test';
  const diagnostics = url.startsWith('/api/settings/ai-diagnostics');
  const timeoutMessage = 'Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.';
  const unexpectedMessage = 'Gemini ayarları işlenirken beklenmeyen bir sunucu hatası oluştu. Tekrar deneyin; sorun sürerse Tanılama ekranını kontrol edin.';
  function failure(message, category) {
    const error = new Error(message); error.category = category; return error;
  }
  function timedOut(error) { return ['TimeoutError', 'AbortError'].includes(error?.name); }
  async function classifyFetchFailure(error) {
    // A failed external operation does not establish that the local app is down.
    try {
      await fetch('/api/health', {cache: 'no-store', signal: AbortSignal.timeout(3000)});
    } catch (healthError) {
      if (timedOut(healthError)) return failure('Yerel uygulama sağlık kontrolüne zamanında yanıt vermedi. Bir süre bekleyip tekrar deneyin.', 'local_health_timeout');
      return failure('Uygulamaya ulaşılamadı. Uygulama penceresini kontrol edip yeniden açın.', 'local_unreachable');
    }
    if(ai33&&timedOut(error))return failure('AI33 API zaman aşımına uğradı. İnternet bağlantısını kontrol edip tekrar deneyin.','timeout');
    if(mapbox&&timedOut(error))return failure('Mapbox zamanında yanıt vermedi. İnternet bağlantısını kontrol edip tekrar deneyin.','timeout');
    if (gemini && timedOut(error)) return failure(timeoutMessage, 'gemini_timeout');
    if (openai && timedOut(error)) return failure('OpenAI API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.', 'generation_timeout');
    if (gemini && globalThis.navigator?.onLine === false) return failure('Gemini API için internet bağlantısı kurulamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.', 'no_internet');
    if (openai && globalThis.navigator?.onLine === false) return failure('OpenAI API için internet bağlantısı kurulamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.', 'no_internet');
    if (gemini) return failure(unexpectedMessage, 'unexpected_backend');
    return failure('Yerel uygulama çalışıyor ancak işlem tamamlanamadı. Bir süre bekleyip tekrar deneyin.', 'local_request_failed');
  }
  const options = {method, cache: 'no-store', signal: AbortSignal.timeout(gemini || openai || stock || ai33 ? 60000 : 20000), headers: {'X-AI-Video-Studio': 'settings'}};
  if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  let response;
  try { response = await fetch(url, options); }
  catch (error) { throw await classifyFetchFailure(error); }
  let result;
  try { result = await response.json(); }
  catch (error) {
    if (timedOut(error)) throw await classifyFetchFailure(error);
    throw failure(gemini ? unexpectedMessage : 'Yanıt okunamadı. Sayfayı yeniden açıp tekrar deneyin.', 'unexpected_backend');
  }
  if (!result || typeof result !== 'object') throw failure(unexpectedMessage, 'unexpected_backend');
  if (!response.ok) {
    if (diagnostics) {
      const messages = {403:'Tanılama yalnızca yerel uygulama ekranından çalıştırılabilir. Sayfayı yeniden açın.',
        409:'Bu sağlayıcının testi sürüyor. Sonucu bekleyip yenileyin.',
        422:'Test başlatılamadı. Ekrandaki test düğmesini kullanın ve varsa maliyet onayını verin.',
        503:'Yerel tanılama şu anda çalıştırılamıyor. Uygulamayı yeniden açıp tekrar deneyin.'};
      throw failure(messages[response.status] || 'Yerel tanılama işlemi tamamlanamadı. Sonuçları yenileyip tekrar deneyin.', 'local_request_failed');
    }
    if (openai) {
      const messages = {
        provider_disabled:'OpenAI kapalı. Ayarlar → OpenAI bölümünde Etkinleştir seçimini açıp Kaydet deyin.',
        missing_key:'OpenAI API anahtarı yapılandırılmamış. Ayarlar bölümünden kaydedin.',
        missing_model:'OpenAI modelini Ayarlar bölümünde kontrol edin.',
        key_rejected:'OpenAI API anahtarı veya erişim izni kabul edilmedi.',
        invalid_model:'OpenAI modeli veya desteklediği API isteği geçersiz.',
        model_unavailable:'Seçilen OpenAI modeli kullanılamıyor.',
        billing_quota:'OpenAI faturalandırma veya kota sınırına ulaşıldı. API hesabınızın bakiye ve limitlerini kontrol edin.',
        rate_limit:'OpenAI istek hız sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
        quota_limit:'OpenAI kullanım sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
        generation_timeout:'OpenAI API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.',
        no_internet:'OpenAI API için internet bağlantısı kurulamadı.',
        network_error:'OpenAI API HTTP bağlantısı tamamlanamadı. Ağ ve proxy ayarlarını kontrol edin.',
        upstream_error:'OpenAI API şu anda yanıt veremiyor. Daha sonra tekrar deneyin.',
        invalid_response:'OpenAI API yanıtı okunamadı. Tekrar deneyin.'};
      const known=Object.hasOwn(messages,result.category);
      throw failure(known?messages[result.category]:'OpenAI bağlantısı işlenirken beklenmeyen hata oluştu. Tekrar deneyin; mevcut dosyaları silmeyin.',known?result.category:'unexpected_backend');
    }
    if (gemini) {
      // Do not display arbitrary proxy/server error bodies, even if valid JSON.
      const messages = {
        gemini_timeout: timeoutMessage,
        key_rejected: 'Google Gemini API anahtarı veya erişim izni kabul edilmedi. Google AI Studio anahtarını ve API kısıtlamalarını kontrol edin.',
        quota_limit: 'Gemini kota veya istek sınırına ulaşıldı. Bir süre bekleyip Google AI Studio kotasını kontrol edin.',
        rate_limit: 'Gemini istek hız sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
        free_quota_exhausted: 'Gemini ücretsiz API kotası tükendi veya bu model için ücretsiz kota yok. Google AI Studio kullanım sınırlarını kontrol edin.',
        invalid_request: 'Gemini model veya istek ayarlarını kabul etmedi. Seçilen modelin metin üretimini desteklediğini kontrol edin.',
        no_internet: 'Gemini API için internet bağlantısı kurulamadı. İnternet bağlantınızı, güvenlik duvarını ve varsa proxy ayarlarını kontrol edin.',
        network_error: 'Gemini API HTTP bağlantısı tamamlanamadı. Ağ ve proxy ayarlarını kontrol edin.',
        model_unavailable: 'Kayıtlı model Gemini API listesinde bulunamadı. Modelleri Getir düğmesine basıp listeden geçerli bir model seçin ve Kaydet deyin.',
        missing_key: 'Önce Ayarlar → Gemini bölümünde API anahtarını kaydedin. Gemini kullanmak zorunda değilsiniz.',
        invalid_settings: 'Gemini ayarları sorgu sırasında değişmiş olabilir. Ayarları yeniden açıp tekrar deneyin.',
        local_storage: 'Yerel ayarlar açılamadı. Dosyaları silmeden destek isteyin.',
        upstream_error: 'Google Gemini API şu anda yanıt veremiyor. Daha sonra tekrar deneyin.',
        invalid_response: 'Gemini API yanıtı okunamadı. Daha sonra tekrar deneyin.',
        response_schema_mismatch: 'Gemini API yanıt yapısı beklenen sözleşmeyle uyuşmuyor.',
        model_unsupported: 'Seçilen Gemini modeli bu metin isteğini desteklemiyor.'
      };
      const known = Object.hasOwn(messages, result.category);
      throw failure(known ? messages[result.category] : unexpectedMessage, known ? result.category : 'unexpected_backend');
    }
    if(ai33){
      const messages={missing_key:'Önce AI33 / OpenSpeaker API anahtarını kaydedin.',key_rejected:'API anahtarı reddedildi. Kaydettiğiniz AI33 anahtarını kontrol edin.',
        connection_error:'API bağlantısı kurulamadı. İnternet bağlantısını kontrol edip tekrar deneyin.',timeout:'AI33 API zaman aşımına uğradı. İnternet bağlantısını kontrol edip tekrar deneyin.',
        credits_unavailable:'Kullanım/kredi bilgisi alınamadı. Daha sonra tekrar deneyin.',rate_limit:'AI33 istek sınırına ulaşıldı. Bir süre bekleyip tekrar deneyin.',
        task_history_unavailable:'Görev geçmişi bu API yanıtında kullanılamıyor. Ses ayarları korundu; bu uç noktanın hesap erişimini kontrol edin.',
        invalid_task_id:'Geçerli bir Task ID girin. Yalnız harf, rakam, tire ve alt çizgi kullanılabilir (en fazla 150 karakter).',
        invalid_request:'Ses sağlayıcısını, arama metnini ve sayfa seçimini kontrol edin.',unexpected_voice_schema:'AI33 ses yanıtı beklenen biçimde değil. Önceki ses seçimi korundu; tekrar deneyin.',
        unexpected_task_schema:'AI33 görev yanıtı bu sürümün beklediği biçimden farklı.',documentation_required:'Tamamlanan TTS görevinin ses çıktı alanı doğrulanmadı. Ücretli görev başlatılmadı.'};
      const known=Object.hasOwn(messages,result.category),error=failure(known?messages[result.category]:'AI33 ayarları işlenirken beklenmeyen hata oluştu. Dosyaları silmeden tekrar deneyin.',known?result.category:'unexpected_backend');
      if(known)error.diagnostic=result.diagnostic;throw error;
    }
    throw failure(result.message || 'İşlem tamamlanamadı. Bilgileri kontrol edip tekrar deneyin.', result.category || 'invalid_settings');
  }
  return result;
}
