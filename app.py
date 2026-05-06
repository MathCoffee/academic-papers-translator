import os
import uuid
import threading
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from progress import update_progress
from translate_article import process_docx, convert_pdf_to_docx

# Attempt to load genai
try:
    from google import genai
except ImportError:
    genai = None

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50 MB limit

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('tasks', exist_ok=True)

def run_translation_task(task_id, input_path, direction, api_key):
    try:
        update_progress(task_id, "processing", 10, "Initializing Google Gemini Client...")
        client = genai.Client(api_key=api_key)
        
        base_name, ext = os.path.splitext(input_path)
        ext = ext.lower()
        suffix = "_ES" if direction == "en2es" else "_EN"
        output_path = f"{base_name}{suffix}.docx"
        
        if ext == ".pdf":
            temp_docx_path = f"{base_name}_temp.docx"
            update_progress(task_id, "processing", 20, "Converting PDF to DOCX...")
            convert_pdf_to_docx(input_path, temp_docx_path)
            
            update_progress(task_id, "processing", 40, "Translating document...")
            # We pass task_id to process_docx so it can update progress
            process_docx(temp_docx_path, output_path, client, direction, task_id=task_id)
            
            if os.path.exists(temp_docx_path):
                os.remove(temp_docx_path)
        else:
            update_progress(task_id, "processing", 20, "Translating document...")
            process_docx(input_path, output_path, client, direction, task_id=task_id)
            
        update_progress(task_id, "done", 100, "Translation complete!", result_file=output_path)
        
    except Exception as e:
        update_progress(task_id, "error", 0, f"Error: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    direction = request.form.get('direction', 'en2es')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if not (file.filename.lower().endswith('.pdf') or file.filename.lower().endswith('.docx')):
        return jsonify({'error': 'Only PDF and DOCX files are allowed'}), 400
        
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({'error': 'GEMINI_API_KEY environment variable is not set on the server.'}), 500

    if file:
        filename = secure_filename(file.filename)
        task_id = str(uuid.uuid4())
        
        # Save file with task_id to avoid collisions
        safe_filename = f"{task_id}_{filename}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(input_path)
        
        update_progress(task_id, "processing", 0, "Upload complete. Starting translation...")
        
        # Start background thread
        thread = threading.Thread(target=run_translation_task, args=(task_id, input_path, direction, api_key))
        thread.daemon = True
        thread.start()
        
        return jsonify({'task_id': task_id}), 200

@app.route('/status/<task_id>')
def status(task_id):
    task_file = f"tasks/{task_id}.json"
    if not os.path.exists(task_file):
        return jsonify({'status': 'not_found', 'message': 'Task not found'}), 404
        
    with open(task_file, 'r') as f:
        import json
        data = json.load(f)
        return jsonify(data)

@app.route('/download/<task_id>')
def download(task_id):
    task_file = f"tasks/{task_id}.json"
    if not os.path.exists(task_file):
        return "Task not found", 404
        
    with open(task_file, 'r') as f:
        import json
        data = json.load(f)
        
    if data.get('status') != 'done' or 'result_file' not in data:
        return "File not ready", 400
        
    result_file = data['result_file']
    if os.path.exists(result_file):
        # Send file and then we could optionally clean it up, but for now just send it
        filename = os.path.basename(result_file)
        # Remove the UUID prefix from download name
        if "_" in filename:
            original_name = filename.split("_", 1)[1]
        else:
            original_name = filename
            
        return send_file(result_file, as_attachment=True, download_name=original_name)
    else:
        return "File not found on server", 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
