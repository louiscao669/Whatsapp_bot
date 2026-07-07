#!/usr/bin/env python3
"""Create a small PowerPoint deck for the translation-quality evaluation."""

import argparse
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


SLIDE_W = 13_333_500
SLIDE_H = 7_500_000
EMU = 914400


def emu(inches: float) -> int:
    return int(inches * EMU)


def xml_text(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def fmt(value, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def shape_text(
    shape_id: int,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    font_size: int = 24,
    bold: bool = False,
    color: str = "1F2937",
    align: str = "l",
) -> str:
    bold_attr = ' b="1"' if bold else ""
    paragraphs = []
    for line in text.split("\n"):
        paragraphs.append(
            f"""
            <a:p>
              <a:pPr algn="{align}"/>
              <a:r>
                <a:rPr lang="en-US" sz="{font_size * 100}"{bold_attr}>
                  <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
                </a:rPr>
                <a:t>{xml_text(line)}</a:t>
              </a:r>
            </a:p>"""
        )
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="Text {shape_id}"/>
        <p:cNvSpPr txBox="1"/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm>
          <a:off x="{emu(x)}" y="{emu(y)}"/>
          <a:ext cx="{emu(w)}" cy="{emu(h)}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:noFill/>
        <a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr wrap="square"/>
        <a:lstStyle/>
        {''.join(paragraphs)}
      </p:txBody>
    </p:sp>"""


def rect(
    shape_id: int,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str,
    line: str | None = None,
) -> str:
    line_xml = (
        f'<a:ln><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>'
        if line
        else "<a:ln><a:noFill/></a:ln>"
    )
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="Rect {shape_id}"/>
        <p:cNvSpPr/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm>
          <a:off x="{emu(x)}" y="{emu(y)}"/>
          <a:ext cx="{emu(w)}" cy="{emu(h)}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
        {line_xml}
      </p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
    </p:sp>"""


def bullet_lines(lines: list[str]) -> str:
    return "\n".join(f"• {line}" for line in lines)


def title(slide_title: str, subtitle: str = "") -> list[str]:
    shapes = [
        shape_text(2, slide_title, 0.65, 0.35, 11.8, 0.65, font_size=28, bold=True, color="111827")
    ]
    if subtitle:
        shapes.append(shape_text(3, subtitle, 0.68, 0.95, 11.4, 0.35, font_size=13, color="667085"))
    shapes.append(rect(4, 0.65, 1.28, 12.0, 0.03, fill="315FBD"))
    return shapes


def slide_xml(shapes: list[str]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {''.join(shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def table_slide(methods: list[dict]) -> list[str]:
    shapes = title("Results by Translation Method", "Luke 2-8, qwen2.5:1.5b answer model")
    headers = ["Method", "Combined", "Open", "MCQ", "Null MCQ"]
    xs = [0.75, 4.2, 5.9, 7.3, 8.65]
    widths = [3.2, 1.25, 1.1, 1.1, 1.2]
    y = 1.55
    for i, header in enumerate(headers):
        shapes.append(rect(10 + i, xs[i], y, widths[i], 0.35, fill="E9EEF8", line="CBD5E1"))
        shapes.append(shape_text(20 + i, header, xs[i] + 0.05, y + 0.06, widths[i] - 0.1, 0.2, font_size=10, bold=True))
    for r, row in enumerate(methods[:8]):
        y = 1.95 + r * 0.48
        fill = "FFFFFF" if r % 2 == 0 else "F8FAFC"
        for i in range(len(headers)):
            shapes.append(rect(40 + r * 10 + i, xs[i], y, widths[i], 0.42, fill=fill, line="E5E7EB"))
        values = [
            row["method"],
            fmt(row["combined_score"]),
            fmt(row["open_llm_mean"]),
            pct(row["mcq_accuracy"]),
            str(row["null_mcq"]),
        ]
        for i, value in enumerate(values):
            shapes.append(shape_text(120 + r * 10 + i, value, xs[i] + 0.05, y + 0.09, widths[i] - 0.1, 0.22, font_size=10))
        bar_w = 2.1 * (row["combined_score"] or 0)
        shapes.append(rect(220 + r, 10.1, y + 0.1, 2.1, 0.15, fill="E5E7EB"))
        shapes.append(rect(240 + r, 10.1, y + 0.1, bar_w, 0.15, fill="315FBD"))
    return shapes


def heatmap_slide(rows: list[dict], chapters: list[dict]) -> list[str]:
    shapes = title("Chapter-Level Pattern", "Hard chapters expose answer-model and passage-quality failures")
    x0 = 0.78
    y0 = 1.55
    shapes.append(shape_text(10, "Chapter", x0, y0, 1.4, 0.25, font_size=10, bold=True))
    shapes.append(shape_text(11, "Mean combined", x0 + 1.7, y0, 1.4, 0.25, font_size=10, bold=True))
    shapes.append(shape_text(12, "Range", x0 + 3.35, y0, 1.4, 0.25, font_size=10, bold=True))
    for i, row in enumerate(chapters):
        y = y0 + 0.45 + i * 0.45
        shapes.append(shape_text(20 + i, f"Luke {row['chapter']}", x0, y, 1.0, 0.22, font_size=10))
        shapes.append(shape_text(30 + i, fmt(row["combined_mean"]), x0 + 1.7, y, 1.0, 0.22, font_size=10))
        shapes.append(shape_text(40 + i, f"{fmt(row['combined_min'])} - {fmt(row['combined_max'])}", x0 + 3.35, y, 2.0, 0.22, font_size=10))
        shapes.append(rect(50 + i, x0 + 5.45, y + 0.04, 2.2, 0.13, fill="E5E7EB"))
        shapes.append(rect(60 + i, x0 + 5.45, y + 0.04, 2.2 * (row["combined_mean"] or 0), 0.13, fill="2E7D32"))
    hardest = min(chapters, key=lambda row: row["combined_mean"] or 999)
    easiest = max(chapters, key=lambda row: row["combined_mean"] or -1)
    shapes.append(
        shape_text(
            100,
            bullet_lines(
                [
                    f"Hardest average: Luke {hardest['chapter']} ({fmt(hardest['combined_mean'])}).",
                    f"Easiest average: Luke {easiest['chapter']} ({fmt(easiest['combined_mean'])}).",
                    "Lower chapters likely reflect harder content, weaker passage translations, and deterministic answer-model errors.",
                ]
            ),
            0.85,
            5.25,
            11.5,
            1.1,
            font_size=15,
        )
    )
    return shapes


def build_slides(data: dict) -> list[str]:
    methods = data["methods"]
    chapters = data["chapters"]
    total_items = sum(row["total"] for row in data["rows"])
    total_mcq = sum(row["mcq_count"] for row in data["rows"])
    total_open = sum(row["open_scored"] for row in data["rows"])
    best = methods[0]
    best_open = max(methods, key=lambda row: row["open_llm_mean"] or -1)
    best_mcq = max(methods, key=lambda row: row["mcq_accuracy"] or -1)

    slides = []
    slides.append(
        slide_xml(
            title("Evaluating Translation Quality via Answer Accuracy", "Bible QA evaluation, Luke 2-8, all translation methods")
            + [
                shape_text(
                    10,
                    "Core question",
                    0.85,
                    1.65,
                    4.0,
                    0.4,
                    font_size=20,
                    bold=True,
                    color="315FBD",
                ),
                shape_text(
                    11,
                    "Can an answer model's accuracy on translated passages serve as a practical signal for passage translation quality?",
                    0.85,
                    2.15,
                    11.3,
                    0.9,
                    font_size=24,
                    bold=True,
                ),
                shape_text(
                    12,
                    bullet_lines(
                        [
                            "Shared QA translation controls for question wording.",
                            "Passage translation method is the main experimental variable.",
                            "Open-answer and MCQ scoring provide complementary signals.",
                        ]
                    ),
                    0.95,
                    3.55,
                    11.2,
                    1.25,
                    font_size=16,
                ),
            ]
        )
    )
    slides.append(
        slide_xml(
            title("Experimental Design", "Hold QA fixed; vary only translated passage quality")
            + [
                shape_text(
                    10,
                    bullet_lines(
                        [
                            "Dataset: Luke 2-8 all-format QA, evaluated across 8 passage translation methods.",
                            "QA translation: one shared high-quality LLM translation and decanonicalization per chapter.",
                            "Passage translation: google word-by-word, LLM prompts, Helsinki, mBART, NLLB variants.",
                            "Answer model: qwen2.5:1.5b through Ollama, deterministic temperature 0.",
                            "Failures: invalid MCQ outputs can be saved as null and counted wrong.",
                        ]
                    ),
                    0.85,
                    1.65,
                    11.6,
                    2.2,
                    font_size=16,
                ),
                shape_text(
                    20,
                    f"Scale: {len(data['rows'])} method/chapter runs, {total_items} scored items, {total_open} open answers, {total_mcq} MCQs.",
                    0.9,
                    4.45,
                    11.4,
                    0.55,
                    font_size=20,
                    bold=True,
                    color="111827",
                ),
            ]
        )
    )
    slides.append(
        slide_xml(
            title("Pipeline Controls", "The evaluation isolates passage translation as much as possible")
            + [
                shape_text(
                    10,
                    "1. English passage + English QA\n2. LLM entity inventory and placeholders\n3. Shared QA translation + shared QA decanonicalization\n4. Per-method passage translation + passage decanonicalization\n5. qwen2.5:1.5b answers shared QA from each translated passage\n6. Backtranslation, MCQ direct scoring, open-answer LLM/embedding scoring",
                    0.85,
                    1.55,
                    11.7,
                    2.9,
                    font_size=17,
                ),
                shape_text(
                    20,
                    "Why this matters: if QA differs by method, answer accuracy can measure question translation artifacts. The corrected pipeline keeps QA constant so method differences mainly reflect passage translation.",
                    0.9,
                    5.0,
                    11.4,
                    0.9,
                    font_size=17,
                    bold=True,
                    color="315FBD",
                ),
            ]
        )
    )
    slides.append(slide_xml(table_slide(methods)))
    slides.append(slide_xml(heatmap_slide(data["rows"], chapters)))
    slides.append(
        slide_xml(
            title("High-Level Takeaways", "Answer accuracy is useful, but not a pure translation metric")
            + [
                shape_text(
                    10,
                    bullet_lines(
                        [
                            f"Best weighted combined score: {best['method']} ({fmt(best['combined_score'])}).",
                            f"Best open-answer mean: {best_open['method']} ({fmt(best_open['open_llm_mean'])}).",
                            f"Best MCQ accuracy: {best_mcq['method']} ({pct(best_mcq['mcq_accuracy'])}).",
                            "MCQs are sensitive to answer-model choice bias and output-format failures.",
                            "Open answers give richer semantic signal, but require reliable judging/backtranslation.",
                            "Use this as a comparative screening metric, then inspect hard chapters/items manually.",
                        ]
                    ),
                    0.85,
                    1.55,
                    11.7,
                    3.0,
                    font_size=16,
                ),
                shape_text(
                    20,
                    "Next: compare with a stronger answer model, report confidence intervals by item, and separate passage comprehension errors from answer-model formatting failures.",
                    0.9,
                    5.15,
                    11.4,
                    0.85,
                    font_size=17,
                    bold=True,
                    color="315FBD",
                ),
            ]
        )
    )
    return slides


def content_types(slide_count: int) -> str:
    slide_overrides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  {slide_overrides}
</Types>"""


def presentation_xml(slide_count: int) -> str:
    slide_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, slide_count + 1)
    )
    master_rid = slide_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId{master_rid}"/></p:sldMasterIdLst>
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""


def presentation_rels(slide_count: int) -> str:
    rels = []
    for i in range(1, slide_count + 1):
        rels.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        )
    rels.append(
        f'<Relationship Id="rId{slide_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    )
    rels.append(
        f'<Relationship Id="rId{slide_count + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {''.join(rels)}
</Relationships>"""


ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>6</Slides>
</Properties>"""


CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Translation Quality Evaluation Summary</dc:title>
  <dc:creator>Codex</dc:creator>
</cp:coreProperties>"""


THEME_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Evaluation">
  <a:themeElements>
    <a:clrScheme name="Evaluation">
      <a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>
      <a:accent1><a:srgbClr val="315FBD"/></a:accent1><a:accent2><a:srgbClr val="2E7D32"/></a:accent2>
      <a:accent3><a:srgbClr val="B45309"/></a:accent3><a:accent4><a:srgbClr val="B42318"/></a:accent4>
      <a:accent5><a:srgbClr val="667085"/></a:accent5><a:accent6><a:srgbClr val="8A6D1F"/></a:accent6>
      <a:hlink><a:srgbClr val="315FBD"/></a:hlink><a:folHlink><a:srgbClr val="8A6D1F"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Evaluation"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Evaluation"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>"""


SLIDE_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>"""


SLIDE_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>"""


SLIDE_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""


def write_pptx(output: Path, slides: list[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types(len(slides)))
        package.writestr("_rels/.rels", ROOT_RELS)
        package.writestr("docProps/app.xml", APP_XML)
        package.writestr("docProps/core.xml", CORE_XML)
        package.writestr("ppt/presentation.xml", presentation_xml(len(slides)))
        package.writestr("ppt/_rels/presentation.xml.rels", presentation_rels(len(slides)))
        package.writestr("ppt/theme/theme1.xml", THEME_XML)
        package.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        package.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS)
        package.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        package.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS)
        for index, slide in enumerate(slides, start=1):
            package.writestr(f"ppt/slides/slide{index}.xml", slide)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("evaluation/outputs/luke_2_8_method_report_1.5b.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/outputs/translation_quality_evaluation_summary.pptx"),
    )
    args = parser.parse_args()
    data = json.loads(args.summary.read_text(encoding="utf-8"))
    write_pptx(args.output, build_slides(data))
    print(f"Wrote PowerPoint: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
