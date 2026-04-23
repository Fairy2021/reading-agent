
# StoryVerse-Agent Harness Execution Plan (UI + Portrait System)

## 🎯 Objective

Build two autonomous capabilities:

1. UI Generation System (style_ui skill)
2. Character Portrait Generation System (unlock_portrait skill)

The system MUST:
- Run without asking user for decisions
- Use predefined tools, prompts, and configurations
- Follow Harness Engineering principles (no free-form reasoning)

---

# 🧠 System Architecture

```

Agent (Director)
↓
Skill Layer
↓
Tool Layer
↓
Harness (rules + constraints)

````

---

# 📦 Required Open Source Projects (Learn & Integrate)

## UI Generation
- https://github.com/wandb/openui
- https://github.com/CopilotKit/OpenGenerativeUI

## Image Generation
- https://github.com/comfyanonymous/ComfyUI
- https://github.com/pythongosssss/ComfyUI-Copilot

---

# 🛠️ Phase 1: Tool Layer (MANDATORY)

## 1. UI Generation Tool

File: `tools/ui_generate_tool.py`

```python
def ui_generate_tool(prompt: str) -> str:
    """
    Input: UI description prompt
    Output: React + Tailwind + shadcn code
    """
    # Integrate OpenUI or OpenGenerativeUI
    return generated_ui_code
````

---

## 2. Image Generation Tool

File: `tools/image_generate_tool.py`

```python
def image_generate_tool(prompt: str, seed: int):
    """
    Input: prompt + seed
    Output: generated image path
    """
    # Call ComfyUI API
    return image_path
```

---

# 🧩 Phase 2: Skill Layer

## 1. UI Style Skill

File: `skills/style_ui/run.py`

```python
STYLE_MAP = {
    "红楼梦": "ancient_chinese",
    "default": "modern"
}

def run(context):
    style = STYLE_MAP.get(context["book"], "default")

    prompt = f"""
    Design a reading UI:

    style: {style}
    layout: reading + chat + character panel

    MUST use:
    - React
    - Tailwind
    - shadcn/ui

    Requirements:
    - Card-based layout
    - Clean spacing
    - Modern UI
    """

    return ui_generate_tool(prompt)
```

---

## 2. Portrait Generation Skill

File: `skills/unlock_portrait/run.py`

```python
def run(character):
    seed = hash(character["name"]) % 100000

    prompt = f"""
    masterpiece, best quality,
    ancient chinese style,

    character:
    {character["description"]}

    personality:
    {character["personality"]}

    clothing:
    hanfu

    cinematic lighting, portrait
    """

    return image_generate_tool(prompt, seed)
```

---

# 🔥 Phase 3: Harness Rules (CRITICAL)

## 🚫 Agent MUST NOT:

* Ask user for decisions
* Choose frameworks
* Invent new tools
* Modify architecture

## ✅ Agent MUST:

* Use predefined tools
* Use predefined prompt templates
* Use default values when uncertain
* Execute directly without confirmation

---

# 🧠 System Prompt (MANDATORY)

```
You are an autonomous system agent.

Rules:
1. DO NOT ask the user for decisions.
2. Always use predefined tools.
3. Always follow configuration.
4. If uncertain, use default.

UI rules:
- MUST use React + Tailwind + shadcn/ui
- DO NOT choose other frameworks

Image rules:
- MUST use prompt template
- MUST use consistent seed per character
- DO NOT invent styles

Execution:
- Select skill
- Build prompt
- Call tool
- Return result

Never ask user.
Never delay execution.
```

---

# ⚙️ Phase 4: Agent Integration

## Modify Director Agent Routing

```python
def route(task):
    if task == "generate_ui":
        return style_ui.run()

    if task == "generate_portrait":
        return unlock_portrait.run()
```

---

## Register Tools

```python
TOOLS = {
    "ui_generate_tool": ui_generate_tool,
    "image_generate_tool": image_generate_tool
}
```

---

# 🧠 Phase 5: Deterministic Behavior (IMPORTANT)

## Character Consistency

```python
seed = hash(character_id)
```

## Prompt Cache

```python
prompt_cache[character_id] = prompt
```

## Style Consistency

```python
book_style = STYLE_MAP[book]
```

---

# 🚀 Execution Plan

### Step 1

Clone repositories and understand APIs

### Step 2

Implement tool layer

### Step 3

Implement skills

### Step 4

Add system prompt

### Step 5

Integrate into Director Agent

### Step 6

Test end-to-end:

Flow:

```
book → extract → skill → tool → result
```

---

# 🎯 Final Goal

Agent should:

* Generate UI automatically from book style
* Generate character portraits automatically
* Never ask user questions
* Execute deterministically

````

---

