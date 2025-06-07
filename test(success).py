import requests
import json
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- Configuration ---
# You can hardcode these here for testing, or leave them empty to be prompted
EXAM_ID = "130009"  # Example: "130009"
TRACE_ID = "12463893"  # Example: "12463893"
AUTHORIZATION_TOKEN = "74E5048C39689357846C6A33D91DECD6" # Example: "74E5048C39689357846C6A33D91DECD6"

BASE_API_URL = "https://utestapi.ulearning.cn"
BASE_OUTPUT_DIR = "ulearning_exports"

# Headers for API requests
# Based on the browser's request for getExamReport
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh",
    "authorization": AUTHORIZATION_TOKEN, # Will be updated after input
    "origin": "https://utest.ulearning.cn",
    "referer": "https://utest.ulearning.cn/",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"", # Adjust if your browser differs
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"", # Adjust if your OS differs
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36" # Adjust if your browser differs
}

# Headers for downloading images (User-Agent is often sufficient)
IMAGE_DOWNLOAD_HEADERS = {
    "User-Agent": API_HEADERS["user-agent"]
}

def sanitize_filename(filename):
    """Removes or replaces characters that are not filename-safe."""
    if filename is None:
        filename = "untitled"
    filename = str(filename)
    filename = re.sub(r'[<>:"/\\|?*\s]', '_', filename) # Replace problematic chars with underscore
    filename = re.sub(r'_+', '_', filename) # Replace multiple underscores with one
    return filename[:100] # Limit length to avoid overly long filenames

def refresh_session(ua_token, trace_id, current_headers):
    """
    Attempts to refresh the session.
    The actual effect of refresh10Session (e.g., if it returns a new token) is based on observation.
    This implementation assumes it helps keep the session alive.
    """
    refresh_url = f"{BASE_API_URL}/users/login/refresh10Session?uaToken={ua_token}&traceId={trace_id}"
    print(f"Attempting to refresh session for traceId: {trace_id}...")
    headers = current_headers.copy()
    # Ensure the authorization header is correctly set with the token for this specific call
    headers["authorization"] = ua_token 

    try:
        response = requests.get(refresh_url, headers=headers, timeout=10)
        response.raise_for_status() # Check for HTTP errors
        print("Session refresh request successful (or at least accepted by the server).")
        # If the API returned a new token in response.json(), you would extract and return it here.
        # For now, assuming it refreshes server-side and the same token continues to be valid.
        return ua_token # Return the same token
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing session: {e}")
        print("Proceeding with the current token. It might fail if it has expired.")
        return ua_token # Return original token on failure

def get_exam_report(exam_id, trace_id, auth_token, current_headers):
    """Fetches the exam report data from the API."""
    report_url = f"{BASE_API_URL}/exams/user/study/getExamReport?examId={exam_id}&traceId={trace_id}"
    print(f"Fetching exam report for examId: {exam_id}, traceId: {trace_id}...")
    
    headers = current_headers.copy()
    headers["authorization"] = auth_token # Ensure the provided token is used

    try:
        response = requests.get(report_url, headers=headers, timeout=15)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        return response.json()
    except requests.exceptions.Timeout:
        print(f"Timeout occurred while fetching exam report: {report_url}")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error fetching exam report: {e.response.status_code} - {e}")
        if e.response.status_code == 401:
            print("Authorization error (401). The provided token might be invalid or expired.")
        try:
            # Attempt to print server's error message if available
            print(f"Server response content: {e.response.text[:500]}...") 
        except Exception:
            pass # Ignore if response text itself causes an error
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching exam report: {e}")
    except json.JSONDecodeError:
        print(f"Failed to decode JSON response from {report_url}.")
        print(f"Response text (first 500 chars): {response.text[:500]}...")
    return None

def extract_image_urls_from_html(html_content):
    """Extracts all unique image URLs from an HTML string."""
    if not html_content or not isinstance(html_content, str):
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    img_tags = soup.find_all('img')
    urls = []
    for img in img_tags:
        if 'src' in img.attrs and img['src'] and img['src'].strip(): # Ensure src exists and is not empty
            urls.append(img['src'].strip())
    return list(set(urls)) # Return unique URLs

def download_image(url, save_path, headers):
    """Downloads an image from a URL and saves it to the specified save_path."""
    try:
        print(f"  Downloading image: {url} \n    to: {save_path}")
        response = requests.get(url, headers=headers, stream=True, timeout=20) # Increased timeout for larger images
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Successfully downloaded.")
        return True
    except requests.exceptions.Timeout:
        print(f"  Timeout downloading image: {url}")
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP error {e.response.status_code} downloading image {url}: {e}")
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading image {url}: {e}")
    return False

