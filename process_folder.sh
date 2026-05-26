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
# ── Load Environment Variables Safely ──
if [ -f "$SCRIPT_DIR/.env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip commented or empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ ! "$line" =~ = ]] && continue
        
        # Strip inline comments (anything after #)
        clean_line="${line%%#*}"
        
        # Extract and trim key/value
        key=$(echo "${clean_line%%=*}" | tr -d '[:space:]')
        value=$(echo "${clean_line#*=}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'' ]*//' -e 's/["'\'' ]*$//')
        
        if [ -n "$key" ]; then
            export "$key=$value"
        fi
    done < "$SCRIPT_DIR/.env"
fi

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
        
        # ── Rename the report to the actual Company Name ──
        # Extract the first H1 header line starting with #
        COMPANY_NAME=$(grep -m 1 "^# " "$OUTPUT_FILE" | sed 's/^# //')
        if [ -n "$COMPANY_NAME" ]; then
            # Sanitize filename (keep only safe alphanumeric, space, dash, and underscore)
            SAFE_COMPANY_NAME=$(echo "$COMPANY_NAME" | tr -cd 'A-Za-z0-9_ -')
            if [ -n "$SAFE_COMPANY_NAME" ]; then
                RENAMED_FILE="$OUTPUT_DIR/${SAFE_COMPANY_NAME}_analysis.txt"
                mv "$OUTPUT_FILE" "$RENAMED_FILE"
                OUTPUT_FILE="$RENAMED_FILE"
            fi
        fi

        echo "✅ Saved: $OUTPUT_FILE"
        ((SUCCESS++))

        # ── Send to Telegram if tokens configured ──
        if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
            echo "Sending report to Telegram..."
            curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
                 -F chat_id="${TELEGRAM_CHAT_ID}" \
                 -F document=@"${OUTPUT_FILE}" \
                 -F caption="📊 Investment Report: $(basename "$OUTPUT_FILE" _analysis.txt)" >/dev/null
        fi
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
