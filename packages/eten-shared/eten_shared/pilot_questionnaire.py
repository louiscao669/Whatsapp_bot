"""Background and eligibility questionnaire for the ``/pilot`` study.

Approved under IRB protocol 26-08-10268 (Exempt Cat. 3, approved 2026-09-04):
the approved packet contains ONLY the English master
``Eligibility_Screening_Questionnaire_EN_v1_1`` (v1.0, 2026-08-31). The ``en``
strings below follow it.

  * **English is the default** (``DEFAULT_LANGUAGE``), switched 2026-10-26.
    No Chinese version was attached to the approved protocol, and protocol §5b
    requires English proficiency. The ``zh`` strings (Claude's translation of
    A-C and the Section C prompt; Section D from the PRESURVEY_DEMOGRAPHICS
    draft) are kept but must not be served (``PILOT_QUESTIONNAIRE_LANGUAGE=zh``)
    unless a Chinese version is approved.
  * Item and option wording in ``en`` is verbatim from the approved PDF. The
    screen chrome (buttons, step label, the Section C consent-prompt wording,
    the screen-out message) is not in the approved packet.
  * ``Questionnaire_Administration_Note_EN_v1`` (screen-out handling, D key)
    was NOT part of the approved packet. The screen-out rule rests on protocol
    §6a step 5: "No identifiable information is retained from anyone who proves
    ineligible."

Rules implemented here:

  * Section A is required; eligibility is decided by Section A only.
    A1 = yes, A2 in {mandarin, other_chinese}, A3 != not_comfortable.
  * Sections B-D are optional item by item.
  * Section C is preceded by its own consent prompt (stated in the approved
    questionnaire); declining skips to D.
  * Section D is scored server-side only. The key never leaves this module:
    :func:`public_instrument` strips it, and no response ever reports a score
    to the participant (approved questionnaire: "Participants are never shown
    their score").

Codes (option values and item ids) are the stable data contract. Labels may
change without touching stored data.
"""

from __future__ import annotations

from typing import Dict, List, Optional

INSTRUMENT_VERSION = "bgq-en-v1.0-2026-08-31"
DEFAULT_LANGUAGE = "en"  # the approved instrument is English-only (IRB 26-08-10268)

PREFER_NOT = {"code": "prefer_not_to_say", "zh": "不愿透露", "en": "Prefer not to say"}
NOT_SURE = {"code": "not_sure", "zh": "不确定", "en": "Not sure"}

#: Ordered steps. ``eligibility`` is Section A, then B, then the Section C
#: consent prompt + C items (one step), then D.
STEPS = ("eligibility", "background", "religion", "familiarity")


def _opt(code, zh, en):
    return {"code": code, "zh": zh, "en": en}


