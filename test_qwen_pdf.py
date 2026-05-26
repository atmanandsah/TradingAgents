import sys
import os
import base64
import json
import urllib.request
import urllib.error
import socket

socket.setdefaulttimeout(300)  # 5 min per page

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"  # streaming: page extraction
OLLAMA_CHAT_URL     = "http://localhost:11434/api/chat"      # non-streaming: final summary

# VISION_MODEL = "qwen2.5vl:3b"   # fast vision model for per-page extraction
VISION_MODEL = "llama3.1"   # fast vision model for per-page extraction
TEXT_MODEL   = "llama3.1"        # fast text model for final coherent summary

# ──────────────────────────────────────────────────────────────────
# PDF helpers
# ──────────────────────────────────────────────────────────────────

def page_to_base64(pdf_path: str, page_num: int) -> str:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    pix = page.get_pixmap(dpi=80)
    png_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(png_bytes).decode("utf-8")

def parse_page_range(range_str: str, total_pages: int) -> list:
    range_str = range_str.strip().lower()
    if range_str == "all":
        return list(range(total_pages))
    pages = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                s, e = part.split("-")
                pages.update(range(int(s) - 1, min(total_pages, int(e))))
            except ValueError:
                pass
        else:
            try:
                v = int(part)
                if 1 <= v <= total_pages:
                    pages.add(v - 1)
            except ValueError:
                pass
    return sorted(pages) if pages else list(range(total_pages))

# ──────────────────────────────────────────────────────────────────
# Phase 1: Extract text from a single page via Qwen (streaming)
# ──────────────────────────────────────────────────────────────────

def extract_page(b64_img: str, page_num: int, total_pages: int) -> str:
    """Send one page image to Qwen, stream output, and return the extracted text."""
    payload = {
        "model": VISION_MODEL,
        "prompt": (
            "Extract all text, numbers, and tables from this document page exactly as they appear. "
            "Format tables as markdown. Do not summarize. Preserve all data."
        ),
        "images": [b64_img],
        "stream": True
    }

    req = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"\n[Phase 1] Extracting Page {page_num + 1}/{total_pages}...", flush=True)
    tokens = []
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            for line in response:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("response", "")
                print(token, end="", flush=True)
                tokens.append(token)
                if chunk.get("done", False):
                    break
        print()
        return "".join(tokens)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"\nERROR: Model '{VISION_MODEL}' not found. Run: ollama pull {VISION_MODEL}")
        else:
            print(f"\nERROR: HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\nERROR: Ollama not reachable: {e}")
        sys.exit(1)

# ──────────────────────────────────────────────────────────────────
# Phase 2: Synthesize all extracted pages into one summary via llama3.1
# ──────────────────────────────────────────────────────────────────

