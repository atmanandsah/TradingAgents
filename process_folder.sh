#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# process_folder.sh
# Batch process all PDF files in a folder using test_qwen_pdf.py
#
# Usage:
#   bash process_folder.sh /path/to/folder [prompt] [page_range]
#
# Examples:
#   bash process_folder.sh /Users/atmanand./Downloads/reports
#   bash process_folder.sh /Users/atmanand./Downloads/reports "Annual report analysis" all
#   bash process_folder.sh /Users/atmanand./Downloads/reports "Extract tables" 1-5
# ──────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python"
QWEN_SCRIPT="$SCRIPT_DIR/test_qwen_pdf.py"

# ── Arguments ──
FOLDER="${1:?Usage: bash process_folder.sh <folder_path> [prompt] [page_range]}"
PROMPT="${2:-Annual report investment analysis}"
PAGE_RANGE="${3:-all}"

# ── Validate ──
if [ ! -d "$FOLDER" ]; then
    echo "ERROR: Folder not found: $FOLDER"
    exit 1
fi

if [ ! -f "$QWEN_SCRIPT" ]; then
    echo "ERROR: test_qwen_pdf.py not found at $QWEN_SCRIPT"
    exit 1
fi

# ── Output folder (saved alongside input folder, not inside it) ──
OUTPUT_DIR="${FOLDER%/}_analysis_reports"
mkdir -p "$OUTPUT_DIR"

# ── Find all PDF files (macOS bash 3.2 compatible) ──
PDF_FILES=()
while IFS= read -r -d '' f; do
    PDF_FILES+=("$f")
done < <(find "$FOLDER" -maxdepth 1 -name "*.pdf" -print0 | sort -z)

TOTAL=${#PDF_FILES[@]}
if [ "$TOTAL" -eq 0 ]; then
    echo "No PDF files found in: $FOLDER"
    exit 1
fi

echo "============================================================"
echo "Batch PDF Analysis"
echo "Folder     : $FOLDER"
echo "Files found: $TOTAL"
echo "Prompt     : $PROMPT"
echo "Pages      : $PAGE_RANGE"
echo "Output dir : $OUTPUT_DIR"
echo "============================================================"
echo ""

# ── Process each PDF ──
SUCCESS=0
FAILED=0

for i in "${!PDF_FILES[@]}"; do
    PDF="${PDF_FILES[$i]}"
    BASENAME=$(basename "$PDF" .pdf)
    OUTPUT_FILE="$OUTPUT_DIR/${BASENAME}_analysis.txt"

    echo "------------------------------------------------------------"
    echo "[$((i+1))/$TOTAL] Processing: $BASENAME.pdf"
    echo "------------------------------------------------------------"

    # Run the analysis and save output
    if "$PYTHON" "$QWEN_SCRIPT" "$PDF" "$PROMPT" "$PAGE_RANGE" 2>&1 | tee "$OUTPUT_FILE"; then
        echo ""
        echo "✅ Saved: $OUTPUT_FILE"
        ((SUCCESS++))
    else
        echo ""
        echo "❌ Failed: $BASENAME.pdf"
        ((FAILED++))
    fi

    echo ""
    # Small pause between files to let Ollama unload memory
    sleep 2
done

echo "============================================================"
echo "BATCH COMPLETE"
echo "  Processed : $TOTAL files"
echo "  Success   : $SUCCESS"
echo "  Failed    : $FAILED"
echo "  Reports   : $OUTPUT_DIR"
echo "============================================================"
