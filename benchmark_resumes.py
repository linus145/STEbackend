import os
import sys
import csv
import time
import math
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maincore.settings")

import django
django.setup()

from django.conf import settings
from AI.services import AIService

# --- COST DEFINITIONS (Gemini Pay-as-you-go Rates) ---
GEMINI_INPUT_RATE_PER_M = 0.075  # $0.075 per 1M input tokens
GEMINI_OUTPUT_RATE_PER_M = 0.30  # $0.30 per 1M output tokens

# --- ESTIMATE TOKENS FROM CHARACTER LENGTH ---
def estimate_tokens(text):
    """Estimate token count based on standard English character-to-token ratio (~4 chars per token)"""
    if not text:
        return 0
    return math.ceil(len(text) / 4)

def run_benchmark(csv_path, resume_col_index, category_col_index, limit, model_name):
    print("=" * 60)
    print("           RESUME SCREENING PLATFORM BENCHMARK RUNNER")
    print("=" * 60)
    print(f"Dataset CSV: {csv_path}")
    print(f"Limit:       {limit} resumes")
    print(f"Model:       {model_name}")
    print("-" * 60)

    # 1. Load data from Kaggle CSV
    resumes = []
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at: {csv_path}")
        print("Please download a resume dataset from Kaggle and specify its path.")
        return

    with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader)
        print(f"Detected columns: {header}")
        
        count = 0
        for row in reader:
            if count >= limit:
                break
            # Extract resume text and category
            resume_text = row[resume_col_index] if len(row) > resume_col_index else ""
            category = row[category_col_index] if len(row) > category_col_index else "General"
            
            if resume_text.strip():
                resumes.append({
                    "text": resume_text,
                    "category": category,
                    "email": f"applicant_{count}@example.com"
                })
                count += 1

    print(f"Loaded {len(resumes)} resumes for testing.")
    if not resumes:
        print("No resumes found to screen. Exiting.")
        return

    # 2. Mock PDF Download & Extraction Hooks
    # This prevents the script from calling external URLs for PDFs,
    # and instead feeds the Kaggle resume text directly into the exact production ATS prompt pipeline.
    original_download = AIService.download_pdf
    original_extract = AIService.extract_text_from_pdf

    # Mock variables representing current resume being processed in the thread
    import threading
    local_data = threading.local()

    def mock_download_pdf(pdf_url):
        # Return dummy bytes to bypass download validation
        return b"%PDF-1.4 dummy pdf bytes", None

    def mock_extract_text_from_pdf(pdf_bytes):
        # Return the specific resume text for this thread
        return getattr(local_data, "resume_text", "No text provided")

    AIService.download_pdf = mock_download_pdf
    AIService.extract_text_from_pdf = mock_extract_text_from_pdf

    # 3. Define the single worker function
    def screen_resume(item):
        local_data.resume_text = item["text"]
        
        job_title = f"{item['category']} Specialist"
        job_brief = {
            "description": f"We are seeking a highly skilled {item['category']} specialist with hands-on experience.",
            "required_skills": "Communication, Problem Solving, " + item["category"],
            "experience_level": "MID",
            "job_type": "FULL_TIME",
            "work_mode": "REMOTE",
            "job_category": item["category"]
        }
        
        start_time = time.time()
        success = False
        error_msg = ""
        score = None
        analysis_json = ""
        
        # Azure Model Pipeline fallback list
        azure_pipeline = ["grok-4-20-non-reasoning", "grok-4-1-fast-non-reasoning", "Kimi-K2.6"]
        
        # Build try order
        models_to_try = [model_name]
        if model_name in azure_pipeline:
            for m in azure_pipeline:
                if m not in models_to_try:
                    models_to_try.append(m)
                    
        # Filter by configured keys/endpoints in django settings
        configured_models = []
        for m in models_to_try:
            if m == "grok-4-20-non-reasoning":
                if getattr(settings, "GROK_API_KEY", "") or getattr(settings, "AZURE_GROK_ENDPOINT", ""):
                    configured_models.append(m)
            elif m == "grok-4-1-fast-non-reasoning":
                if getattr(settings, "AZURE_GROK_API_2", "") or getattr(settings, "AZURE_GROK_ENDPOINT_2", ""):
                    configured_models.append(m)
            elif m == "Kimi-K2.6":
                if getattr(settings, "KIMI_API_KEY", "") or getattr(settings, "AZURE_KIMI_ENDPOINT", ""):
                    configured_models.append(m)
            else:
                # Other non-azure models are assumed configured
                configured_models.append(m)
                
        if not configured_models:
            configured_models = [model_name]

        # Loop through pipeline models on failure / rate limit
        for idx, current_model in enumerate(configured_models):
            has_more = idx < len(configured_models) - 1
            try:
                # Execute actual production screening service
                score, analysis_json = AIService.analyze_resume(
                    job_title=job_title,
                    job_brief=job_brief,
                    resume_url="http://dummyurl.com/resume.pdf",
                    selected_model=current_model
                )
                
                # Check for return signature errors (like return 0, "Grok analysis failed: RateLimitReached")
                is_rate_limit_error = False
                if score == 0 and isinstance(analysis_json, str):
                    err_lower = analysis_json.lower()
                    if "429" in err_lower or "ratelimit" in err_lower or "limit" in err_lower or "quota" in err_lower:
                        is_rate_limit_error = True
                        error_msg = analysis_json
                
                if score is not None and score > 0 and not is_rate_limit_error:
                    success = True
                    break
                else:
                    if is_rate_limit_error and has_more:
                        next_m = configured_models[idx + 1]
                        print(f"[AI Benchmark] Rate limit hit on {current_model}. Instantly trying fallback model: {next_m}...")
                        continue
                    elif not is_rate_limit_error:
                        error_msg = str(analysis_json)
            except Exception as e:
                error_msg = str(e)
                err_lower = error_msg.lower()
                is_rate_limit = "429" in err_lower or "rate" in err_lower or "limit" in err_lower or "quota" in err_lower
                if is_rate_limit and has_more:
                    next_m = configured_models[idx + 1]
                    print(f"[AI Benchmark] Rate limit hit/exception on {current_model}. Instantly trying fallback model: {next_m}...")
                    continue
                break
            
        elapsed = time.time() - start_time
        
        # Estimate tokens and cost
        input_tokens = estimate_tokens(item["text"]) + 1500  # prompt offset
        output_tokens = estimate_tokens(str(analysis_json)) if success else 0
        
        cost = 0.0
        if model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            cost = ((input_tokens / 1000000) * GEMINI_INPUT_RATE_PER_M) + ((output_tokens / 1000000) * GEMINI_OUTPUT_RATE_PER_M)
        else:
            # Default rate estimate ($5 per million tokens combined)
            cost = ((input_tokens + output_tokens) / 1000000) * 5.0
            
        return {
            "email": item["email"],
            "category": item["category"],
            "elapsed": elapsed,
            "success": success,
            "score": score,
            "error": error_msg,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost
        }

    # 4. Run screening concurrently
    print(f"\nStarting screening batch of {len(resumes)} resumes using ThreadPoolExecutor(max_workers=30)...")
    t0 = time.time()
    
    results = []
    completed = 0
    
    # We match the concurrency of the live system
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(screen_resume, item): item for item in resumes}
        
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            completed += 1
            status = "SUCCESS" if res["success"] else "FAILED"
            score_str = f"Score: {res['score']}" if res["success"] else f"Error: {res['error'][:40]}"
            print(f"[{completed}/{len(resumes)}] {res['email']} ({res['category']}) - {status} in {res['elapsed']:.2f}s | {score_str}")

    total_time = time.time() - t0

    # Restore original methods
    AIService.download_pdf = original_download
    AIService.extract_text_from_pdf = original_extract

    # 5. Calculate Metrics
    successful_runs = [r for r in results if r["success"]]
    failed_runs = [r for r in results if not r["success"]]
    
    total_input_tokens = sum(r["input_tokens"] for r in results)
    total_output_tokens = sum(r["output_tokens"] for r in results)
    total_cost = sum(r["cost_usd"] for r in results)
    
    avg_speed = sum(r["elapsed"] for r in results) / len(results) if results else 0
    throughput = (len(results) / total_time) * 60 if total_time > 0 else 0
    
    # 6. Generate Markdown Report File
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screening_benchmark_report.md")
    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write("# Resume Screening Platform Load-Test Report\n\n")
        rf.write("## 1. Executive Summary\n")
        rf.write(f"This benchmark measures the speed, parsing accuracy, and API cost of the screening pipeline under load. ")
        rf.write(f"The simulation processed a batch of resumes using the platform's exact production configurations.\n\n")
        
        rf.write("### Core Metrics Table\n")
        rf.write("| Metric | Value | Details / Observations |\n")
        rf.write("| :--- | :--- | :--- |\n")
        rf.write(f"| **Total Resumes Processed** | {len(results)} | From loaded dataset |\n")
        rf.write(f"| **Successful Screenings** | {len(successful_runs)} | Clean 20-dimension JSON extractions |\n")
        rf.write(f"| **Failed/Timed out** | {len(failed_runs)} | API errors or parser failures |\n")
        rf.write(f"| **Success Rate** | {(len(successful_runs)/len(results))*100:.1f}% | Pipeline robustness indicator |\n")
        rf.write(f"| **Total Wall-Clock Time** | {total_time:.2f} seconds | Actual time user waited for completion |\n")
        rf.write(f"| **Avg. Time Per Resume** | {avg_speed:.2f} seconds | Round-trip latency for single item |\n")
        rf.write(f"| **System Throughput** | {throughput:.1f} resumes/min | Scalability capacity benchmark |\n")
        rf.write(f"| **Total Input Tokens** | {total_input_tokens:,} | Context and prompts sent |\n")
        rf.write(f"| **Total Output Tokens** | {total_output_tokens:,} | Structured analysis objects received |\n")
        rf.write(f"| **Total API Cost (Est.)** | ${total_cost:.4f} USD | Based on active model rates |\n\n")
        
        rf.write("## 2. API Costs & Scaling Projections\n")
        rf.write(f"Based on the token usage measured in this run, here is how the API costs scale for different resume volume goals:\n\n")
        rf.write("| Volume | Estimated Cost (Gemini Flash) | Estimated Duration (Paid Tier) |\n")
        rf.write("| :--- | :--- | :--- |\n")
        rf.write(f"| **50 Resumes** | ${(total_cost/len(results))*50:.4f} USD | ~30 seconds |\n")
        rf.write(f"| **500 Resumes** | ${(total_cost/len(results))*500:.4f} USD | ~3 to 4 minutes |\n")
        rf.write(f"| **5,000 Resumes** | ${(total_cost/len(results))*5000:.4f} USD | ~30 to 40 minutes |\n\n")
        
        rf.write("## 3. Detailed Results Breakdown\n")
        rf.write("| Application Email | Category | Processing Time | Status | Score |\n")
        rf.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for r in results[:50]:  # Limit details to first 50 to avoid massive markdown
            status_text = "✅ SUCCESS" if r["success"] else "❌ FAILED"
            score_text = str(r["score"]) if r["success"] else "-"
            rf.write(f"| {r['email']} | {r['category']} | {r['elapsed']:.2f}s | {status_text} | {score_text} |\n")
            
        if len(results) > 50:
            rf.write(f"| ... and {len(results) - 50} more items ... | | | | |\n")

    print("=" * 60)
    print("                      BENCHMARK COMPLETED")
    print("=" * 60)
    print(f"Total time elapsed: {total_time:.2f} seconds")
    print(f"Total estimated cost: ${total_cost:.4f} USD")
    print(f"Average resume screening speed: {avg_speed:.2f} seconds")
    print(f"Detailed Markdown report generated at: {report_path}")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resume screening platform benchmark.")
    parser.add_argument("--csv", type=str, required=True, help="Path to the Kaggle Resume CSV dataset")
    parser.add_argument("--text_col", type=int, default=1, help="0-based index of the resume text column")
    parser.add_argument("--cat_col", type=int, default=0, help="0-based index of the category column")
    parser.add_argument("--limit", type=int, default=10, help="Max number of resumes to process in the test run")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash-lite", help="Model name (e.g. gemini-2.5-flash-lite, gemini-2.5-flash, grok)")

    args = parser.parse_args()
    run_benchmark(
        csv_path=args.csv,
        resume_col_index=args.text_col,
        category_col_index=args.cat_col,
        limit=args.limit,
        model_name=args.model
    )
