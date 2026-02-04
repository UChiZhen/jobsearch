# jobsearch

An automated job-search system built to identify high-quality opportunities in the Impact Finance sector with low noise and high signal.

This project is actively used as a real-world job-search assistant.

---

## 🌍 Impact Finance Job Radar

**Impact Finance Job Radar** is a lightweight automation system designed to help mission-driven professionals efficiently discover roles that align with their values and experience.

The system continuously scans job postings, evaluates relevance using LLM-based matching, and delivers only high-confidence opportunities.

### Core Capabilities

- Automated scraping of curated Impact Finance job sources
- Semantic matching between job descriptions and a target candidate profile
- Structured output synced to Google Sheets for tracking and review
- High-signal email alerts for top matches
- Fully traceable and low-cost pipeline

📂 **Core system architecture and implementation details**  
👉 [job-radar/README.md](job-radar/README.md)

---

## Why This Project Exists

Searching for Impact Finance roles is uniquely time-consuming:

- Roles are scattered across niche platforms and organization websites
- Job descriptions vary widely in language and structure
- Manual filtering introduces noise and fatigue

This system reduces cognitive load by automating discovery, evaluation, and prioritization, allowing the candidate to focus on applications and conversations.

---

## System Overview

At a high level, the system operates as follows:

1. Periodically collects new job postings from selected sources
2. Uses an LLM-based evaluator to score relevance against a predefined profile
3. Stores structured results in Google Sheets for transparency and iteration
4. Pushes email alerts when high-confidence matches appear

The design prioritizes clarity, auditability, and ease of modification.

---

## Repository Structure

```text
jobsearch/
├─ job-radar/        # Core job radar system (logic, pipelines, configs)
├─ README.md         # Project entry point and overview