def process_exam_data_for_images(exam_json, base_exam_dir):
    """Processes the exam JSON to find, categorize, and download all images."""
    if not exam_json or 'result' not in exam_json:
        print("Exam JSON data is invalid or missing the 'result' key.")
        return

    result = exam_json['result']
    parts = result.get('part', [])

    if not parts:
        print("No 'part' array found in the exam data.")
        return

    for part_idx, part_data in enumerate(parts):
        questions = part_data.get('children', [])
        if not questions:
            print(f"No questions (children) found in part {part_idx + 1}.")
            continue

        print(f"\nProcessing Part {part_idx + 1} (Name: {part_data.get('partname', 'N/A')})...")
        for q_idx, question in enumerate(questions):
            q_order_index = question.get('orderIndex', q_idx + 1)
            q_id = question.get('questionid', f'unknownID_{q_idx+1}')
            
            question_name_prefix = f"question_{q_order_index}"
            question_folder_name = f"{question_name_prefix}_{q_id}"
            question_dir = os.path.join(base_exam_dir, question_folder_name)
            os.makedirs(question_dir, exist_ok=True)
            
            print(f" Processing Question {q_order_index} (ID: {q_id}) - files will be in '{question_folder_name}'")

            images_to_process = [] # Stores tuples of (url, suggested_filename_prefix)

            # 1. Question Title Images
            title_html = question.get('title', '')
            for i, img_url in enumerate(extract_image_urls_from_html(title_html)):
                images_to_process.append((img_url, f"title_img_{i+1}"))

            # 2. Question Item (Option) Images
            items = question.get('item', [])
            if items:
                for item_idx, item_obj in enumerate(items): # Renamed to item_obj to avoid conflict
                    item_order_index = item_obj.get('orderIndex', item_idx + 1)
                    item_title_html = item_obj.get('title', '')
                    
                    item_label_soup = BeautifulSoup(item_title_html, 'html.parser')
                    item_label_text = item_label_soup.get_text().strip()
                    # Use the text content (e.g., "A", "B") as part of filename if simple, otherwise use order index
                    prefix_label = item_label_text if (len(item_label_text) == 1 and item_label_text.isalpha()) else str(item_order_index)
                    
                    for i, img_url in enumerate(extract_image_urls_from_html(item_title_html)):
                        images_to_process.append((img_url, f"option_{prefix_label}_img_{i+1}"))
            
            # 3. Correct Answer and Replay Images
            correct_info = question.get('correctAnswerAndReplay', {})
            
            # Correct Answer(s) Images
            correct_answers_list = correct_info.get('correctAnswer', [])
            for ans_idx, ans_content_html in enumerate(correct_answers_list):
                if isinstance(ans_content_html, str): # Content can be simple text or HTML with images
                    for i, img_url in enumerate(extract_image_urls_from_html(ans_content_html)):
                        images_to_process.append((img_url, f"correct_answer_{ans_idx+1}_img_{i+1}"))

            # Correct Replay Images
            correct_replay_html = correct_info.get('correctReplay', '')
            if isinstance(correct_replay_html, str):
                for i, img_url in enumerate(extract_image_urls_from_html(correct_replay_html)):
                    images_to_process.append((img_url, f"correct_replay_img_{i+1}"))
            
            # Download all unique images collected for this question
            downloaded_urls_in_question = set()
            for img_url, filename_prefix in images_to_process:
                if not img_url.startswith(('http://', 'https://')):
                    print(f"  Skipping invalid or relative URL: {img_url}")
                    continue
                if img_url in downloaded_urls_in_question: 
                    # This check is useful if the same image URL appears in multiple places within one question
                    # (e.g. title and answer) and you want to download it only once per question.
                    # print(f"  Skipping already processed URL for this question: {img_url}")
                    continue 
                
                parsed_url = urlparse(img_url)
                original_filename = os.path.basename(parsed_url.path)
                _, ext = os.path.splitext(original_filename)
                if not ext or len(ext) > 5 : # Basic check for valid extension
                    ext = ".png" # Default extension if not found or seems invalid

                save_filename = f"{filename_prefix}{ext}"
                save_path = os.path.join(question_dir, save_filename)
                
                if download_image(img_url, save_path, IMAGE_DOWNLOAD_HEADERS):
                    downloaded_urls_in_question.add(img_url)

def main():
    global EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN, API_HEADERS

    print("--- 优学院考试图片导出工具 ---")

    # Get user inputs if not hardcoded
    if not EXAM_ID:
        EXAM_ID = input("请输入 Exam ID (例如 130009): ").strip()
    if not TRACE_ID:
        TRACE_ID = input("请输入 Trace ID (例如 12463893): ").strip()
    if not AUTHORIZATION_TOKEN:
        AUTHORIZATION_TOKEN = input("请输入 Authorization Token: ").strip()

    if not all([EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN]):
        print("错误: Exam ID, Trace ID, 和 Authorization Token 都是必填项。脚本将退出。")
        return

    # Update API_HEADERS with the provided token
    API_HEADERS["authorization"] = AUTHORIZATION_TOKEN
    
    # 1. Attempt to refresh session (optional but recommended)
    # The current refresh_session function is designed to ping the endpoint. 
    # If it were to reliably return a new token, that new token should be used.
    # For now, we assume the original token's validity might be extended by this call.
    refreshed_token = refresh_session(AUTHORIZATION_TOKEN, TRACE_ID, API_HEADERS)
    # If refresh_session was designed to return a new token and did so:
    # AUTHORIZATION_TOKEN = refreshed_token
    # API_HEADERS["authorization"] = AUTHORIZATION_TOKEN


    # 2. Get Exam Report Data
    exam_data = get_exam_report(EXAM_ID, TRACE_ID, AUTHORIZATION_TOKEN, API_HEADERS)

    if not exam_data:
        print("未能获取到考试数据。请仔细检查输入的ID、Token是否正确，网络连接是否正常，以及Token是否已过期。")
        return

    # Create base output directory for this specific exam
    exam_title_from_json = exam_data.get("result", {}).get("examTitle", "UnknownExamTitle")
    sanitized_exam_title = sanitize_filename(exam_title_from_json)
    
    current_exam_dir_name = f"exam_{EXAM_ID}_{sanitized_exam_title}"
    current_exam_output_dir = os.path.join(BASE_OUTPUT_DIR, current_exam_dir_name)
    
    os.makedirs(current_exam_output_dir, exist_ok=True)
    print(f"\n所有图片和数据将保存到主目录: {current_exam_output_dir}")

    # 3. Process exam data to extract and download images
    process_exam_data_for_images(exam_data, current_exam_output_dir)

    print("\n--- 图片导出处理完成 ---")
    print(f"请检查输出目录: {os.path.abspath(current_exam_output_dir)}")

if __name__ == "__main__":
    main()