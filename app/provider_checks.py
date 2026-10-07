"""Documented Ollama availability check only. No content generation."""
import httpx


def check_ollama(config: dict, *, transport=None) -> dict:
    try:
        # Ollama is local; never send this request through inherited Internet proxies.
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False, **({'transport': transport} if transport is not None else {})) as client:
            response = client.get(config["base_url"] + "/api/tags")
            response.raise_for_status()
            data = response.json()
        models = data["models"]
        if not isinstance(models, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in models):
            raise ValueError()
        if config["model"] and config["model"] not in {item["name"] for item in models}:
            return {"status": "Hata", "category": "model_unavailable", "message": "Ollama çalışıyor ancak seçilen model bulunamadı. Ollama'da kurulu modelin tam adını girip kaydedin."}
        return {"status": "Hazır", "message": "Ollama bağlantısı başarılı." if config["model"] else "Ollama çalışıyor. Kullanmak için kurulu modelin adını girip kaydedin."}
    except httpx.TimeoutException:
        return {"status": "Hata", "category": "generation_timeout", "message": "Ollama bağlantı kontrolüne zamanında yanıt vermedi. Ollama uygulamasını ve model durumunu kontrol edin."}
    except (httpx.ConnectError, httpx.ProxyError):
        return {"status": "Hata", "category": "local_connection", "message": "Ollama'ya ulaşılamadı. Ollama uygulamasını açın, yerel adresi kontrol edip tekrar deneyin."}
    except httpx.TransportError:
        return {"status": "Hata", "category": "network_error", "message": "Ollama HTTP bağlantısı tamamlanamadı. Yerel adresi ve Ollama durumunu kontrol edin."}
    except httpx.HTTPError:
        return {"status": "Hata", "category": "upstream_error", "message": "Ollama bağlantı kontrolünü kabul etmedi. Yerel adresi ve Ollama durumunu kontrol edin."}
    except (ValueError, KeyError, TypeError):
        return {"status": "Hata", "category": "invalid_response", "message": "Ollama model listesi okunamadı. Ollama'yı güncelleyip tekrar deneyin."}