SECTIONS: List[dict] = [
    {
        "id": "eligibility",
        "label": "A",
        "title": {"zh": "第一部分：参与资格", "en": "Section A — Eligibility"},
        "intro": {"zh": "以下问题必须回答。", "en": "Required."},
        "required": True,
        "items": [
            {
                "id": "a1_age_18_plus",
                "type": "single",
                "text": {"zh": "您是否年满18岁？", "en": "Are you 18 years of age or older?"},
                "options": [_opt("yes", "是", "Yes"), _opt("no", "否", "No")],
            },
            {
                "id": "a2_first_language",
                "type": "single",
                "text": {
                    "zh": "普通话（汉语）是您的第一语言（母语）吗？",
                    "en": "Is Mandarin Chinese your first (native) language?",
                },
                "options": [
                    _opt("mandarin", "是", "Yes"),
                    _opt(
                        "other_chinese",
                        "另一种汉语方言或变体（请注明）",
                        "Another Chinese variety — please specify:",
                    ),
                    _opt("no", "否", "No"),
                ],
                # Free text shown when this option is chosen. Optional: the
                # instrument asks for it but eligibility does not depend on it.
                "specify": {"option": "other_chinese", "id": "a2_other_variety"},
            },
            {
                "id": "a3_reading_comfort",
                "type": "single",
                "text": {
                    "zh": "您阅读中文文字的舒适程度如何？",
                    "en": "How comfortable are you reading Chinese text?",
                },
                "help": {
                    "zh": "本研究的所有段落和问题都以书面文字呈现。",
                    "en": "All study passages and questions are delivered as written text.",
                },
                "options": [
                    _opt("very_comfortable", "非常舒适", "Very comfortable"),
                    _opt("comfortable", "舒适", "Comfortable"),
                    _opt("somewhat_comfortable", "还算舒适", "Somewhat comfortable"),
                    _opt("not_comfortable", "不舒适", "Not comfortable"),
                ],
            },
        ],
    },
    {
        "id": "background",
        "label": "B",
        "title": {"zh": "第二部分：背景信息", "en": "Section B — Background"},
        "intro": {
            "zh": "选填，仅用于描述参与者的整体情况。任何问题都可以跳过。",
            "en": "Optional. Used to describe the sample. Any item may be skipped.",
        },
        "required": False,
        "items": [
            {
                "id": "b1_age_band",
                "type": "single",
                "text": {"zh": "年龄", "en": "Age"},
                "options": [
                    _opt("18_24", "18–24岁", "18–24"),
                    _opt("25_34", "25–34岁", "25–34"),
                    _opt("35_44", "35–44岁", "35–44"),
                    _opt("45_54", "45–54岁", "45–54"),
                    _opt("55_64", "55–64岁", "55–64"),
                    _opt("65_plus", "65岁或以上", "65 or older"),
                    PREFER_NOT,
                ],
            },
            {
                "id": "b2_education",
                "type": "single",
                "text": {"zh": "您已完成的最高学历", "en": "Highest level of education completed"},
                "options": [
                    _opt("less_than_secondary", "未完成中学", "Less than secondary school"),
                    _opt("secondary", "中学／高中", "Secondary / high school"),
                    _opt("some_college", "读过大学但未获学位", "Some college or university"),
                    _opt("bachelors", "学士学位", "Bachelor's degree"),
                    _opt("graduate", "研究生学位", "Graduate degree"),
                    PREFER_NOT,
                ],
            },
            {
                "id": "b3_country_region",
                "type": "text_or_prefer_not",
                "text": {"zh": "您目前居住的国家或地区", "en": "Country or region of residence"},
                "max_length": 120,
            },
        ],
    },
    {
        "id": "religion",
        "label": "C",
        "title": {
            "zh": "第三部分：宗教背景及对原文的熟悉程度",
            "en": "Section C — Religious Background and Familiarity with the Source Material",
        },
        "intro": {
            "zh": "选填。每个问题都可以跳过，也都可以选择“不愿透露”。",
            "en": "Optional and sensitive. A separate consent prompt precedes this section. "
            "Every item may be skipped, and every item offers "
            "\"Prefer not to say.\" Declining this section in whole or in part has no effect "
            "on participation or compensation.",
        },
        # Shown as its own screen before the items (administration note:
        # "A separate consent prompt is presented immediately before Section C").
        "consent_prompt": {
            "zh": "接下来的几个问题涉及您的宗教信仰和宗教活动，属于敏感信息。"
            "这些问题全部为选填。是否回答、回答多少，都不会影响您参与本研究，也不会影响您的报酬。"
            "您愿意回答这一部分吗？",
            "en": "The next questions ask about your religious affiliation and practice, "
            "which is sensitive information. They are all optional. Whether you answer "
            "them, in whole or in part, has no effect on your participation or your "
            "payment. Do you agree to answer this section?",
            "agree": {"zh": "愿意回答", "en": "Yes, I agree to answer"},
            "decline": {"zh": "跳过这一部分", "en": "No, skip this section"},
        },
        "required": False,
        "items": [
            {
                "id": "c1_religious_affiliation",
                "type": "single",
                "text": {"zh": "您的宗教信仰", "en": "Religious affiliation"},
                "options": [
                    _opt("christian_protestant", "基督教（新教）", "Christian — Protestant"),
                    _opt("christian_catholic", "天主教", "Christian — Catholic"),
                    _opt(
                        "christian_orthodox_other",
                        "东正教或其他基督宗教",
                        "Christian — Orthodox or other",
                    ),
                    _opt("another_religion", "其他宗教", "Another religion"),
                    _opt("no_religion", "无宗教信仰", "No religion / not religious"),
                    PREFER_NOT,
                ],
            },
            {
                "id": "c2_service_attendance",
                "type": "single",
                "text": {
                    "zh": "您目前多久参加一次宗教聚会或礼拜？",
                    "en": "How often do you currently attend religious services?",
                },
                "options": [
                    _opt("never", "从不", "Never"),
                    _opt("few_times_year", "一年几次", "A few times a year"),
                    _opt("monthly", "大约每月一次", "About monthly"),
                    _opt("weekly", "大约每周一次", "About weekly"),
                    _opt("more_than_weekly", "每周不止一次", "More than weekly"),
                    PREFER_NOT,
                ],
            },
            {
                "id": "c3_bible_frequency",
                "type": "single",
                "text": {
                    "zh": "您多久阅读或聆听一次圣经（任何语言）？",
                    "en": "How often do you read or listen to the Bible, in any language?",
                },
                "options": [
                    _opt("never", "从不", "Never"),
                    _opt("rarely", "很少", "Rarely"),
                    _opt("few_times_year", "一年几次", "A few times a year"),
                    _opt("monthly", "每月", "Monthly"),
                    _opt("weekly", "每周", "Weekly"),
                    _opt("daily", "每天", "Daily"),
                    PREFER_NOT,
                ],
            },
            {
                "id": "c4_chinese_bible",
                "type": "single",
                "text": {
                    "zh": "您是否读过或听过中文圣经？",
                    "en": "Have you read or heard the Bible in Chinese specifically?",
                },
                "options": [
                    _opt("regularly", "经常", "Regularly"),
                    _opt("occasionally", "偶尔", "Occasionally"),
                    _opt("once_or_twice", "一两次", "Once or twice"),
                    _opt("never", "从未", "Never"),
                    PREFER_NOT,
                ],
            },
        ],
    },
    {
        "id": "familiarity",
        "label": "D",
        "title": {"zh": "第四部分：熟悉程度小测验", "en": "Section D — Familiarity Quiz"},
        "intro": {
            "zh": "选填。共七道选择题。如果不确定，请选择“不确定”，不必猜测。不会向您显示得分。",
            "en": "Optional. Seven multiple-choice items measuring prior knowledge of the source "
            "material, used as an analysis covariate. Not an eligibility criterion. \"Not sure\" "
            "is offered on every item so that participants with little familiarity are not "
            "required to guess. Participants are never shown their score. Items are drawn from "
            "portions of the source text that do not appear anywhere in the study passages.",
        },
        "required": False,
        "items": [
            {
                "id": "d1_good_samaritan",
                "type": "single",
                "text": {
                    "zh": "在耶稣的比喻中，一个人受伤倒在路旁，祭司和利未人都走过去不理会。最后是谁停下来帮助他？",
                    "en": "In the parable, a wounded man lies by the road, and a priest and a "
                    "Levite pass by without helping. Who finally stops to help him?",
                },
                "options": [
                    _opt("a", "一个祭司", "A priest"),
                    _opt("b", "一个撒玛利亚人", "A Samaritan"),
                    _opt("c", "一个法利赛人", "A Pharisee"),
                    _opt("d", "一个税吏", "A tax collector"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d2_prodigal_son",
                "type": "single",
                "text": {
                    "zh": "在“浪子回头”的比喻中，小儿子挥霍完财产后回家，父亲如何对待他？",
                    "en": "In the parable of the prodigal son, the younger son returns home after "
                    "wasting his inheritance. How does his father treat him?",
                },
                "options": [
                    _opt("a", "把他赶走", "Turns him away"),
                    _opt("b", "罚他做仆人", "Makes him a hired servant"),
                    _opt("c", "欢喜地迎接他并摆设宴席", "Welcomes him joyfully with a feast"),
                    _opt("d", "不肯认他", "Refuses to acknowledge him"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d3_zacchaeus_tree",
                "type": "single",
                "text": {
                    "zh": "税吏撒该个子矮，为了看见耶稣，他爬上了哪一种树？",
                    "en": "Zacchaeus the tax collector was short. Which kind of tree did he "
                    "climb in order to see Jesus?",
                },
                "options": [
                    _opt("a", "无花果树", "A fig tree"),
                    _opt("b", "橄榄树", "An olive tree"),
                    _opt("c", "桑树", "A sycamore tree"),
                    _opt("d", "棕榈树", "A palm tree"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d4_emmaus",
                "type": "single",
                "text": {
                    "zh": "耶稣复活后与两个门徒同行，走在往哪个村子的路上？",
                    "en": "After the resurrection, Jesus walks with two disciples along the road "
                    "to which village?",
                },
                "options": [
                    _opt("a", "耶利哥", "Jericho"),
                    _opt("b", "以马忤斯", "Emmaus"),
                    _opt("c", "伯大尼", "Bethany"),
                    _opt("d", "拿撒勒", "Nazareth"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d5_lazarus",
                "type": "single",
                "text": {
                    "zh": "在财主和讨饭的比喻中，躺在财主门口的穷人叫什么名字？",
                    "en": "In the parable of the rich man and the beggar, what is the name of "
                    "the beggar who lay at the rich man's gate?",
                },
                "options": [
                    _opt("a", "拉撒路", "Lazarus"),
                    _opt("b", "尼哥底母", "Nicodemus"),
                    _opt("c", "巴拿巴", "Barnabas"),
                    _opt("d", "亚居拉", "Aquila"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d6_ten_lepers",
                "type": "single",
                "text": {
                    "zh": "耶稣洁净了十个长大麻风的人，有几个回来感谢他？",
                    "en": "Jesus healed ten men of leprosy. How many came back to thank him?",
                },
                "options": [
                    _opt("a", "十个都回来", "All ten"),
                    _opt("b", "五个", "Five"),
                    _opt("c", "一个", "One"),
                    _opt("d", "一个也没有", "None"),
                    NOT_SURE,
                ],
            },
            {
                "id": "d7_repentant_criminal",
                "type": "single",
                "text": {
                    "zh": "耶稣被钉十字架时，对身旁那个悔改的犯人说了什么？",
                    "en": "At the crucifixion, what did Jesus say to the repentant criminal "
                    "beside him?",
                },
                "options": [
                    _opt("a", "“你的罪赦了。”", "\"Your sins are forgiven.\""),
                    _opt("b", "“今日你要同我在乐园里了。”", "\"Today you will be with me in paradise.\""),
                    _opt("c", "“你为什么不救自己？”", "\"Why do you not save yourself?\""),
                    _opt("d", "“起来行走吧。”", "\"Rise up and walk.\""),
                    NOT_SURE,
                ],
            },
        ],
    },
]

#: Section D key (administration note, reviewer reference). Server-side only.
_FAMILIARITY_KEY: Dict[str, str] = {
    "d1_good_samaritan": "b",
    "d2_prodigal_son": "c",
    "d3_zacchaeus_tree": "c",
    "d4_emmaus": "b",
    "d5_lazarus": "a",
    "d6_ten_lepers": "c",
    "d7_repentant_criminal": "b",
}

ELIGIBLE_FIRST_LANGUAGE = {"mandarin", "other_chinese"}
INELIGIBLE_READING = {"not_comfortable"}

UI_TEXT = {
    "zh": {
        "heading": "背景问卷",
        "intro": "开始阅读之前，请先回答几个简短的问题（大约3–10分钟）。",
        "continue": "继续",
        "finish": "完成，开始阅读",
        "required_missing": "请回答本部分的所有问题后再继续。",
        "specify_placeholder": "请注明",
        "text_placeholder": "请填写",
        "saving": "正在保存……",
        "screened_out_title": "感谢您的关注",
        "screened_out_body": "本研究需要年满18岁、以汉语为第一语言、并能较舒适地阅读中文的参与者。"
        "根据您的回答，您不符合本研究的参与条件，因此不会再向您提出其他问题。"
        "您的回答已被删除。您可以关闭此页面。",
        "step": "第{n}部分，共{total}部分",
    },
    "en": {
        "heading": "Background questionnaire",
        "intro": "Before the reading begins, please answer a few short questions (about 3–10 minutes).",
        "continue": "Continue",
        "finish": "Finish and start reading",
        "required_missing": "Please answer every question in this section to continue.",
        "specify_placeholder": "Please specify",
        "text_placeholder": "Type here",
        "saving": "Saving…",
        "screened_out_title": "Thank you for your interest",
        "screened_out_body": "This study needs readers who are 18 or older, whose first language is "
        "Chinese, and who are comfortable reading Chinese. Based on your answers you are not "
        "eligible, so no further questions will be asked. Your answers have been deleted. You "
        "can close this page.",
        "step": "Part {n} of {total}",
    },
}


class QuestionnaireValidationError(ValueError):
    """The submitted answers do not fit the instrument."""


def section(section_id: str) -> dict:
    for entry in SECTIONS:
        if entry["id"] == section_id:
            return entry
    raise QuestionnaireValidationError(f"Unknown questionnaire section '{section_id}'")


def public_instrument(language: str = DEFAULT_LANGUAGE) -> dict:
    """Everything the client renders. Contains no answer key and no score."""

    language = language if language in UI_TEXT else DEFAULT_LANGUAGE
    return {
        "version": INSTRUMENT_VERSION,
        "language": language,
        "ui": UI_TEXT[language],
        "sections": [
            {
                key: value
                for key, value in entry.items()
            }
            for entry in SECTIONS
        ],
    }


def _item_ids(entry: dict) -> List[str]:
    ids = []
    for item in entry["items"]:
        ids.append(item["id"])
        if item.get("specify"):
            ids.append(item["specify"]["id"])
    return ids


def _clean_text(value, max_length: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise QuestionnaireValidationError("Text answers must be strings")
    value = " ".join(value.split())
    if not value:
        return None
    return value[:max_length]


def validate_section_answers(section_id: str, answers) -> Dict[str, Optional[str]]:
    """Normalise one section's answers to ``{item_id: code-or-text-or-None}``.

    Unknown item ids and unknown option codes are refused rather than dropped,
    so a client bug can never silently lose or invent data. Required sections
    must answer every item.
    """

    entry = section(section_id)
    if answers is None:
        answers = {}
    if not isinstance(answers, dict):
        raise QuestionnaireValidationError("answers must be an object")
    allowed = set(_item_ids(entry))
    unknown = sorted(set(answers) - allowed)
    if unknown:
        raise QuestionnaireValidationError(f"Unknown item(s): {', '.join(unknown)}")

    cleaned: Dict[str, Optional[str]] = {}
    for item in entry["items"]:
        raw = answers.get(item["id"])
        if item["type"] == "single":
            codes = {option["code"] for option in item["options"]}
            if raw in (None, ""):
                value = None
            elif raw in codes:
                value = raw
            else:
                raise QuestionnaireValidationError(
                    f"'{raw}' is not an option for {item['id']}"
                )
        elif item["type"] == "text_or_prefer_not":
            if raw == PREFER_NOT["code"]:
                value = raw
            else:
                value = _clean_text(raw, item.get("max_length", 120))
        else:  # pragma: no cover - instrument definition error
            raise QuestionnaireValidationError(f"Unsupported item type {item['type']}")

        if entry["required"] and value is None:
            raise QuestionnaireValidationError(f"{item['id']} is required")
        cleaned[item["id"]] = value

        specify = item.get("specify")
        if specify:
            text = _clean_text(answers.get(specify["id"]), 120)
            # Only kept when the option it qualifies is the one chosen.
            cleaned[specify["id"]] = text if value == specify["option"] else None
    return cleaned


def is_eligible(eligibility_answers: Dict[str, Optional[str]]) -> bool:
    """Section A screening rule from the administration note v1.0."""

    return (
        eligibility_answers.get("a1_age_18_plus") == "yes"
        and eligibility_answers.get("a2_first_language") in ELIGIBLE_FIRST_LANGUAGE
        and eligibility_answers.get("a3_reading_comfort") is not None
        and eligibility_answers.get("a3_reading_comfort") not in INELIGIBLE_READING
    )


def score_familiarity(answers: Dict[str, Optional[str]]) -> dict:
    """Section D covariate. Never returned to the participant.

    ``score`` = correct / 7 (PRESURVEY_DEMOGRAPHICS: "Not sure" and wrong both
    count 0; a skipped item also counts 0). ``answered`` excludes skipped items
    and includes "Not sure", so an analysis can tell skipping from not knowing.
    """

    correct = sum(
        1 for item_id, key in _FAMILIARITY_KEY.items() if answers.get(item_id) == key
    )
    answered = sum(1 for item_id in _FAMILIARITY_KEY if answers.get(item_id) is not None)
    not_sure = sum(
        1 for item_id in _FAMILIARITY_KEY if answers.get(item_id) == NOT_SURE["code"]
    )
    total = len(_FAMILIARITY_KEY)
    return {
        "correct": correct,
        "answered": answered,
        "not_sure": not_sure,
        "items": total,
        "score": correct / total,
    }


def next_step(status: Optional[str]) -> Optional[str]:
    """The step after ``status`` (None = not started). ``None`` once complete."""

    if status is None:
        return STEPS[0]
    if status not in STEPS:
        return None
    index = STEPS.index(status)
    return STEPS[index + 1] if index + 1 < len(STEPS) else None
