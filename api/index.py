import json
import os
import urllib.request

API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

SYSTEM_PROMPT = (
    "Ты — дружелюбный голосовой помощник для умной колонки. "
    "Отвечай кратко, не длиннее 50 слов, простыми предложениями, без списков и эмодзи."
)

MAX_HISTORY = 6
_history = {}


def _alice_response(text, end_session=False):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "response": {"text": text, "tts": text, "end_session": end_session},
            "version": "1.0",
        }, ensure_ascii=False),
    }


def _ask_yandexgpt(messages):
    payload = {
        "modelUri": "gpt://{}/yandexgpt-lite".format(os.environ["FOLDER_ID"]),
        "completionOptions": {"temperature": 0.6, "maxTokens": 200},
        "messages": messages,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Api-Key {}".format(os.environ["YANDEX_API_KEY"]),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["result"]["alternatives"][0]["message"]["text"]


def handler(request):
    # Токен вебхука: сверяем, если он есть в URL и задан в настройках
    token_env = os.environ.get("ALICE_WEBHOOK_TOKEN", "")
    url = getattr(request, "url", "") or ""
    if token_env and "token=" in url:
        token_in_url = url.split("token=")[1].split("&")[0]
        if token_in_url != token_env:
            return {"statusCode": 404, "body": "not found"}

    # Читаем запрос от Алисы
    try:
        raw = getattr(request, "body", b"") or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return {"statusCode": 400, "body": "bad request"}

    session = data.get("session", {}) if isinstance(data, dict) else {}

    # Проверка ID навыка — чужие запросы не пройдут
    skill_id_env = os.environ.get("ALICE_SKILL_ID", "")
    if skill_id_env and session.get("skill_id") != skill_id_env:
        return {"statusCode": 403, "body": "forbidden"}

    utterance = ((data.get("request") or {}).get("original_utterance") or "").strip()
    session_id = session.get("session_id") or "default"

    if utterance.lower() in ("выход", "стоп", "заверши"):
        return _alice_response("Выхожу из навыка. Снова доступна обычная Алиса!", end_session=True)

    if not utterance:
        return _alice_response("Привет! Я умный помощник. Спроси меня о чём угодно.")

    if utterance.lower() == "сброс":
        _history.pop(session_id, None)
        return _alice_response("Начинаем новый разговор. Спрашивай!")

    messages = [{"role": "system", "text": SYSTEM_PROMPT}]
    messages += _history.get(session_id, [])
    messages.append({"role": "user", "text": utterance})

    try:
        answer = _ask_yandexgpt(messages)
    except Exception:
        answer = "Что-то пошло не так, попробуй спросить ещё раз."

    history = _history.setdefault(session_id, [])
    history.append({"role": "user", "text": utterance})
    history.append({"role": "assistant", "text": answer})
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]

    return _alice_response(answer)
