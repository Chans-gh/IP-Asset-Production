"""Deterministic intent & reference analysis (SPEC §2.1, §2.2, G1; T01-T05, T19).

The router is rule-based on purpose: it never "decides" ambiguous identity questions on the
user's behalf. When something important is unclear it returns exactly one question
(SPEC §2.2 "只问一个最影响结果的确认问题"). A host LLM may refine the result, but must feed
the same ``CreationIntent`` structure back through :func:`analyze_intent`'s validation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .models import ReferenceImage

IDENTITY_ROLES = frozenset({"identity", "face", "silhouette"})

TRANSFORM_PAT = re.compile(
    r"(微调|改造|改成|改为|变成|衍生|二创|新角色|新形象|重新设计|参考.{0,6}(设计|创作|做)一个|基于.{0,12}(设计|改)|"
    r"transform|derive|variation|re-?design|based on)",
    re.I,
)
DIRECT_PAT = re.compile(
    r"(以(这些|这张|此)图为准|照着|就用|直接用|保持(一致|不变)|按图|原样|就是这个|as[- ]is|exactly|keep (it|the same))",
    re.I,
)
ORIGINAL_PAT = re.compile(r"(原创|设计一个|创造一个|从零|新\s*IP|帮我(想|设计|做)一个|invent|create a new)", re.I)

IP_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "digital_human",
        re.compile(r"(数字人|虚拟人|真人|写实人物|照片里的我|我自己|本人|digital human|photoreal)", re.I),
    ),
    (
        "fantasy_creature",
        re.compile(r"(精灵|小龙|龙|怪兽|妖怪|独角兽|幻想|魔法生物|dragon|sprite|monster|fairy)", re.I),
    ),
    (
        "cartoon_animal",
        re.compile(
            r"(动物|小熊|熊|猫|狗|犬|柴犬|柯基|狐狸|狼|兔|鸭|鸡|鸟|鹦鹉|猫头鹰|企鹅|熊猫|老虎|狮子|豹|松鼠|仓鼠|鼠|"
            r"猴|鹿|羊|羊驼|牛|马|猪|鱼|鲸|海豹|海獭|水獭|考拉|树袋熊|刺猬|浣熊|河马|大象|象|长颈鹿|青蛙|蛙|龟|"
            r"bear|cat|dog|puppy|shiba|corgi|fox|wolf|rabbit|bunny|duck|bird|owl|penguin|panda|tiger|lion|"
            r"squirrel|hamster|mouse|monkey|deer|sheep|alpaca|cow|horse|pig|fish|whale|seal|otter|koala|"
            r"hedgehog|raccoon|elephant|giraffe|frog|turtle|animal)",
            re.I,
        ),
    ),
    (
        "anthropomorphic_object",
        re.compile(r"(拟人|杯|云朵|云|瓶|面包|饭团|水果|苹果|灯泡|书本|机器|物体|cup|cloud|bottle|object)", re.I),
    ),
    ("anime_human", re.compile(r"(动漫|二次元|少女|少年|女孩|男孩|人物|角色形象|anime|manga|girl|boy)", re.I)),
]
LIMBLESS_PAT = re.compile(r"(无腿|没有腿|没腿|无四肢|没有手脚|无手无脚|无肢体|史莱姆|团子|云朵|limbless|no legs)", re.I)
QUADRUPED_PAT = re.compile(r"(四足|四条腿|四脚着地|爬行|quadruped|on all fours)", re.I)
WINGED_PAT = re.compile(r"(翅膀|有翼|飞行|鸟|wings?|winged)", re.I)
USE_CASE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("emoji", re.compile(r"(表情包|表情贴|emoji|sticker pack)", re.I)),
    ("door_sign", re.compile(r"(门牌|会议室|meeting room|door sign)", re.I)),
    ("office_signage", re.compile(r"(导视|指示牌|办公区标识|signage)", re.I)),
    ("social", re.compile(r"(头像|封面|横幅|社交账号|公众号|小红书|avatar|banner)", re.I)),
    ("live_stream", re.compile(r"(直播|贴片|口播|live ?stream|overlay)", re.I)),
    ("holiday_poster", re.compile(r"(海报|节日|春节|中秋|圣诞|poster|holiday)", re.I)),
    ("wallpaper", re.compile(r"(壁纸|wallpaper)", re.I)),
    ("sticker_print", re.compile(r"(贴纸|手账|印刷周边|sticker)", re.I)),
    ("notice_sign", re.compile(r"(欢迎牌|提示牌|欢迎光临|请保持安静|notice)", re.I)),
    ("brand", re.compile(r"(品牌手册|角色介绍|介绍页|brand)", re.I)),
    ("animation", re.compile(r"(动画|视频制作|口型|拆件|animation)", re.I)),
    ("merchandise", re.compile(r"(周边|公仔|盲盒|毛绒玩具|merch|toy)", re.I)),
    ("full_set", re.compile(r"(全套|所有资产|全部资产|完整资产|full set)", re.I)),
]


@dataclass(frozen=True)
class Conflict:
    code: str
    detail: str
    ref_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreationIntent:
    mode: str
    mode_confidence: float
    ip_type: str | None
    body_topology: str | None
    use_cases: tuple[str, ...]
    reference_roles: dict[str, tuple[str, ...]]
    primary_subject: str | None
    conflicts: tuple[Conflict, ...] = ()
    needs_rights_confirmation: bool = False
    needs_style_confirmation: bool = False
    question: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def g1_satisfied(self) -> bool:
        """G1: mode/type clear and reference conflicts resolved."""
        return self.question is None and not self.conflicts and self.ip_type is not None


def _first_match(rules: list[tuple[str, re.Pattern[str]]], text: str) -> str | None:
    for value, pat in rules:
        if pat.search(text):
            return value
    return None


def guess_topology(ip_type: str | None, text: str) -> str | None:
    if LIMBLESS_PAT.search(text):
        return "limbless"
    if ip_type in ("digital_human", "anime_human"):
        return "humanoid"
    if QUADRUPED_PAT.search(text):
        return "quadruped"
    if WINGED_PAT.search(text) and ip_type in ("cartoon_animal", "fantasy_creature"):
        return "winged"
    if ip_type == "cartoon_animal":
        return "biped_animal"
    if ip_type == "anthropomorphic_object":
        return "object_with_limbs"
    if ip_type == "fantasy_creature":
        return "custom"
    return None


def reference_conflicts(refs: Sequence[ReferenceImage]) -> tuple[tuple[Conflict, ...], str | None]:
    """Detect identity fusion risks and same-subject structure conflicts (SPEC §2.2, T04)."""
    conflicts: list[Conflict] = []
    identity_refs = [r for r in refs if r.role in IDENTITY_ROLES]
    subjects = {r.subject_id or "unspecified" for r in identity_refs}
    primary = None
    if len(subjects) > 1:
        conflicts.append(
            Conflict(
                "multiple_identity_subjects",
                f"身份类参考图来自不同主体 {sorted(subjects)}；不会自动混合多个角色的身份特征",
                tuple(r.ref_id for r in identity_refs),
            )
        )
    elif subjects:
        primary = next(iter(subjects))
    by_subject: dict[str, list[ReferenceImage]] = {}
    for r in identity_refs:
        by_subject.setdefault(r.subject_id or "unspecified", []).append(r)
    for subj, group in by_subject.items():
        roles = {r.role for r in group}
        if "identity" in roles and "silhouette" in roles:
            top = sorted(group, key=lambda r: -(r.priority or 0))
            if len(top) > 1 and (top[0].priority or 0) == (top[1].priority or 0):
                conflicts.append(
                    Conflict(
                        "identity_structure_conflict",
                        f"主体 {subj} 的身份图与轮廓图优先级相同，需要指定以哪张为准",
                        tuple(r.ref_id for r in group),
                    )
                )
    return tuple(conflicts), primary


def analyze_intent(message: str, references: Sequence[ReferenceImage] = ()) -> CreationIntent:
    """SPEC §9.2 ``analyze_intent(user_message, reference_manifest) -> CreationIntent``."""
    text = message or ""
    notes: list[str] = []
    refs = list(references)
    ids = [r.ref_id for r in refs]
    if len(set(ids)) != len(ids):
        raise ValueError("reference ref_id values must be unique")

    if not refs:
        mode, conf = "ORIGINAL_CREATE", 0.95 if ORIGINAL_PAT.search(text) else 0.8
        if TRANSFORM_PAT.search(text) or DIRECT_PAT.search(text):
            notes.append("提到参考图但没有收到图片：按原创处理，可随时补充参考图")
    elif TRANSFORM_PAT.search(text):
        mode, conf = "REFERENCE_TRANSFORM", 0.9
    elif DIRECT_PAT.search(text):
        mode, conf = "REFERENCE_DIRECT", 0.9
    else:
        mode, conf = "REFERENCE_DIRECT", 0.55

    ip_type = _first_match(IP_TYPE_RULES, text)
    if ip_type is None and refs and any(r.role == "face" for r in refs):
        notes.append("含 face 角色参考但未说明类型")
    topology = guess_topology(ip_type, text)
    use_cases = tuple(uc for uc, pat in USE_CASE_RULES if pat.search(text))

    roles: dict[str, list[str]] = {}
    for r in refs:
        roles.setdefault(r.role, []).append(r.ref_id)
    conflicts, primary = reference_conflicts(refs)

    has_identity_ref = any(r.role in IDENTITY_ROLES for r in refs)
    needs_rights = has_identity_ref and (ip_type in (None, "digital_human") or bool(re.search("真人|照片|本人", text)))
    needs_style = ip_type is not None and ip_type != "digital_human"

    question: str | None = None
    if any(c.code == "multiple_identity_subjects" for c in conflicts):
        question = "这些身份参考图来自不同角色。请指定以哪一个角色为主体（其余图片只作风格/服装/姿态参考）？"
    elif any(c.code == "identity_structure_conflict" for c in conflicts):
        question = "身份图与轮廓图冲突时以哪一张为准？"
    elif refs and conf < 0.6:
        question = "请确认：直接以这些参考图中的角色为准制作资产（直接创建），还是参考它们改出一个新角色（微调创建）？"
    elif mode == "REFERENCE_TRANSFORM" and not re.search(r"(保留|保持|不变|keep)", text):
        question = "微调创建需要明确边界：哪些特征必须保留、哪些要改？"
    elif ip_type is None:
        question = "这个 IP 是数字人（写实真人风格），还是卡通/动漫角色（人物、动物或拟人物体）？"
    elif needs_rights:
        question = "参考图含有可辨认的人物。请确认你拥有这些照片和肖像的使用权限（如涉及他人，已获得同意）。"

    return CreationIntent(
        mode=mode,
        mode_confidence=conf,
        ip_type=ip_type,
        body_topology=topology,
        use_cases=use_cases,
        reference_roles={k: tuple(v) for k, v in roles.items()},
        primary_subject=primary,
        conflicts=conflicts,
        needs_rights_confirmation=needs_rights,
        needs_style_confirmation=needs_style,
        question=question,
        notes=tuple(notes),
    )
