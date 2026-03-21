import os
import json
import time
import asyncio
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional

from supabase import create_client
from dotenv import load_dotenv
from groq import Groq

# ================= INIT ===============================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= MODELS =============================
CHAT_MODEL = "llama-3.1-8b-instant"
CODE_MODEL = "llama-3.3-70b-versatile"

# ================= SYSTEM PROMPTS =====================
UNIFIED_SYSTEM = """
You are an intelligent AI assistant with adaptive behavior.

Your job is to understand the user's intent and respond appropriately.

CORE RULE:
First understand the intent, then choose response style.

---------------------

INTENT TYPES:

1. CASUAL / SIMPLE:
Examples:
- "как дела"
- "привет"
- "что это"

Response:
- short
- natural
- human-like
- no extra info

2. TECHNICAL / CODE:
Examples:
- "write python script"
- "fix this error"
- "create API"

Response:
- precise
- structured
- code if needed
- no fluff

---------------------

STRICT RULES:

- NEVER over-explain simple questions
- NEVER switch topic on your own
- NEVER assume complex intent if question is simple
- NEVER generate code unless clearly requested
- If user is casual → be casual
- If user is technical → be technical

---------------------

STYLE CONTROL:

- casual → 1-2 sentences max
- technical → structured answer or code

---------------------

FINAL RULE:
Match the user's level and intent exactly.
Do not act smarter than needed.
"""
ENHANCER_PROMPT = """
You improve user input ONLY if it is clearly a programming task.

Rules:
- If NOT programming → return EXACT same text
- Do NOT rephrase casual input
- Do NOT add new meaning
- Only clarify technical intent

Return ONLY final version.

User input:
"""
FOLLOWUP_PROMPT = """
Generate a SHORT natural follow-up suggestion.

Rules:
- Max 1 short sentence
- Sound human, not robotic
- Do NOT list features
- Do NOT explain capabilities
- Only suggest something relevant

Examples:

User: привет
→ "Хочешь что-нибудь разобрать или просто поболтать?"

User: ошибка в коде
→ "Можешь скинуть код, посмотрим что не так?"

User: как сделать API
→ "Хочешь пример на FastAPI?"

If nothing useful → return empty.
"""
FOLLOWUP_PROMPT = """
Suggest next steps ONLY if useful.

Rules:
- If casual → return EMPTY
- If simple answer → return EMPTY
- Only for complex technical tasks → suggest max 2 short actions
"""
# ================= UTILS ==============================
def now():
    return str(datetime.utcnow())

def safe_json(text):
    try:
        return json.loads(text)
    except:
        return {"score": 10}

def log_error(e):
    print("ERROR:", str(e))
    
# ================= LLM CORE ===========================
def call_llm(messages, model, temperature=0.3, retries=3):
    for attempt in range(retries):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=4096
            )
            return res.choices[0].message.content
        except Exception as e:
            log_error(e)
            time.sleep(1)
    return "LLM_ERROR"

#================= ASYNC WRAPPER =====================
async def call_llm_async(messages, model, temperature=0.3):
    return await asyncio.to_thread(call_llm, messages, model, temperature)

#================= PROMPT ENHANCER ====================
def enhance_prompt_sync(user_input):
    step1 = call_llm([
        {"role": "system", "content": ENHANCER_STAGE_1},
        {"role": "user", "content": user_input}
    ], CHAT_MODEL, 0)

    step2 = call_llm([
        {"role": "system", "content": ENHANCER_STAGE_2},
        {"role": "user", "content": step1}
    ], CHAT_MODEL, 0)

    return step2

async def enhance_prompt(user_input):
    return await asyncio.to_thread(enhance_prompt_sync, user_input)

# ================= ROUTER =============================
def detect_task_sync(user_input):
    try:
        res = call_llm([
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_input}
        ], CHAT_MODEL, 0)

        if "code" in res.lower():
            return "code"
    except:
        pass

    keywords = ["python", "code", "api", "bug", "error"]
    return "code" if any(k in user_input.lower() for k in keywords) else "chat"

async def detect_task(user_input):
    return await asyncio.to_thread(detect_task_sync, user_input)

# ================= MODEL SELECT =======================
def select_model(task):
    return CODE_MODEL if task == "code" else CHAT_MODEL

#================= MEMORY =============================
def save_message(user_id, role, content):
    supabase.table("messages").insert({
        "user_id": user_id,
        "role": role,
        "content": content,
        "created_at": now()
    }).execute()

def get_history(user_id, limit=40):
    res = supabase.table("messages") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .execute()

    return [{"role": m["role"], "content": m["content"]} for m in res.data]

def clear_history(user_id):
    supabase.table("messages").delete().eq("user_id", user_id).execute()

# ================= CONTEXT ============================
def trim_history(history, max_chars=12000):
    total = 0
    trimmed = []

    for msg in reversed(history):
        total += len(msg["content"])
        if total > max_chars:
            break
        trimmed.append(msg)

    return list(reversed(trimmed))

def build_context(history):
    return trim_history(history)

# ================= SUMMARY ============================
def summarize(user_id):
    history = get_history(user_id, 60)

    if len(history) < 20:
        return

    summary = call_llm([
        {"role": "system", "content": "Summarize with technical detail"},
        {"role": "user", "content": str(history)}
    ], CHAT_MODEL)

    clear_history(user_id)
    save_message(user_id, "system", f"SUMMARY: {summary}")

