"""Documented Ollama availability check only. No content generation."""
import httpx


def check_ollama(config: dict) -> dict:
    try:
        # Ollama is local; never send this request through inherited Internet proxies.
        with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = client.get(config["base_url"] + "/api/tags")
            response.raise_for_status()
            data = response.json()
        models = data["models"]
        if not isinstance(models, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in models):
            raise ValueError()
        if config["model"] and config["model"] not in {item["name"] for item in models}:
            return {"status": "Hata", "message": "Ollama çalışıyor ancak seçilen model bulunamadı. Ollama'da kurulu modelin tam adını girip kaydedin."}
        return {"status": "Hazır", "message": "Ollama bağlantısı başarılı." if config["model"] else "Ollama çalışıyor. Kullanmak için kurulu modelin adını girip kaydedin."}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {"status": "Hata", "message": "Ollama'ya ulaşılamadı. Ollama uygulamasını açın, yerel adresi kontrol edip tekrar deneyin."}
