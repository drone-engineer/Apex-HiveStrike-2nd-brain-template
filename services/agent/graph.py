import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

class KnowledgeState(TypedDict):
    doc_id: str
    title: str
    raw_content: str
    category: str
    triage_notes: Optional[str]
    is_human_verified: bool
    final_path: Optional[str]

def triage_node(state: KnowledgeState) -> KnowledgeState:
    print(f"\n[Node: Triage] Analyzing: {state['title']}")
    state["triage_notes"] = f"Auto-triaged for {state['category']}. Validated structure."
    return state

def human_review_gate(state: KnowledgeState) -> KnowledgeState:
    print(f"[Node: Human Review Gate] Checking verification flag...")
    if state.get("is_human_verified", False):
        folder = f"knowledge/02_Canonical/{state['category']}"
        status_str = "verified"
        reviewed_str = "true"
    else:
        folder = f"knowledge/03_Discovery/{state['category']}"
        status_str = "draft"
        reviewed_str = "false"
        
    os.makedirs(folder, exist_ok=True)
    file_path = f"{folder}/{state['doc_id']}.md"
    state["final_path"] = file_path
    
    # 2nd-Brain YAML Frontmatter 규격 준수 마크다운 생성
    md_content = f"""---
id: {state['doc_id']}
title: {state['title']}
status: {status_str}
reviewed: {reviewed_str}
category: {state['category']}
tags: [ros2, px4, autonomy, generated]
---

# {state['title']}

- 상위 인덱스: [[Index]]
- 처리 노트: {state['triage_notes']}

## 본문 요약
{state['raw_content']}
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"[File Writer] Saved document to -> {file_path}")
    return state

def routing_condition(state: KnowledgeState) -> str:
    if state.get("is_human_verified", False):
        return "promote_canonical"
    return "keep_discovery"

def promote_canonical_node(state: KnowledgeState) -> KnowledgeState:
    print(f"[Node: Promote Canonical] Successfully stored in SSOT (02_Canonical)")
    return state

def keep_discovery_node(state: KnowledgeState) -> KnowledgeState:
    print(f"[Node: Keep Discovery] Successfully queued in 03_Discovery")
    return state

# 그래프 조립
workflow = StateGraph(KnowledgeState)
workflow.add_node("triage", triage_node)
workflow.add_node("review_gate", human_review_gate)
workflow.add_node("promote_canonical", promote_canonical_node)
workflow.add_node("keep_discovery", keep_discovery_node)

workflow.set_entry_point("triage")
workflow.add_edge("triage", "review_gate")

workflow.add_conditional_edges(
    "review_gate",
    routing_condition,
    {
        "promote_canonical": "promote_canonical",
        "keep_discovery": "keep_discovery"
    }
)
workflow.add_edge("promote_canonical", END)
workflow.add_edge("keep_discovery", END)

app = workflow.compile()

if __name__ == "__main__":
    test_data: KnowledgeState = {
        "doc_id": "DISC-ROS2-XRCE-001",
        "title": "Micro-XRCE-DDS Communication Guide",
        "raw_content": "PX4 to ROS2 offboard control requires Micro-XRCE-DDS Agent running with 921600 baudrate.",
        "category": "02_Autonomy_ROS",
        "triage_notes": None,
        "is_human_verified": False,
        "final_path": None
    }
    app.invoke(test_data)