# ================= RESPONSE CRITIC ====================
def evaluate_response(response):
    raw = call_llm([
        {"role": "system", "content": CRITIC_PROMPT},
        {"role": "user", "content": response}
    ], CHAT_MODEL, 0)

    return safe_json(raw)

def improve_response(response, model):
    return call_llm([
        {"role": "system", "content": "Improve response quality"},
        {"role": "user", "content": response}
    ], model)

# ================= FOLLOWUP ===========================
def generate_followup(response):
    return call_llm([
        {"role": "system", "content": FOLLOWUP_PROMPT},
        {"role": "user", "content": response}
    ], CHAT_MODEL)

# ================= OUTPUT =============================
def clean_output(text):
    return text.strip()

def format_output(response, followup):
    if not followup or len(followup.strip()) < 5:
        return response

    return f"{response}\n\n💡 {followup}"

# ================= MAIN (SYNC) ========================
def chat(user_id, user_input):
    history = get_history(user_id)

    task = detect_task_sync(user_input)

    # enhancer только для code
    if task == "code":
        enhanced = enhance_prompt_sync(user_input)
    else:
        enhanced = user_input

    model = select_model(task)

    # 🔥 ГЛАВНОЕ ИЗМЕНЕНИЕ
    system_prompt = UNIFIED_SYSTEM

    messages = [
        {"role": "system", "content": system_prompt},
        *build_context(history),
        {"role": "user", "content": enhanced}
    ]

    response = call_llm(messages, model, 0.2)
    response = clean_output(response)

    eval_data = evaluate_response(response)

    if eval_data.get("score", 10) < 8:
        response = improve_response(response, model)

    followup = generate_followup(response)

    final = format_output(response, followup)

    save_message(user_id, "user", user_input)
    save_message(user_id, "assistant", final)

    if len(history) > 30:
        summarize(user_id)

    return final
#================ MAIN (ASYNC) =======================
async def chat_async(user_id, user_input):
    history = await asyncio.to_thread(get_history, user_id)

    task = await detect_task(user_input)

    if task == "code":
        enhanced = await enhance_prompt(user_input)
    else:
        enhanced = user_input

    model = select_model(task)

    # 🔥 ГЛАВНОЕ
    system_prompt = UNIFIED_SYSTEM

    messages = [
        {"role": "system", "content": system_prompt},
        *build_context(history),
        {"role": "user", "content": enhanced}
    ]

    response = await call_llm_async(messages, model, 0.2)
    response = clean_output(response)

    eval_data = await asyncio.to_thread(evaluate_response, response)

    if eval_data.get("score", 10) < 8:
        response = await call_llm_async([
            {"role": "system", "content": "Improve response"},
            {"role": "user", "content": response}
        ], model)

    followup = await call_llm_async([
        {"role": "system", "content": FOLLOWUP_PROMPT},
        {"role": "user", "content": response}
    ], CHAT_MODEL)

    final = format_output(response, followup)

    await asyncio.to_thread(save_message, user_id, "user", user_input)
    await asyncio.to_thread(save_message, user_id, "assistant", final)

    if len(history) > 30:
        await asyncio.to_thread(summarize, user_id)

    return final

# ================= AGENT LOOP =========================
MAX_ITERATIONS = 3


def extract_code(text):
    """
    Вытаскивает код из ответа модели
    """
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            return parts[1]
    return text


def run_code_safely(code: str):
    """
    Выполнение кода с перехватом ошибок
    """
    local_vars = {}

    try:
        exec(code, {}, local_vars)
        return True, "Execution success"
    except Exception as e:
        return False, str(e)


def agent_fix_prompt(code, error):
    return f"""
You wrote this code:

{code}

It produced this error:

{error}

Fix the code.
Return ONLY corrected code.
"""


def agent_generate_code(user_input):
    return call_llm([
        {"role": "system", "content": CODE_SYSTEM},
        {"role": "user", "content": user_input}
    ], CODE_MODEL)


def agent_loop(user_input):
    """
    Главный агент
    """

    code = agent_generate_code(user_input)

    for i in range(MAX_ITERATIONS):
        extracted = extract_code(code)

        success, result = run_code_safely(extracted)

        if success:
            return f"{extracted}\n\n# ✅ Code executed successfully"

        # если ошибка — фикс
        code = call_llm([
            {"role": "system", "content": "You are fixing code"},
            {"role": "user", "content": agent_fix_prompt(extracted, result)}
        ], CODE_MODEL)

    return f"{extracted}\n\n# ❌ Could not fully fix after {MAX_ITERATIONS} attempts"

# ================= AGENT CHAT =========================
def chat_with_agent(user_id, user_input):
    """
    Используем агент ТОЛЬКО для кодовых задач
    """

    history = get_history(user_id)

    task = detect_task_sync(user_input)

    if task == "code":
        response = agent_loop(user_input)
    else:
        response = chat(user_id, user_input)

    followup = generate_followup(response)

    final = format_output(response, followup)

    save_message(user_id, "user", user_input)
    save_message(user_id, "assistant", final)

    return final