def synthesize_summary(all_page_texts: list[str], user_prompt: str) -> str:
    """Send all extracted page texts to llama3.1 for a structured investment analysis report."""
    combined = "\n\n".join(
        f"--- PAGE {i + 1} ---\n{text}" for i, text in enumerate(all_page_texts)
    )

    # ── CRITICAL: Put document content FIRST, strict format instructions LAST.
    # llama3.1 follows the LAST instruction it sees before generating. ──
    system_message = (
        "You are a professional equity research analyst specializing in Indian stock markets. "
        "When given financial document content, you MUST respond using ONLY the exact 6-section "
        "structured format requested. Never deviate from the format. Quote exact numbers."
    )

    user_message = f"""DOCUMENT CONTENT ({len(all_page_texts)} pages total):

{combined}

---

USER REQUEST: {user_prompt}

---

NOW produce the analysis using EXACTLY this format. Fill every section using data from above:

## 1. FINANCIAL PERFORMANCE
- **Revenue (Top Line):** Latest year figure + YoY growth %
- **Net Profit / PAT:** Latest figure + YoY growth %
- **Operating Profit & OPM%:** Latest OPM%. Expanding or contracting?
- **Trend:** 3-year revenue direction (growing/flat/declining)

## 2. SECTOR & KPIs
- **Sector:** (identify: Oil & Gas / IT / FMCG / Manufacturing / Defence / Other)
- **EBITDA / EBITDA%:** (if applicable)
- **Order Book:** (if applicable)
- **Dollar Revenue / Deal Wins:** (if IT)

## 3. KEY RATIOS
| Ratio | Value | Signal |
|---|---|---|
| ROE | ? | |
| Net Profit Margin | ? | |
| Debt to Equity | ? | |
| 5-Yr Revenue CAGR | ? | |
| Promoter Holding | ? | Increasing/Decreasing |

## 4. QUALITATIVE
- **Business Model:** (one line: what does the company do?)
- **Tailwinds:** (2-3 bullet points)
- **Headwinds:** (2-3 bullet points)
- **Cash Flow from Operations:** Positive or Negative?

## 5. ANTITHESIS (Red Flags)
List ONLY confirmed red flags found in the document:
- (red flag 1)
- (red flag 2)

## 6. VERDICT
**Financial Health:** Improving / Stable / Deteriorating
**Signal:** Bullish / Neutral / Bearish
**Top Risk:** (one sentence)
"""

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user",   "content": user_message}
        ],
        "options": {"temperature": 0},  # temperature=0 forces strict format adherence
        "stream": True   # Stream so output is visible live
    }

    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"\n[Phase 2] Generating structured analysis with {TEXT_MODEL}...\n", flush=True)
    tokens = []
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            for line in response:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("message", {}).get("content", "")
                print(token, end="", flush=True)
                tokens.append(token)
                if chunk.get("done", False):
                    break
        print()
        return "".join(tokens)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"\nERROR: Text model '{TEXT_MODEL}' not found. Run: ollama pull {TEXT_MODEL}")
        else:
            print(f"\nERROR: HTTP {e.code}: {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\nERROR: Ollama not reachable: {e}")
        sys.exit(1)

# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_qwen_pdf.py <pdf_or_image> [prompt] [page_range]")
        print("Examples:")
        print("  python test_qwen_pdf.py doc.pdf 'Summarize' all")
        print("  python test_qwen_pdf.py doc.pdf 'Extract tables' 1-5")
        sys.exit(1)

    if not PYMUPDF_AVAILABLE:
        print("ERROR: Install pymupdf first: pip install pymupdf")
        sys.exit(1)

    file_path = sys.argv[1]
    user_prompt = sys.argv[2] if len(sys.argv) > 2 else "Summarize the entire document"
    page_range  = sys.argv[3] if len(sys.argv) > 3 else "all"

    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in [".pdf", ".png", ".jpg", ".jpeg", ".webp"]:
        print(f"ERROR: Unsupported file type '{ext}'")
        sys.exit(1)

    if ext == ".pdf":
        doc = fitz.open(file_path)
        total_pages = len(doc)
        doc.close()
        pages_to_process = parse_page_range(page_range, total_pages)
    else:
        total_pages = 1
        pages_to_process = [0]

    print(f"Document: {os.path.basename(file_path)} ({total_pages} total pages)")
    print(f"Processing: {len(pages_to_process)} page(s) | Vision: {VISION_MODEL} | Summary: {TEXT_MODEL}")
    print("=" * 70)
    print("PHASE 1: Extracting content page by page (streaming)...")
    print("=" * 70)

    # ── Phase 1: Extract each page individually ──
    all_page_texts = []
    for page_num in pages_to_process:
        if ext == ".pdf":
            b64 = page_to_base64(file_path, page_num)
        else:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        text = extract_page(b64, page_num, total_pages)
        all_page_texts.append(text)

    print("\n" + "=" * 70)
    print("PHASE 2: Synthesizing unified summary...")
    print("=" * 70)

    # ── Phase 2: Synthesize into one coherent summary ──
    final_summary = synthesize_summary(all_page_texts, user_prompt)

    print("\n" + "=" * 30 + " FINAL SUMMARY " + "=" * 30)
    print(final_summary)
    print("=" * 75)

if __name__ == "__main__":
    main()
