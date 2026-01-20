#!/bin/bash

# Example: Test the new API format with curl
# This script demonstrates how to call the streaming API and see the wrapped format

API_URL="http://localhost:8000/v1/chat/completions"

echo "Testing MiroThinker API with new wrapped format..."
echo "=================================================="
echo ""

curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {
        "role": "user",
        "content": "什么是人工智能？"
      }
    ],
    "stream": true
  }' \
  --no-buffer | while IFS= read -r line; do
    # Skip empty lines and [DONE] marker
    if [[ "$line" =~ ^data:\ \[DONE\] ]]; then
      echo ""
      echo "Stream completed."
      break
    elif [[ "$line" =~ ^data:\ \{.*\}$ ]]; then
      # Extract JSON after "data: "
      json_data="${line#data: }"
      
      # Pretty print the JSON (requires jq)
      if command -v jq &> /dev/null; then
        echo "$json_data" | jq '.'
      else
        echo "$json_data"
      fi
      echo "---"
    fi
  done

echo ""
echo "=================================================="
echo "Expected format:"
echo ""
echo '{'
echo '  "type": "chat",'
echo '  "messageId": "uuid-here",'
echo '  "chatResp": {'
echo '    "id": "chatcmpl-xxx",'
echo '    "object": "chat.completion.chunk",'
echo '    "created": 1737300000,'
echo '    "model": "mirothinker",'
echo '    "choices": [{'
echo '      "index": 0,'
echo '      "delta": {'
echo '        "taskstat": "message_start",'
echo '        "role": "task",'
echo '        "content_type": "research_process_block",'
echo '        "task_content": "{\"label\": \"正在收集和分析资料\"}",'
echo '        "content": "",'
echo '        "taskid": "1737300000123000"'
echo '      },'
echo '      "finish_reason": null'
echo '    }]'
echo '  }'
echo '}'
echo ""
echo "Note: Install jq for pretty printing: brew install jq (macOS) or apt install jq (Linux)"

