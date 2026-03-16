#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
对齐前去掉“特殊标点”，对齐后在生成 ASS 时再把标点加回去。

规则：
1) long_token_dur_s：如果某个词 token 的持续时间 (end-start) > long_token_dur_s，
   则在该 token 之前强制换行（把它放到下一行第一个词）。
2) fast_speed_s：如果相邻词（用开始时间 start）的间隔 gap <= fast_speed_s，
   认为读得太快 -> 合并成一组，一次性显示 2~N 个词（减少刷屏/抖动）。
3) 支持 Title：--title / --title_start / --title_end / --title_x / --title_y

输出：
- out_words.json (word-level timestamps, 含 _lead/_trail/_orig)
- out_words.tsv
- out_words.ass (typewriter)

示例：
python word_timestamps_punct_restore.py \
  --audio ./audio.wav \
  --text ./transcript.txt \
  --language en \
  --device cpu \
  --out_prefix out \
  --make_ass \
  --title "Isaiah 41:10" \
  --title_start 0 \
  --title_end 10 \
  --title_x 540 \
  --title_y 300 \
  --max_words_per_line 12 \
  --long_token_dur_s 1.0 \
  --fast_speed_s 0.18
"""

import argparse
import json
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import whisperx


# -------------------------
# IO + normalize
# -------------------------
def read_text(text_path: Optional[str], text_inline: Optional[str]) -> str:
    if text_inline and text_inline.strip():
        return text_inline.strip()
    if not text_path:
        raise ValueError("You must provide --text or --text_inline")
    p = Path(text_path)
    if not p.exists():
        raise FileNotFoundError(f"Text file not found: {text_path}")
    return p.read_text(encoding="utf-8").strip()


def normalize_spaces(s: str) -> str:
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def audio_duration_seconds(audio_array, sample_rate: int = 16000) -> float:
    return float(len(audio_array)) / float(sample_rate)


def build_single_segment(text: str, duration: float) -> List[Dict[str, Any]]:
    return [{"start": 0.0, "end": max(0.01, duration), "text": text}]


def save_json(obj: Any, path: str) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_tsv(word_segments: List[Dict[str, Any]], path: str) -> None:
    lines = ["index\tword\tstart\tend\tdur\tscore\tlead\ttrail\torig"]
    for i, w in enumerate(word_segments):
        start = w.get("start", None)
        end = w.get("end", None)
        score = w.get("score", None)
        dur = ""
        if start is not None and end is not None:
            dur = f"{(float(end) - float(start)):.3f}"
        lines.append(
            f"{i}\t{w.get('word','')}\t"
            f"{'' if start is None else f'{float(start):.3f}'}\t"
            f"{'' if end is None else f'{float(end):.3f}'}\t"
            f"{dur}\t"
            f"{'' if score is None else f'{float(score):.4f}'}\t"
            f"{w.get('_lead_punc','')}\t{w.get('_trail_punc','')}\t{w.get('_orig_word','')}"
        )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# -------------------------
# Punctuation handling (align前去掉，ASS时加回)
# -------------------------
SPECIAL_PUNC = set(list(r""",.;:!?，。！？；："""))
LEADING_PUNC = set(list(r"""([{“‘"「『（《"""))
TRAILING_PUNC = set(list(r""")]}”’"」』）》"""))

# English word chars: letters/digits/apostrophe
WORD_CHARS_RE = re.compile(r"[A-Za-z0-9']")


def tokenize_words_with_punc(text: str) -> Tuple[List[str], List[str], List[str]]:
    """
    原文 -> words(去标点后的词序列) + lead_punc + trail_punc（与 words 一一对应）
    """
    text = normalize_spaces(text)

    words: List[str] = []
    lead: List[str] = []
    trail: List[str] = []

    pending_lead = ""
    cur_word = ""

    def flush_word():
        nonlocal cur_word, pending_lead
        if not cur_word:
            return
        words.append(cur_word)
        lead.append(pending_lead)
        trail.append("")
        cur_word = ""
        pending_lead = ""

    for ch in text:
        if WORD_CHARS_RE.match(ch):
            cur_word += ch
            continue

        if ch.isspace():
            flush_word()
            continue

        if ch in LEADING_PUNC:
            flush_word()
            pending_lead += ch
            continue

        if ch in TRAILING_PUNC:
            flush_word()
            if words:
                trail[-1] += ch
            else:
                pending_lead += ch
            continue

        if ch in SPECIAL_PUNC:
            flush_word()
            if words:
                trail[-1] += ch
            else:
                pending_lead += ch
            continue

        # unknown char -> treat as separator
        flush_word()

    flush_word()
    return words, lead, trail


def clean_word_for_match(w: str) -> str:
    w = w.replace("\n", " ")
    w = re.sub(r"\s+", " ", w).strip()
    return "".join(ch for ch in w if WORD_CHARS_RE.match(ch))


def fix_abnormal_durations(word_segments: List[Dict[str, Any]], max_word_dur: float = 0.8) -> List[Dict[str, Any]]:
    """
    修复异常长的词持续时间
    如果某个词的 duration > max_word_dur，将其 end 时间调整为 start + max_word_dur
    """
    fixed = []
    for i, seg in enumerate(word_segments):
        seg2 = dict(seg)
        start = float(seg["start"])
        end = float(seg["end"])
        dur = end - start

        if dur > max_word_dur:
            # 异常长的词，缩短其持续时间
            seg2["end"] = start + max_word_dur
            print(f"Fixed abnormal duration: '{seg.get('word')}' {dur:.3f}s -> {max_word_dur:.3f}s")

        fixed.append(seg2)

    return fixed


def smooth_word_gaps(word_segments: List[Dict[str, Any]], max_gap: float = 0.5, avg_word_dur: float = 0.3) -> List[Dict[str, Any]]:
    """
    平滑词之间的异常间隔
    如果相邻词之间的间隔 > max_gap，在它们之间均匀分布时间
    """
    if len(word_segments) < 2:
        return word_segments

    smoothed = [dict(word_segments[0])]

    for i in range(1, len(word_segments)):
        prev = smoothed[-1]
        curr = dict(word_segments[i])

        prev_end = float(prev["end"])
        curr_start = float(curr["start"])
        gap = curr_start - prev_end

        if gap > max_gap:
            # 异常大的间隔，重新分配时间
            # 假设每个词平均持续 avg_word_dur 秒
            new_prev_end = prev_end + avg_word_dur
            new_curr_start = new_prev_end + 0.05  # 留 50ms 间隔

            # 如果新的开始时间超过了原始开始时间，使用原始时间
            if new_curr_start < curr_start:
                curr["start"] = new_curr_start
                print(f"Smoothed gap before '{curr.get('word')}': {gap:.3f}s -> {0.05:.3f}s")

        smoothed.append(curr)

    return smoothed


def apply_time_offset(word_segments: List[Dict[str, Any]], offset: float) -> List[Dict[str, Any]]:
    """
    对所有词的时间戳应用全局偏移
    offset < 0: 提前（向左移动）
    offset > 0: 延后（向右移动）
    """
    if offset == 0.0:
        return word_segments

    adjusted = []
    for seg in word_segments:
        seg2 = dict(seg)
        seg2["start"] = max(0.0, float(seg["start"]) + offset)
        seg2["end"] = max(0.0, float(seg["end"]) + offset)
        adjusted.append(seg2)

    print(f"Applied time offset: {offset:+.3f}s")
    return adjusted


def attach_punc_to_aligned_words(
    word_segments: List[Dict[str, Any]],
    words: List[str],
    lead: List[str],
    trail: List[str],
) -> List[Dict[str, Any]]:
    """
    将 lead/trail 标点映射回 WhisperX 的 word_segments
    """
    out: List[Dict[str, Any]] = []
    i = 0

    for seg in word_segments:
        seg_word_raw = str(seg.get("word", ""))
        seg_word = clean_word_for_match(seg_word_raw)

        seg2 = dict(seg)
        seg2["_lead_punc"] = ""
        seg2["_trail_punc"] = ""
        seg2["_orig_word"] = seg_word_raw.strip()

        if not seg_word:
            out.append(seg2)
            continue

        tries = 0
        matched = False
        while i < len(words) and tries < 8:
            if seg_word.lower() == words[i].lower():
                matched = True
                break
            # loose fallback (rare)
            if (
                seg_word.lower() in words[i].lower()
                or words[i].lower() in seg_word.lower()
            ):
                matched = True
                break
            i += 1
            tries += 1

        if matched and i < len(words):
            seg2["_lead_punc"] = lead[i]
            seg2["_trail_punc"] = trail[i]
            seg2["_orig_word"] = words[i]
            i += 1

        out.append(seg2)

    return out


# -------------------------
# ASS helpers + typewriter
# -------------------------
def to_cs_floor(t: float) -> int:
    if t < 0:
        t = 0.0
    return int(math.floor(t * 100.0 + 1e-9))


def cs_to_ass_time(cs: int) -> str:
    if cs < 0:
        cs = 0
    h = cs // (100 * 3600)
    cs -= h * 100 * 3600
    m = cs // (100 * 60)
    cs -= m * 100 * 60
    s = cs // 100
    cs -= s * 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def make_ass_header(subtitle_fontsize: int = 80, subtitle_marginv: int = 60, title_fontsize: int = 64, video_width: int = 1080, video_height: int = 1920, title_margin: int = 100) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,{subtitle_fontsize},&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,8,0,2,30,30,{subtitle_marginv},1
Style: Title,Arial,{title_fontsize},&H0000D7FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,6,0,9,{title_margin},{title_margin},60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# 移除这行，不再使用静态模板
# ASS_HEADER_TEMPLATE = make_ass_header()

END_PUNC_RENDER = set([",", ".", "!", "?", ";", ":", "，", "。", "！", "？", "；", "："])
NO_SPACE_AFTER = set(["(", "[", "{", "“", "‘", '"', "「", "『", "（", "《"])
NO_SPACE_BEFORE = set([")", "]", "}", "”", "’", '"', "」", "』", "）", "》"])


def smart_join_en(tokens: List[str]) -> str:
    out = ""
    prev = ""
    for t in tokens:
        t = t.strip()
        if not t:
            continue

        is_punc_only = len(t) == 1 and t in END_PUNC_RENDER

        if not out:
            out = t
            prev = t
            continue

        if is_punc_only:
            out += t
        elif prev and prev[-1] in NO_SPACE_AFTER:
            out += t
        elif t and t[0] in NO_SPACE_BEFORE:
            out += t
        else:
            out += " " + t

        prev = t
    return out.strip()


def make_display_token(seg: Dict[str, Any]) -> str:
    word = str(seg.get("_orig_word") or seg.get("word", "")).strip()
    lp = str(seg.get("_lead_punc", ""))
    tp = str(seg.get("_trail_punc", ""))
    return f"{lp}{word}{tp}"


def token_dur_s(seg: Dict[str, Any]) -> float:
    return float(seg["end"]) - float(seg["start"])


def group_into_lines(
    segments: List[Dict[str, Any]],
    max_words_per_line: int,
    long_token_dur_s: float,
) -> List[List[Dict[str, Any]]]:
    """
    分行规则：
    1) 若当前 token duration > long_token_dur_s，则在它前面强制换行（该 token 放到下一行）
    2) 单行词数 >= max_words_per_line 换行
    """
    lines: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []

    for w in segments:
        if long_token_dur_s is not None and long_token_dur_s > 0:
            if token_dur_s(w) > long_token_dur_s and cur:
                lines.append(cur)
                cur = [w]
            else:
                cur.append(w)
        else:
            cur.append(w)

        if len(cur) >= max_words_per_line:
            lines.append(cur)
            cur = []

    if cur:
        lines.append(cur)
    return lines


def group_fast_merge_within_line(
    line: List[Dict[str, Any]],
    fast_speed_s: float,
) -> List[List[Dict[str, Any]]]:
    """
    行内"快读合并显示"：
    gap = next.start - prev.start
    gap <= fast_speed_s -> 读得很快 -> 同一组（一次显示多个词）
    否则 -> 新组
    """
    if not line:
        return []

    groups: List[List[Dict[str, Any]]] = []
    cur = [line[0]]

    for i in range(1, len(line)):
        prev = line[i - 1]
        now = line[i]
        gap = float(now["start"]) - float(prev["start"])
        if gap <= fast_speed_s:
            cur.append(now)
        else:
            groups.append(cur)
            cur = [now]

    groups.append(cur)
    return groups


def make_typewriter_ass(
    word_segments: List[Dict[str, Any]],
    out_ass_path: str,
    max_words_per_line: int = 12,
    long_token_dur_s: float = 1.0,
    fast_speed_s: float = 0.18,
    highlight_last_word: bool = True,
    highlight_scale: int = 150,
    end_gap_cs: int = 1,  # 0.01s
    # title
    title: Optional[str] = None,
    title_start: float = 0.0,
    title_end: float = 10.0,
    title_x: int = 540,
    title_y: int = 300,
    # subtitle style
    subtitle_fontsize: int = 80,
    subtitle_marginv: int = 60,
    subtitle_x: int = 540,
    subtitle_y: int = 1800,
    title_fontsize: int = 64,
    video_width: int = 1080,
    video_height: int = 1920,
    title_margin: int = 100,
) -> None:
    ws = [
        w
        for w in word_segments
        if w.get("start") is not None and w.get("end") is not None
    ]
    if not ws:
        Path(out_ass_path).write_text(make_ass_header(subtitle_fontsize, subtitle_marginv, title_fontsize, video_width, video_height), encoding="utf-8")
        return

    # 分行
    lines = group_into_lines(
        ws, max_words_per_line=max_words_per_line, long_token_dur_s=long_token_dur_s
    )

    out_lines: List[str] = [make_ass_header(subtitle_fontsize, subtitle_marginv, title_fontsize, video_width, video_height).strip(), ""]

    # Title (layer=1)
    if title:
        st = to_cs_floor(title_start)
        ed = to_cs_floor(title_end)
        if ed <= st:
            ed = st + 1
        out_lines.append("; --- Persistent Title ---")
        out_lines.append(
            f"Dialogue: 1,{cs_to_ass_time(st)},{cs_to_ass_time(ed)},Title,,0,0,0,,{{\\an9\\pos({title_x},{title_y})\\q2}}{title}"
        )
        out_lines.append("")

    # Body
    prev_line_last_word = None  # 跟踪上一行的最后一个词
    prev_line_end_cs = None  # 跟踪上一行的实际结束时间（用于后续更新）

    for li, line in enumerate(lines, start=1):
        out_lines.append(f"; ---- Line {li} ----")

        groups = group_fast_merge_within_line(line, fast_speed_s=fast_speed_s)

        cum_tokens: List[str] = []

        # 用于存储当前行的所有对话行，以便后续可能需要更新上一行的结束时间
        current_line_dialogues = []

        # 第一步：计算所有组的开始时间
        group_start_times = []
        for gi, g in enumerate(groups):
            # 检查是否需要延迟显示（因为上一个词有标点）
            should_delay = False

            if gi > 0:
                # 同一行内：检查上一组最后一个词
                prev_group = groups[gi - 1]
                prev_last_word = prev_group[-1]
                prev_trail_punc = prev_last_word.get("_trail_punc", "")

                if prev_trail_punc and prev_trail_punc.strip():
                    should_delay = True
            elif li > 1 and prev_line_last_word:
                # 跨行：检查上一行的最后一个词
                prev_trail_punc = prev_line_last_word.get("_trail_punc", "")

                if prev_trail_punc and prev_trail_punc.strip():
                    should_delay = True

            # 确定开始时间
            if should_delay:
                # 延迟到当前组第一个词的 end 时间
                start_cs = to_cs_floor(float(g[0]["end"]))

                # 如果是跨行且需要延迟，更新上一行最后一个对话的结束时间
                if li > 1 and gi == 0 and len(out_lines) >= 2:
                    # 找到上一行最后一个 Dialogue
                    for i in range(len(out_lines) - 1, -1, -1):
                        if out_lines[i].startswith("Dialogue:"):
                            # 更新结束时间为当前行的开始时间（衔接）
                            parts = out_lines[i].split(",")
                            if len(parts) >= 10:
                                parts[2] = cs_to_ass_time(start_cs)  # 更新 End 时间
                                out_lines[i] = ",".join(parts)
                            break
            elif li == 1 and gi == 0:
                # 第一行第一个词：使用中位数时间
                first_word = g[0]
                mid_time = (float(first_word["start"]) + float(first_word["end"])) / 2.0
                start_cs = to_cs_floor(mid_time)
            else:
                # 正常：使用当前组第一个词的 start 时间
                start_cs = to_cs_floor(float(g[0]["start"]))

            group_start_times.append(start_cs)

        # 第二步：生成对话行
        for gi, g in enumerate(groups):
            start_cs = group_start_times[gi]

            if gi < len(groups) - 1:
                # 组内：检查当前组最后一个词是否有标点
                current_last_word = g[-1]
                current_trail_punc = current_last_word.get("_trail_punc", "")

                # 使用下一组预先计算好的开始时间
                next_start_cs = group_start_times[gi + 1]

                if current_trail_punc and current_trail_punc.strip():
                    # 有标点：延长到下一组的开始时间（衔接）
                    end_cs = next_start_cs
                else:
                    # 无标点：正常结束
                    end_cs = next_start_cs - end_gap_cs
            else:
                # 最后一组：显示到该组最后一个词结束
                last_word_end_cs = to_cs_floor(float(g[-1]["end"]))

                # 检查是否有下一行（注意：li是从1开始的）
                if li < len(lines):
                    # 使用下一行第一个词的原始 start 时间（不是延迟后的时间）
                    next_line_first_word = lines[li][0]
                    next_line_original_start = float(next_line_first_word["start"])
                    next_line_start_cs = to_cs_floor(next_line_original_start)

                    # 检查当前行最后一个词是否有标点
                    current_last_word = g[-1]
                    current_trail_punc = current_last_word.get("_trail_punc", "")

                    if current_trail_punc and current_trail_punc.strip():
                        # 有标点：延长到下一行第一个词的原始 start 时间（衔接）
                        end_cs = next_line_start_cs
                    elif next_line_start_cs <= last_word_end_cs:
                        # 无标点但重叠：在下一行开始前结束
                        end_cs = next_line_start_cs - end_gap_cs
                    else:
                        # 正常情况：显示到当前词结束
                        end_cs = last_word_end_cs + end_gap_cs
                else:
                    # 最后一行：正常结束
                    end_cs = last_word_end_cs + end_gap_cs

            if end_cs <= start_cs:
                end_cs = start_cs + end_gap_cs

            # 累积显示：把当前组的词加入
            for seg in g:
                cum_tokens.append(make_display_token(seg))

            text_cum = smart_join_en(cum_tokens)

            # highlight last token of the whole line
            if highlight_last_word and gi == len(groups) - 1 and cum_tokens:
                prefix = smart_join_en(cum_tokens[:-1]) if len(cum_tokens) > 1 else ""
                last = cum_tokens[-1].strip()
                if prefix:
                    text_cum = (
                        f"{prefix} "
                        f"{{\\fscx{highlight_scale}\\fscy{highlight_scale}}}{last}"
                        f"{{\\fscx100\\fscy100}}"
                    )
                else:
                    text_cum = (
                        f"{{\\fscx{highlight_scale}\\fscy{highlight_scale}}}{last}"
                        f"{{\\fscx100\\fscy100}}"
                    )

            out_lines.append(
                f"Dialogue: 0,{cs_to_ass_time(start_cs)},{cs_to_ass_time(end_cs)},Default,,0,0,0,,{{\\pos({subtitle_x},{subtitle_y})}}{text_cum}"
            )

        # 记录当前行的最后一个词，用于下一行的标点检查
        if line:
            prev_line_last_word = line[-1]

        out_lines.append("")

    Path(out_ass_path).write_text("\n".join(out_lines).strip() + "\n", encoding="utf-8")


# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="audio/video file path")
    ap.add_argument("--text", default=None, help="transcript text file (utf-8)")
    ap.add_argument("--text_inline", default=None, help="transcript inline")
    ap.add_argument("--language", default="en", help="language code: en/zh/...")
    ap.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda", "mps"], help="cpu/cuda/mps"
    )
    ap.add_argument("--out_prefix", default="out_words", help="output prefix")

    ap.add_argument("--make_ass", action="store_true", help="also output .ass")

    # title
    ap.add_argument("--title", default=None, help="optional persistent title")
    ap.add_argument("--title_start", type=float, default=0.0)
    ap.add_argument("--title_end", type=float, default=10.0)
    ap.add_argument("--title_x", type=int, default=540)
    ap.add_argument("--title_y", type=int, default=300)

    # line / ass options
    ap.add_argument("--max_words_per_line", type=int, default=12)

    # ✅ 你要的：token 持续时间太长 -> 该 token 放到下一行
    ap.add_argument(
        "--long_token_dur_s",
        type=float,
        default=1.0,
        help="if token duration (end-start) > this, force a new ASS line starting from this token",
    )

    # ✅ 你要的：读得很快 -> 合并显示多个词
    ap.add_argument(
        "--fast_speed_s",
        type=float,
        default=0.18,
        help="if adjacent word(mid) gap <= this, treat as fast and merge (show multiple words at once)",
    )

    ap.add_argument("--highlight_last_word", action="store_true")
    ap.add_argument("--highlight_scale", type=int, default=150)

    # 时间间隔参数
    ap.add_argument(
        "--end_gap_cs",
        type=int,
        default=1,
        help="gap between groups in centiseconds (0.01s)",
    )

    args = ap.parse_args()

    raw_text = normalize_spaces(read_text(args.text, args.text_inline))

    # 原文 -> (词序列 + 标点映射)
    words, lead, trail = tokenize_words_with_punc(raw_text)

    # 对齐用文本：只用词序列（无标点）
    align_text = " ".join(words).strip()
    if not align_text:
        raise ValueError("No alignable words after removing punctuation.")

    audio = whisperx.load_audio(args.audio)
    dur = audio_duration_seconds(audio, sample_rate=16000)
    segments = build_single_segment(align_text, dur)

    align_model, metadata = whisperx.load_align_model(
        language_code=args.language, device=args.device
    )

    aligned = whisperx.align(
        segments,
        align_model,
        metadata,
        audio,
        args.device,
        return_char_alignments=True,
    )

    word_segments = aligned.get("word_segments", []) or []
    if not word_segments:
        raise RuntimeError(
            "No word_segments produced. Check language/text match and audio quality."
        )

    # 补回标点（用于 ASS 显示）
    word_segments = attach_punc_to_aligned_words(word_segments, words, lead, trail)

    # 输出 json/tsv
    out_json = f"{args.out_prefix}.json"
    out_tsv = f"{args.out_prefix}.tsv"
    save_json(word_segments, out_json)
    save_tsv(word_segments, out_tsv)

    # 输出 ass
    if args.make_ass:
        out_ass = f"{args.out_prefix}.ass"
        make_typewriter_ass(
            word_segments,
            out_ass,
            max_words_per_line=args.max_words_per_line,
            long_token_dur_s=args.long_token_dur_s,
            fast_speed_s=args.fast_speed_s,
            highlight_last_word=args.highlight_last_word,
            highlight_scale=args.highlight_scale,
            end_gap_cs=args.end_gap_cs,
            title=args.title,
            title_start=args.title_start,
            title_end=args.title_end,
            title_x=args.title_x,
            title_y=args.title_y,
        )
        print(f"Saved: {out_ass}")

    print(f"Audio: {args.audio}")
    print(f"Duration: {dur:.2f}s")
    print(f"Align words: {len(words)}")
    print(f"Aligned segments: {len(word_segments)}")
    print(f"Saved: {out_json}")
    print(f"Saved: {out_tsv}")


if __name__ == "__main__":
    main()
