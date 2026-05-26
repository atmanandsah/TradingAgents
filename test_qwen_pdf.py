import sys
import os
import base64
import json
import urllib.request
import urllib.error
import socket
import datetime

socket.setdefaulttimeout(300)  # 5 min per page

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"  # streaming: page extraction
OLLAMA_CHAT_URL     = "http://localhost:11434/api/chat"      # non-streaming: final summary

VISION_MODEL = "qwen2.5vl:3b"   # fast vision model for per-page extraction
# VISION_MODEL = "llama3.1"   # fast vision model for per-page extraction
TEXT_MODEL   = "llama3.1"        # fast text model for final coherent summary

# ──────────────────────────────────────────────────────────────────
# Telegram & Environment helpers
# ──────────────────────────────────────────────────────────────────

def load_env_vars() -> dict:
    env_vars = {}
    for path in [os.path.join(os.getcwd(), ".env"), os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        v = v.split("#", 1)[0].strip()
                        env_vars[k.strip()] = v.strip().strip("'\"")
    for k in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        if k in os.environ:
            env_vars[k] = os.environ[k]
    return env_vars

def send_telegram_document(token: str, chat_id: str, filepath: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = "---TelegramBoundary---"
    
    try:
        with open(filepath, "rb") as f:
            file_content = f.read()
    except Exception as e:
        print(f"\n[Telegram] Error reading file for upload: {e}", flush=True)
        return

    filename = os.path.basename(filepath)
    
    parts = []
    parts.append(f"--{boundary}".encode('utf-8'))
    parts.append(f'Content-Disposition: form-data; name="chat_id"'.encode('utf-8'))
    parts.append(''.encode('utf-8'))
    parts.append(str(chat_id).encode('utf-8'))
    
    if caption:
        parts.append(f"--{boundary}".encode('utf-8'))
        parts.append(f'Content-Disposition: form-data; name="caption"'.encode('utf-8'))
        parts.append(''.encode('utf-8'))
        parts.append(caption.encode('utf-8'))
        
    parts.append(f"--{boundary}".encode('utf-8'))
    parts.append(f'Content-Disposition: form-data; name="document"; filename="{filename}"'.encode('utf-8'))
    parts.append('Content-Type: text/plain'.encode('utf-8'))
    parts.append(''.encode('utf-8'))
    parts.append(file_content)
    parts.append(f"--{boundary}--".encode('utf-8'))
    
    body = b"\r\n".join(parts)
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        print(f"\n[Telegram] Report sent successfully to chat: {chat_id}", flush=True)
    except Exception as e:
        print(f"\n[Telegram] Error sending document: {e}", flush=True)

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

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n[Phase 1] [{ts}] Extracting Page {page_num + 1}/{total_pages}...", flush=True)
    tokens = []
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            for line in response:
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("response", "")
                # print(token, end="", flush=True)
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

    user_message = f"""DOCUMENT CONTENT ({len(all_page_texts)} pages total):

{combined}

---

USER REQUEST: {user_prompt}

---

ROLE:
You are a senior equity research analyst specialized in Indian listed companies and annual report analysis.

TASK:
Analyze the provided annual report / financial document and produce a structured investment-quality summary.

==================================================
CRITICAL FINANCIAL NORMALIZATION & VALIDATION RULES
==================================================

### 1. UNIT DETECTION IS MANDATORY
Before extracting any financial number, identify the original reporting unit exactly as written in the source.
Possible source units: lakh, crore, INR lakh, INR crore, INR million (Mn), INR billion, USD million. Never assume units.

### 2. STANDARDIZE ALL OUTPUTS INTO ₹ CRORE ONLY
Convert every extracted figure into ₹ crore format only.
Mandatory conversion rules:
- 1 crore = 100 lakh
- 1 crore = 10 million
- 1 million = 0.1 crore
- 1 billion = 100 crore
Examples:
- ₹3,88,989 lakh = ₹3,889.89 crore
- INR 7,016 Mn = ₹701.60 crore
- INR 1,100 Mn = ₹110.00 crore
Never output lakh, Mn, million, or raw source units in your final response.

### 3. EXPLICIT MATHEMATICAL CONVERSION REQUIRED
Do NOT copy values directly from source. Always detect source unit, convert mathematically, and verify final output.

### 4. CONSOLIDATED VS STANDALONE RULE
Always explicitly identify whether numbers are Consolidated or Standalone.
Priority: 1. Consolidated financials, 2. Standalone financials only if consolidated unavailable.
Never mix standalone and consolidated metrics in the same analysis.

### 5. MANDATORY ARITHMETIC VALIDATION
Before generating output, validate:
- Revenue sanity: Revenue should not inflate by 10x or 100x after conversion.
- Margin validation: Recalculate: EBITDA Margin = EBITDA / Revenue × 100; Net Margin = PAT / Revenue × 100. If reported and calculated margins mismatch materially, recompute.
- Ratio sanity: PAT cannot exceed Revenue. Operating profit cannot exceed Revenue. Reject inconsistent extraction.

### 6. OUTPUT FORMATTING RULES
Always display values as: ₹X.XX crore, and percentages with max 2 decimals. Never display lakh, Mn, million, or scientific notation.

### 7. MULTIPLE FIGURES RULE
If multiple values exist, prioritize: 1. Latest FY consolidated, 2. Latest FY standalone, 3. Quarterly only if annual unavailable.

### 8. SOURCE CONFIRMATION RULE
For every major metric, verify source section, unit, and whether consolidated or standalone.

### 9. RED FLAG FILTER
List ONLY confirmed red flags explicitly present in the document. Do NOT infer or speculate.

### 10. FINAL VALIDATION BEFORE OUTPUT
Recheck all conversions, percentages, crore formatting, ensure no lakh/Mn values remain, and ensure all metrics belong to the same reporting basis. Do NOT infer units.

==================================================
STRICT FACTUALITY & ANTI-HALLUCINATION RULES
==================================================
- Do NOT infer sector unless explicitly mentioned.
- Do NOT generate generic industry commentary.
- Do NOT fabricate growth rates.
- Do NOT fabricate promoter holding.
- Do NOT fabricate ratios.
- If a qualitative point or tailwind/headwind is not explicitly mentioned in the document, write: "Not explicitly discussed in provided document."
- If value is unavailable, write: "Not explicitly disclosed."
- If arithmetic validation fails, discard the extraction, recompute from raw values, and re-validate before final output.

==================================================
COGNITIVE WORKFLOW STEPS
==================================================
You MUST perform and display the following three steps before generating the final summary:

### STEP 1 — RAW EXTRACTION TABLE
Extract ONLY directly available raw figures from the source. Fill in this table:
| Metric | Raw Value | Original Unit | Basis (Consolidated/Standalone) | Source Section/Page |
|---|---|---|---|---|
| Revenue | | | | |
| PAT | | | | |
| Operating Profit / EBITDA | | | | |
| Other key metrics | | | | |

### STEP 2 — UNIT NORMALIZATION TABLE
Convert all extracted raw values mathematically into ₹ crore:
- Show the math: `Converted Value = Raw Value / Conversion Factor`
- E.g., `3,88,989 lakh / 100 = ₹3,889.89 crore`
- E.g., `7,016 Mn / 10 = ₹701.60 crore`

### STEP 3 — RECONCILIATION VALIDATION
Verify and show the arithmetic reconciliation:
1. Is PAT <= Revenue? (Yes/No)
2. Is EBITDA <= Revenue? (Yes/No)
3. Recalculate: EBITDA Margin = (EBITDA / Revenue) * 100. Does it match reported margins? (Show calculation)
4. Recalculate: Net Margin = (PAT / Revenue) * 100. Does it match reported margins? (Show calculation)
5. Are all values standardized to ₹ crore only? (Yes/No)

==================================================
OUTPUT FORMAT
==================================================
NOW produce the final summary using EXACTLY this format. Fill every section using data validated above:

# [COMPANY NAME]

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

Do NOT infer units. Perform explicit mathematical conversion before generating output.
"""

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a senior equity research analyst specialized in Indian listed companies and annual report analysis. When given financial document content, you MUST respond using ONLY the exact structured format requested, applying all financial normalization and validation rules. Never deviate."},
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
    if ext == ".pdf":
        doc = fitz.open(file_path)
    for page_num in pages_to_process:
        text = ""
        if ext == ".pdf":
            page = doc.load_page(page_num)
            extracted_text = page.get_text("text").strip()
            # Use native text if it contains substantial content, otherwise fall back to vision
            if len(extracted_text) > 100:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[Phase 1] [{ts}] Page {page_num + 1}/{total_pages}: Extracted native text directly (Skipped Vision)...", flush=True)
                text = extracted_text
                # print("text",text)
            else:
                b64 = page_to_base64(file_path, page_num)
                text = extract_page(b64, page_num, total_pages)
        else:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            text = extract_page(b64, page_num, total_pages)
        all_page_texts.append(text)
    if ext == ".pdf":
        doc.close()

    print("\n" + "=" * 70)
    print("PHASE 2: Synthesizing unified summary...")
    print("=" * 70)
    # print("all_page_texts",all_page_texts)

    # ── Phase 2: Synthesize into one coherent summary ──
    final_summary = synthesize_summary(all_page_texts, user_prompt)

    print("\n" + "=" * 30 + " FINAL SUMMARY " + "=" * 30)
    print(final_summary)
    print("=" * 75)

if __name__ == "__main__":
    main()
