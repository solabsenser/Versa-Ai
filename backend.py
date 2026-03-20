import os
import json
import time
from datetime import datetime
from typing import List, Dict

from supabase import create_client
from dotenv import load_dotenv
from groq import Groq

# ================= INIT =================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= MODELS =================
CHAT_MODEL = "llama-3.1-8b-instant"
CODE_MODEL = "llama-3.3-70b-versatile"

# ================= SYSTEM PROMPTS =================

CODE_SYSTEM = """
You are an elite software engineer.

STRICT:
- Only clean production code
- No explanations unless asked
- Fix bugs automatically
- Optimize
- Use best practices
- No fluff
"""

CHAT_SYSTEM = """
You are a smart assistant.
Be clear, helpful, and proactive.
Always suggest next actions.
"""

ENHANCER_STAGE_1 = """
Rewrite user input into a structured intent.
Remove noise. Keep meaning.
"""

ENHANCER_STAGE_2 = """
Convert this into a precise developer instruction.
Make it executable and technical.
"""

ROUTER_PROMPT = """
Classify task:
Return ONLY one word:
code OR chat

Text:
"""

CRITIC_PROMPT = """
Evaluate response quality (1-10) and suggest fix if <8.
Return JSON:
{ "score": number, "fix": "..." }
"""

FOLLOWUP_PROMPT = """
Suggest 2 next actions user may want.
"""

# ================= LLM CORE =================
def call_llm(messages, model, temperature=0.3, retries=2):
    for _ in range(retries):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=4096
            )
            return res.choices[0].message.content
        except Exception:
            time.sleep(1)
    return "Error: LLM failed"


# ================= PROMPT ENHANCER =================
def enhance_prompt(user_input):
    step1 = call_llm([
        {"role": "system", "content": ENHANCER_STAGE_1},
        {"role": "user", "content": user_input}
    ], CHAT_MODEL)

    step2 = call_llm([
        {"role": "system", "content": ENHANCER_STAGE_2},
        {"role": "user", "content": step1}
    ], CHAT_MODEL)

    return step2


# ================= ROUTER =================
def detect_task(user_input):
    try:
        result = call_llm([
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_input}
        ], CHAT_MODEL, 0)

        if "code" in result.lower():
            return "code"
    except:
        pass

    keywords = ["python", "api", "bug", "error", "code"]
    for k in keywords:
        if k in user_input.lower():
            return "code"

    return "chat"


# ================= MODEL SELECT =================
def select_model(task):
    return CODE_MODEL if task == "code" else CHAT_MODEL


# ================= MEMORY =================
def save_message(user_id, role, content):
    supabase.table("messages").insert({
        "user_id": user_id,
        "role": role,
        "content": content,
        "created_at": str(datetime.utcnow())
    }).execute()


def get_history(user_id, limit=30):
    res = supabase.table("messages") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=False) \
        .limit(limit) \
        .execute()

    return [{"role": m["role"], "content": m["content"]} for m in res.data]


# ================= CONTEXT BUILDER =================
def build_context(history):
    context = []

    for msg in history:
        context.append(msg)

    return context


# ================= SUMMARY =================
def summarize(user_id):
    history = get_history(user_id, 50)

    if len(history) < 15:
        return

    summary = call_llm([
        {"role": "system", "content": "Summarize with technical details"},
        {"role": "user", "content": str(history)}
    ], CHAT_MODEL)

    supabase.table("messages").delete().eq("user_id", user_id).execute()
    save_message(user_id, "system", f"SUMMARY: {summary}")


# ================= RESPONSE CRITIC =================
def evaluate_response(response):
    try:
        raw = call_llm([
            {"role": "system", "content": CRITIC_PROMPT},
            {"role": "user", "content": response}
        ], CHAT_MODEL)

        data = json.loads(raw)
        return data
    except:
        return {"score": 10}


# ================= FOLLOWUP =================
def generate_followup(response):
    try:
        return call_llm([
            {"role": "system", "content": FOLLOWUP_PROMPT},
            {"role": "user", "content": response}
        ], CHAT_MODEL)
    except:
        return ""


# ================= CLEAN =================
def clean_output(text):
    return text.strip()


# ================= MAIN =================
def chat(user_id, user_input):
    history = get_history(user_id)

    task = detect_task(user_input)
    enhanced = enhance_prompt(user_input)
    model = select_model(task)

    system_prompt = CODE_SYSTEM if task == "code" else CHAT_SYSTEM

    messages = [
        {"role": "system", "content": system_prompt},
        *build_context(history),
        {"role": "user", "content": enhanced}
    ]

    response = call_llm(messages, model)
    response = clean_output(response)

    # self-critic
    eval_data = evaluate_response(response)

    if eval_data.get("score", 10) < 8:
        response = call_llm([
            {"role": "system", "content": "Improve this response"},
            {"role": "user", "content": response}
        ], model)

    followup = generate_followup(response)

    final = f"{response}\n\n---\n💡 Next:\n{followup}"

    save_message(user_id, "user", user_input)
    save_message(user_id, "assistant", final)

    if len(history) > 25:
        summarize(user_id)

    return final
