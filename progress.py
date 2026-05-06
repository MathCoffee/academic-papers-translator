import os
import json

def update_progress(task_id, status, progress, message, result_file=None):
    if not task_id:
        return
    
    os.makedirs('tasks', exist_ok=True)
    task_file = f"tasks/{task_id}.json"
    
    data = {
        "status": status,
        "progress": progress,
        "message": message
    }
    if result_file:
        data["result_file"] = result_file
        
    with open(task_file, 'w') as f:
        json.dump(data, f)

