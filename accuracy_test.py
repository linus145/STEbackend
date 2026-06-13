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

def run_accuracy_test(csv_path, model_name, limit, threshold):
    print("=" * 70)
    print("        ATS SCREENING ACCURACY BENCHMARK - SOFTWARE ENGINEER (IT)")
    print("=" * 70)
    print(f"Dataset CSV: {csv_path}")
    print(f"Base Model:  {model_name}")
    print(f"Total Limit: {limit} resumes ({limit//2} IT + {limit//2} Non-IT)")
    print(f"Threshold:   {threshold}")
    print("-" * 70)

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at: {csv_path}")
        return

    half_limit = limit // 2

    # 1. Load IT Resumes and Non-IT Resumes
    it_resumes = []
    non_it_resumes = []
    
    with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader)
        
        it_count = 0
        non_it_count = 0
        
        for row in reader:
            if len(row) < 4:
                continue
            category = row[3].strip()
            resume_text = row[1].strip()
            
            if not resume_text:
                continue
                
            if category == "INFORMATION-TECHNOLOGY" and it_count < half_limit:
                it_resumes.append({
                    "text": resume_text,
                    "category": category,
                    "is_relevant_ground_truth": True,
                    "email": f"it_candidate_{it_count}@example.com"
                })
                it_count += 1
            elif category in ["HR", "TEACHER", "CHEF", "SALES", "ACCOUNTANT", "ADVOCATE"] and non_it_count < half_limit:
                non_it_resumes.append({
                    "text": resume_text,
                    "category": category,
                    "is_relevant_ground_truth": False,
                    "email": f"non_it_candidate_{non_it_count}@example.com"
                })
                non_it_count += 1
                
            if it_count >= half_limit and non_it_count >= half_limit:
                break

    test_batch = it_resumes + non_it_resumes
    print(f"Loaded {len(it_resumes)} IT Resumes and {len(non_it_resumes)} Non-IT Resumes (Total: {len(test_batch)})")
    
    if len(test_batch) < limit:
        print(f"Warning: Only loaded {len(test_batch)} resumes instead of the requested {limit} due to dataset constraints.")

    # 2. Mock PDF Download & Extraction Hooks
    original_download = AIService.download_pdf
    original_extract = AIService.extract_text_from_pdf

    import threading
    local_data = threading.local()

    AIService.download_pdf = lambda url: (b"%PDF-1.4 dummy pdf bytes", None)
    AIService.extract_text_from_pdf = lambda pdf_bytes: getattr(local_data, "resume_text", "No text")

    # 3. Define screening job description and evaluation loop
    def screen_resume(item):
        local_data.resume_text = item["text"]
        
        job_title = "Software Engineer / IT Specialist"
        job_brief = {
            "description": (
                "We are seeking an IT professional to support software installation, manage database systems, "
                "troubleshoot network connectivity, and perform systems administration tasks. "
                "You will coordinate technical support and assist in software deployment projects."
            ),
            "required_skills": "Information Technology, Systems Administration, Technical Support, Troubleshooting, Database, Networking, Project Management",
            "experience_level": "MID",
            "job_type": "FULL_TIME",
            "work_mode": "REMOTE",
            "job_category": "INFORMATION-TECHNOLOGY"
        }
        
        score = None
        success = False
        error_msg = ""
        analysis_json = ""
        
        azure_pipeline = ["grok-4-20-non-reasoning", "grok-4-1-fast-non-reasoning", "Kimi-K2.6"]
        models_to_try = [model_name]
        if model_name in azure_pipeline:
            for m in azure_pipeline:
                if m not in models_to_try:
                    models_to_try.append(m)
                    
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
                configured_models.append(m)
                
        if not configured_models:
            configured_models = [model_name]

        # Execute screening using pipeline fallback
        for idx, current_model in enumerate(configured_models):
            has_more = idx < len(configured_models) - 1
            try:
                score, analysis_json = AIService.analyze_resume(
                    job_title=job_title,
                    job_brief=job_brief,
                    resume_url="http://dummyurl.com/resume.pdf",
                    selected_model=current_model
                )
                
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
                        print(f"[AI Accuracy Test] Rate limit hit on {current_model}. Instantly trying fallback model: {next_m}...")
                        continue
                    elif not is_rate_limit_error:
                        error_msg = str(analysis_json)
            except Exception as e:
                error_msg = str(e)
                err_lower = error_msg.lower()
                is_rate_limit = "429" in err_lower or "rate" in err_lower or "limit" in err_lower or "quota" in err_lower
                if is_rate_limit and has_more:
                    next_m = configured_models[idx + 1]
                    print(f"[AI Accuracy Test] Rate limit exception on {current_model}. Instantly trying fallback: {next_m}...")
                    continue
                break
                
        matching_skills = "N/A"
        missing_skills = "N/A"
        experience_match = "N/A"
        education_match = "N/A"
        ai_summary = "N/A"
        recommendation = "N/A"
        
        if success and analysis_json:
            try:
                import json
                clean_json = analysis_json.strip()
                if clean_json.startswith('```json'):
                    clean_json = clean_json[7:]
                if clean_json.endswith('```'):
                    clean_json = clean_json[:-3]
                ai_data = json.loads(clean_json.strip())
                
                intel = ai_data.get("intelligence", {})
                rv = ai_data.get("recruiter_view", {})
                
                # Matching Skills
                matched_list = intel.get("skills_assessment", {}).get("matched_required", [])
                if matched_list:
                    matching_skills = ", ".join([s.get("skill") if isinstance(s, dict) else str(s) for s in matched_list])
                    
                # Missing Skills
                missing_list = intel.get("skills_assessment", {}).get("missing_required", [])
                if missing_list:
                    missing_skills = ", ".join([s.get("skill") if isinstance(s, dict) else str(s) for s in missing_list])
                    
                # Experience
                exp_years = intel.get("career_summary", {}).get("total_years_experience")
                exp_level = intel.get("career_summary", {}).get("career_level_assessed")
                if exp_years is not None:
                    experience_match = f"{exp_years} yrs ({exp_level})"
                    
                # Education
                edu_list = intel.get("education", [])
                if edu_list:
                    top_edu = edu_list[0]
                    education_match = f"{top_edu.get('degree', 'Degree')} from {top_edu.get('institution', 'Institution')}"
                    
                # AI Summary
                ai_summary = intel.get("professional_summary", {}).get("summary_text") or rv.get("recommendation_reason") or "N/A"
                recommendation = rv.get("recommendation", "N/A")
            except Exception as pe:
                pass
                
        return {
            "email": item["email"],
            "category": item["category"],
            "is_relevant_ground_truth": item["is_relevant_ground_truth"],
            "success": success,
            "score": score if success else 0,
            "error": error_msg,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "experience_match": experience_match,
            "education_match": education_match,
            "ai_summary": ai_summary,
            "recommendation": recommendation
        }

    # 4. Run Batch Screenings Concurrently
    print(f"\nProcessing {len(test_batch)} evaluations using ThreadPoolExecutor(max_workers=30)...")
    results = []
    completed = 0
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(screen_resume, item): item for item in test_batch}
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            completed += 1
            status = "SUCCESS" if res["success"] else "FAILED"
            score_str = f"Score: {res['score']}" if res["success"] else f"Error: {res['error'][:40]}"
            gt_str = "RELEVANT (IT)" if res["is_relevant_ground_truth"] else "NOT-RELEVANT"
            print(f"[{completed}/{len(test_batch)}] {res['email']} ({res['category']}) [{gt_str}] -> {status} | {score_str}")

    total_time = time.time() - t0

    # Restore overrides
    AIService.download_pdf = original_download
    AIService.extract_text_from_pdf = original_extract

    # 5. Sort results descending
    sorted_results = sorted(results, key=lambda c: c["score"], reverse=True)

    # 6. Calculate Confusion Matrix based on custom threshold
    TP = sum(1 for r in results if r["score"] >= threshold and r["is_relevant_ground_truth"])
    FP = sum(1 for r in results if r["score"] >= threshold and not r["is_relevant_ground_truth"])
    FN = sum(1 for r in results if r["score"] < threshold and r["is_relevant_ground_truth"])
    TN = sum(1 for r in results if r["score"] < threshold and not r["is_relevant_ground_truth"])

    # Precision, Recall, F1
    precision = (TP / (TP + FP)) * 100 if (TP + FP) > 0 else 0.0
    recall = (TP / (TP + FN)) * 100 if (TP + FN) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # Top 10 Precision
    top_10 = sorted_results[:10]
    tp_10 = sum(1 for r in top_10 if r["is_relevant_ground_truth"])
    precision_10 = (tp_10 / len(top_10)) * 100 if len(top_10) > 0 else 0.0

    # Top 20 Precision
    top_20 = sorted_results[:20]
    tp_20 = sum(1 for r in top_20 if r["is_relevant_ground_truth"])
    precision_20 = (tp_20 / len(top_20)) * 100 if len(top_20) > 0 else 0.0

    # Mean Scores
    relevant_scores = [r["score"] for r in results if r["is_relevant_ground_truth"]]
    non_relevant_scores = [r["score"] for r in results if not r["is_relevant_ground_truth"]]
    mean_relevant = sum(relevant_scores) / len(relevant_scores) if relevant_scores else 0.0
    mean_non_relevant = sum(non_relevant_scores) / len(non_relevant_scores) if non_relevant_scores else 0.0

    # 7. Generate Accuracy Report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accuracy_test_report.md")
    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write(f"# Software Engineer (IT) ATS Accuracy Report (Batch Size: {len(test_batch)})\n\n")
        rf.write("## 1. Executive Summary\n")
        rf.write(f"This report evaluates the relevance classification metrics of the ATS screening engine. ")
        rf.write(f"The benchmark matched {len(it_resumes)} actual IT resumes against a control group of {len(non_it_resumes)} non-IT resumes ")
        rf.write(f"with the shortlisting threshold set to **Score >= {threshold}**.\n\n")
        
        rf.write("### Accuracy Metrics Table\n")
        rf.write("| Metric | Value | Description / Observations |\n")
        rf.write("| :--- | :--- | :--- |\n")
        rf.write(f"| **Total Resumes Screened** | {len(test_batch)} | Half IT + Half non-IT control |\n")
        rf.write(f"| **True Positives (TP)** | {TP} | IT resumes correctly selected (Score >= {threshold}) |\n")
        rf.write(f"| **False Positives (FP)** | {FP} | Non-IT resumes incorrectly selected (Score >= {threshold}) |\n")
        rf.write(f"| **True Negatives (TN)** | {TN} | Non-IT resumes correctly rejected (Score < {threshold}) |\n")
        rf.write(f"| **False Negatives (FN)** | {FN} | IT resumes incorrectly rejected (Score < {threshold}) |\n")
        rf.write(f"| **Precision** | **{precision:.1f}%** | Of those shortlisted, how many are actually IT developers |\n")
        rf.write(f"| **Recall** | **{recall:.1f}%** | Of all actual IT resumes, how many did the system shortlist |\n")
        rf.write(f"| **F1 Score** | **{f1:.1f}%** | Harmonic mean of Precision and Recall |\n")
        rf.write(f"| **Top 10 Precision** | **{precision_10:.1f}%** | Precision restricted to the highest 10 scores |\n")
        rf.write(f"| **Top 20 Precision** | **{precision_20:.1f}%** | Precision restricted to the highest 20 scores |\n")
        rf.write(f"| **Mean ATS Score (Relevant)** | **{mean_relevant:.1f}** | Average score of actual IT candidates |\n")
        rf.write(f"| **Mean ATS Score (Non-Relevant)** | **{mean_non_relevant:.1f}** | Average score of non-IT candidates |\n\n")
        
        rf.write(f"## 2. Detailed Shortlist breakdown (Score >= {threshold})\n")
        rf.write("| Candidate Email | Category | ATS Score | Recommendation | Relevance Status |\n")
        rf.write("| :--- | :--- | :--- | :--- | :--- |\n")
        top_selected = [r for r in sorted_results if r["score"] >= threshold]
        for r in top_selected:
            status = "✅ Actually Relevant (True Positive)" if r["is_relevant_ground_truth"] else "❌ Not Relevant (False Positive)"
            rf.write(f"| {r['email']} | {r['category']} | {r['score']} | {r['recommendation']} | {status} |\n")
            
        rf.write("\n## 3. Shortlisted Candidate Profile Details\n")
        rf.write("This section showcases the structured AI analysis for each candidate selected by the ATS:\n\n")
        for r in top_selected:
            rf.write(f"### 🧑‍💼 Candidate: {r['email']}\n")
            rf.write(f"- **Match Score:** `{r['score']}%` (Recommendation: `{r['recommendation']}`)\n")
            status_tag = "Actually Relevant (IT Specialist)" if r["is_relevant_ground_truth"] else "Not Relevant (Non-IT Specialist)"
            rf.write(f"- **Relevance Status:** `{status_tag}`\n")
            rf.write(f"- **Experience Match:** {r['experience_match']}\n")
            rf.write(f"- **Education Match:** {r['education_match']}\n")
            rf.write(f"- **Matching Skills:** {r['matching_skills']}\n")
            rf.write(f"- **Missing Skills:** {r['missing_skills']}\n")
            rf.write(f"- **AI Summary:** {r['ai_summary']}\n")
            rf.write("\n---\n\n")
            
        rf.write(f"\n## 4. Rejected/Filtered breakdown (Score < {threshold})\n")
        rf.write("| Candidate Email | Category | ATS Score | Relevance Status |\n")
        rf.write("| :--- | :--- | :--- | :--- |\n")
        rejected = [r for r in sorted_results if r["score"] < threshold]
        for r in rejected:
            status = "⚠️ Missed IT Resume (False Negative)" if r["is_relevant_ground_truth"] else "✅ Correctly Filtered (True Negative)"
            rf.write(f"| {r['email']} | {r['category']} | {r['score']} | {status} |\n")

    print("\n" + "=" * 70)
    print("                     ACCURACY BENCHMARK COMPLETED")
    print("=" * 70)
    print(f"Total Screened:          {len(test_batch)}")
    print(f"Precision:               {precision:.1f}%")
    print(f"Recall:                  {recall:.1f}%")
    print(f"F1 Score:                {f1:.1f}%")
    print(f"Top 10 Precision:        {precision_10:.1f}%")
    print(f"Top 20 Precision:        {precision_20:.1f}%")
    print(f"Mean Score (Relevant):   {mean_relevant:.1f}")
    print(f"Mean Score (Non-Rel):    {mean_non_relevant:.1f}")
    print(f"Report Generated at:     {report_path}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Accuracy benchmark test.")
    parser.add_argument("--csv", type=str, required=True, help="Path to CSV dataset")
    parser.add_argument("--model", type=str, default="grok-4-20-non-reasoning", help="Base model")
    parser.add_argument("--limit", type=int, default=30, help="Total number of resumes (must be even)")
    parser.add_argument("--threshold", type=int, default=70, help="Score threshold for shortlisting")
    args = parser.parse_args()
    
    run_accuracy_test(args.csv, args.model, args.limit, args.threshold)
