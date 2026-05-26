python3 -m venv venv
source venv/bin/activate
pip install -e .
python main.py


 ollama run llama3.1


# To open in VS Code:
code ~/.tradingagents/memory/trading_memory.md
# Or to just print it in the terminal:
cat ~/.tradingagents/memory/trading_memory.md


# Keep model loaded in RAM indefinitely (no auto-unload between files)
export OLLAMA_KEEP_ALIVE=-1

# Run the full batch without the Mac ever sleeping:
caffeinate -i bash process_folder.sh /Users/atmanand./Downloads/reports "Annual report analysis" all


# If you want to close the laptop lid and still run:
caffeinate -s bash process_folder.sh /Users/atmanand./Downloads/reports "Annual report analysis" all

# To know all the porcess runing 
ollama ps

ollama stop qwen2.5vl:3b
ollama stop llama3.1


top -o MEM
