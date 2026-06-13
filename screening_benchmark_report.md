# Resume Screening Platform Load-Test Report

## 1. Executive Summary
This benchmark measures the speed, parsing accuracy, and API cost of the screening pipeline under load. The simulation processed a batch of resumes using the platform's exact production configurations.

### Core Metrics Table
| Metric | Value | Details / Observations |
| :--- | :--- | :--- |
| **Total Resumes Processed** | 100 | From loaded dataset |
| **Successful Screenings** | 100 | Clean 20-dimension JSON extractions |
| **Failed/Timed out** | 0 | API errors or parser failures |
| **Success Rate** | 100.0% | Pipeline robustness indicator |
| **Total Wall-Clock Time** | 138.89 seconds | Actual time user waited for completion |
| **Avg. Time Per Resume** | 36.09 seconds | Round-trip latency for single item |
| **System Throughput** | 43.2 resumes/min | Scalability capacity benchmark |
| **Total Input Tokens** | 320,918 | Context and prompts sent |
| **Total Output Tokens** | 299,919 | Structured analysis objects received |
| **Total API Cost (Est.)** | $3.1042 USD | Based on active model rates |

## 2. API Costs & Scaling Projections
Based on the token usage measured in this run, here is how the API costs scale for different resume volume goals:

| Volume | Estimated Cost (Gemini Flash) | Estimated Duration (Paid Tier) |
| :--- | :--- | :--- |
| **50 Resumes** | $1.5521 USD | ~30 seconds |
| **500 Resumes** | $15.5209 USD | ~3 to 4 minutes |
| **5,000 Resumes** | $155.2093 USD | ~30 to 40 minutes |

## 3. Detailed Results Breakdown
| Application Email | Category | Processing Time | Status | Score |
| :--- | :--- | :--- | :--- | :--- |
| applicant_25@example.com | HR | 29.40s | ✅ SUCCESS | 88 |
| applicant_14@example.com | HR | 29.41s | ✅ SUCCESS | 88 |
| applicant_24@example.com | HR | 29.53s | ✅ SUCCESS | 88 |
| applicant_18@example.com | HR | 29.54s | ✅ SUCCESS | 88 |
| applicant_23@example.com | HR | 30.03s | ✅ SUCCESS | 88 |
| applicant_16@example.com | HR | 30.09s | ✅ SUCCESS | 88 |
| applicant_5@example.com | HR | 30.20s | ✅ SUCCESS | 88 |
| applicant_9@example.com | HR | 30.30s | ✅ SUCCESS | 82 |
| applicant_8@example.com | HR | 30.31s | ✅ SUCCESS | 88 |
| applicant_0@example.com | HR | 30.40s | ✅ SUCCESS | 82 |
| applicant_15@example.com | HR | 30.40s | ✅ SUCCESS | 52 |
| applicant_1@example.com | HR | 30.51s | ✅ SUCCESS | 88 |
| applicant_7@example.com | HR | 30.54s | ✅ SUCCESS | 78 |
| applicant_12@example.com | HR | 30.67s | ✅ SUCCESS | 82 |
| applicant_28@example.com | HR | 30.78s | ✅ SUCCESS | 82 |
| applicant_10@example.com | HR | 30.81s | ✅ SUCCESS | 88 |
| applicant_11@example.com | HR | 30.92s | ✅ SUCCESS | 78 |
| applicant_6@example.com | HR | 31.10s | ✅ SUCCESS | 82 |
| applicant_4@example.com | HR | 31.22s | ✅ SUCCESS | 88 |
| applicant_27@example.com | HR | 31.27s | ✅ SUCCESS | 92 |
| applicant_21@example.com | HR | 31.46s | ✅ SUCCESS | 92 |
| applicant_19@example.com | HR | 31.64s | ✅ SUCCESS | 88 |
| applicant_20@example.com | HR | 31.68s | ✅ SUCCESS | 52 |
| applicant_26@example.com | HR | 31.82s | ✅ SUCCESS | 88 |
| applicant_22@example.com | HR | 32.00s | ✅ SUCCESS | 92 |
| applicant_17@example.com | HR | 32.03s | ✅ SUCCESS | 82 |
| applicant_13@example.com | HR | 32.15s | ✅ SUCCESS | 82 |
| applicant_2@example.com | HR | 32.84s | ✅ SUCCESS | 82 |
| applicant_29@example.com | HR | 32.83s | ✅ SUCCESS | 52 |
| applicant_3@example.com | HR | 33.52s | ✅ SUCCESS | 58 |
| applicant_34@example.com | HR | 17.67s | ✅ SUCCESS | 88 |
| applicant_37@example.com | HR | 17.92s | ✅ SUCCESS | 88 |
| applicant_32@example.com | HR | 19.08s | ✅ SUCCESS | 82 |
| applicant_35@example.com | HR | 19.56s | ✅ SUCCESS | 82 |
| applicant_31@example.com | HR | 22.27s | ✅ SUCCESS | 92 |
| applicant_33@example.com | HR | 22.15s | ✅ SUCCESS | 88 |
| applicant_30@example.com | HR | 22.77s | ✅ SUCCESS | 82 |
| applicant_40@example.com | HR | 22.41s | ✅ SUCCESS | 35 |
| applicant_36@example.com | HR | 22.75s | ✅ SUCCESS | 88 |
| applicant_39@example.com | HR | 22.97s | ✅ SUCCESS | 82 |
| applicant_38@example.com | HR | 23.31s | ✅ SUCCESS | 35 |
| applicant_43@example.com | HR | 23.55s | ✅ SUCCESS | 82 |
| applicant_45@example.com | HR | 25.09s | ✅ SUCCESS | 88 |
| applicant_41@example.com | HR | 27.75s | ✅ SUCCESS | 68 |
| applicant_52@example.com | HR | 26.76s | ✅ SUCCESS | 92 |
| applicant_42@example.com | HR | 31.63s | ✅ SUCCESS | 92 |
| applicant_51@example.com | HR | 33.54s | ✅ SUCCESS | 78 |
| applicant_55@example.com | HR | 34.84s | ✅ SUCCESS | 88 |
| applicant_60@example.com | HR | 20.80s | ✅ SUCCESS | 92 |
| applicant_61@example.com | HR | 21.79s | ✅ SUCCESS | 82 |
| ... and 50 more items ... | | | | |
