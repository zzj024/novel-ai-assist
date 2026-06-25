"""LLM Prompt 模板——章节结构化提取"""

PROMPT_VERSION = "1.1.0"

# ── System Prompt 
# 角色定义 + 行为约束 + 输出规范
SYSTEM_PROMPT = """你是一个长篇小说分析工具。你的职责是从给定的章节正文中提取结构化信息。

## 核心原则
- 你是分析工具，禁止生成、禁止续写、禁止修改任何小说正文
- 只提取本章中**明确出现**的信息，禁止跨章脑补，禁止推断未发生的事件
- 如果某个信息在正文中没有明确依据，禁止虚构

## 提取要求
- 每个提取项必须附带 evidence字段，内容为原文中对应的30字以内依据
- 人物状态只记录本章结束时可见的状态
- 关系只记录本章中主动提及或发生互动的关系
- 伏笔只记录本章中明显埋设但未回收的设定/事件/对话

## 输出要求
- 严格按照 OUTPUT_SCHEMA 的 JSON 格式输出
- 禁止输出任何解释性文字，只输出 JSON
- 如果某个字段在正文中无对应内容，使用空数组 [] 禁止使用null"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description":"本章标题（如有），否则留空字符串"
        },
        "summary": {
            "type": "string",
            "description":"本章核心事件概述（50字以内）"
        },
        "plot_flow": {
            "type": "array",
            "description":"本章剧情流向，按叙事顺序排列",
            "items": {
                "type": "object",
                "properties": {
                    "order": {
                        "type": "integer",
                        "description":"叙事顺序（从1递增）"
                    },
                    "stage": {
                        "type": "string",
                        "description": "剧情阶段标签"
                    },
                    "description": {
                        "type": "string",
                        "description":"该阶段的事件描述"
                    },
                    "characters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description":"参与的角色名列表"
                    },
                    "location": {
                        "type": "string",
                        "description": "事件发生地点"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    }
                },
                "required": ["order", "stage","description"]
            }
        },
        "characters": {
            "type": "array",
            "description": "本章出现或提及的角色列表",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "角色名"
                    },
                    "aliases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description":"本章使用的别名列表"
                    },
                    "status": {
                        "type": "object",
                        "properties": {
                            "physical": {
                                "type": "string",
                                "description":"身体状况"
                            },
                            "emotional": {
                                "type": "string",
                                "description":"情绪状态"
                            },
                            "social": {
                                "type": "string",
                                "description":"社会关系状态（独行/组队/被追捕……）"
                            },
                            "location": {
                                "type": "string",
                                "description":"当前位置"
                            }
                        },
                        "description":"角色在本章结束时的状态快照"
                    },
                    "description": {
                        "type": "string",
                        "description": "角色简短描述"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    }
                },
                "required": ["name", "status"]
            }
        },
        "relations": {
            "type": "array",
            "description":"本章出现或明确提及的人物关系",
            "items": {
                "type": "object",
                "properties": {
                    "char_a": {
                        "type": "string",
                        "description": "角色A"
                    },
                    "char_b": {
                        "type": "string",
                        "description": "角色B"
                    },
                    "relation": {
                        "type": "string",
                        "description":"关系类型：师徒/敌对/爱慕/青梅竹马/暧昧/暗恋/单恋/盟友/宿敌/仇敌/同族/同门/主仆/旧识/同僚/其他"
                    },
                    "detail": {
                        "type": "string",
                        "description": "关系补充描述"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    }
                },
                "required": ["char_a", "char_b","relation"]
            }
        },
        "timeline_events": {
            "type": "array",
            "description":"本章发生的事件列表，按叙事顺序",
            "items": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "事件描述"
                    },
                    "story_time": {
                        "type": "string",
                        "description":"故事内时间描述（如'第二天''三年后'）"
                    },
                    "narrative_order": {
                        "type": "integer",
                        "description":"本章叙事顺序（从1递增，对应 plot_flow.order）"
                    },
                    "characters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description":"参与的角色名列表"
                    },
                    "location": {
                        "type": "string",
                        "description": "事件发生地点"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    }
                },
                "required": ["event", "narrative_order"]
            }
        },
        "foreshadowings": {
            "type": "array",
            "description": "本章埋设的伏笔",
            "items": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "伏笔描述"
                    },
                    "related_chars": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "相关角色名列表"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "置信度 0.0~1.0"
                    },
                    "confidence_label": {
                        "type": "string",
                        "enum": ["low", "medium","high"],
                        "description": "置信度标签"
                    }
                },
                "required": ["description"]
            }
        },
        "episodic_entities": {
            "type": "array",
            "description": "本章中以描述性方式出现的角色（如'黑衣人''白衣女子'），非名字形式",
            "items": {
                "type": "object",
                "properties": {
                    "descriptor": {
                        "type": "string",
                        "description": "描述符（如'黑衣人'）"
                    },
                    "resolved_to": {
                        "type": "string",
                        "description": "如果该描述指代某个已知角色，填角色名；否则留空"
                    },
                    "context": {
                        "type": "string",
                        "description": "简短上下文（如'一个黑衣男子出现在山巅'）"
                    },
                    "evidence": {
                        "type": "string",
                        "description": "原文依据（30字以内）"
                    }
                },
                "required": ["descriptor"]
            }
        },
        "unresolved_questions": {
            "type": "array",
            "description": "本章结束后仍未解答的问题",
            "items": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "未解问题描述"
                    },
                    "related_chars": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "相关问题角色"
                    },
                    "evidence": {
                        "type": "string",
                        "description":"原文依据（30字以内）"
                    }
                },
                "required": ["question"]
            }
        },
        "meta": {
            "type": "object",
            "description": "解析元信息",
            "properties": {
                "truncated": {
                    "type": "boolean",
                    "description": "正文是否被截断"
                },
                "truncation_strategy": {
                    "type": "string",
                    "description": "截断策略（如head_middle_tail）"
                },
                "warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description":"解析过程中的警告列表"
                }
            }
        }
    },
    "required": [
        "title", "characters", "relations",
        "timeline_events", "foreshadowings"
    ]
}

def build_extract_messages(chapter_text: str) -> list[dict]:
    """构建发送给 LLM 的消息列表

    参数：
        chapter_text: 完整的章节正文（已做 token 截断处理）

    返回：
        list[dict]: 包含 system 和 user 两条消息的列表
    """
    import json

    schema_str = json.dumps(
        OUTPUT_SCHEMA, ensure_ascii=False, indent=2
    )

    user_prompt = (
        "请从以下章节正文中提取结构化信息，"
        "严格按照 OUTPUT_SCHEMA 的格式输出 JSON。\n\n"
        f"章节正文：\n{chapter_text}\n\n"
        f"OUTPUT_SCHEMA：\n{schema_str}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

