"""
CV Ranking System - GDPR Compliant Approach
============================================

This Gradio interface collects:
1. Job Description (uploaded by recruiter)
2. CV (uploaded by recruiter)
3. Candidate Name, Email, Phone (entered by recruiter)
4. Social Media Links (MANUALLY ENTERED - Only if provided by candidate)

All data flows to the ranking API for SHAP analysis and Flowise for social evaluation.
No automatic web scraping - fully compliant with GDPR/PDPA.
"""

import gradio as gr
import requests
import os
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, Any

# Add parent directory to path so we can import api module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import utilities
from db_manager import save_search_result, get_search_history, clear_all_search_history, format_search_history_display
from file_handler import validate_file_upload, extract_text_from_file, format_file_info
from api.services.flowise_handler import FloweiseCandidateQuery

# API Configuration
API_URL = os.environ.get("RANKER_API", "http://127.0.0.1:8000/rank/enhanced")
FLOWISE_API_URL = os.environ.get("FLOWISE_API_URL", "https://flowiseai-railway-production-cbbd.up.railway.app/api/v1/prediction/11949f30-0d9b-4cdb-ac8d-bb3fd3a55d60")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 10))

# ============================================================================
# API Functions
# ============================================================================

def process_file_upload(file_obj) -> Tuple[str, str]:
    """
    Process uploaded file and extract text
    
    Args:
        file_obj: Gradio file object with path, name, size
    
    Returns:
        Tuple of (extracted_text, file_info)
    """
    try:
        if file_obj is None:
            return "", "No file uploaded"
        
        # Read file
        with open(file_obj, "rb") as f:
            file_content = f.read()
        
        filename = Path(file_obj).name
        
        # Validate
        is_valid, message = validate_file_upload(file_content, filename)
        if not is_valid:
            return "", f"❌ {message}"
        
        # Extract text
        text = extract_text_from_file(file_content, filename)
        file_info = format_file_info(filename, len(file_content))
        
        return text, f"✅ {file_info} - Extracted successfully"
    
    except Exception as e:
        return "", f"❌ Error: {str(e)}"


def build_flowise_question_from_fields(
    candidate_name: str,
    email: str,
    phone: str,
    github_url: str,
    linkedin_url: str,
    portfolio_url: str,
    facebook_url: str,
    other_social: str,
    cv_summary: str = ""
) -> str:
    """
    Build a properly formatted question for Flowise with all available fields
    
    Only includes fields that are provided (handles partial inputs)
    """
    
    query = FloweiseCandidateQuery.build_query(
        candidate_name=candidate_name,
        email=email,
        phone=phone,
        github=github_url,
        linkedin=linkedin_url,
        portfolio=portfolio_url,
        facebook=facebook_url,
        other_social=other_social,
        cv_summary=cv_summary[:200] if cv_summary else None
    )
    
    return query


def evaluate_with_flowise_via_be(question: str) -> Dict[str, Any]:
    """
    Send candidate info to BE for Flowise evaluation
    
    FE communicates with BE, not directly with Flowise
    BE handles all external API communication
    """
    try:
        # Call BE endpoint for Flowise evaluation
        # This ensures all external communication goes through BE
        flowise_endpoint = API_URL.replace("/rank/enhanced", "/flowise/evaluate-social")
        
        payload = {"question": question}
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(flowise_endpoint, json=payload, headers=headers, timeout=300)  # 300 seconds (5 minutes) for Flowise scraping
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get("success"):
                return result.get("evaluation", {})
            else:
                return {
                    "error": result.get("error", "Unknown error"),
                    "profiles_found": [],
                    "profiles_verified": [],
                    "social_presence_score": 0.0,
                    "risk_flags": []
                }
        else:
            return {
                "error": f"BE returned {response.status_code}: {response.text}",
                "profiles_found": [],
                "profiles_verified": [],
                "social_presence_score": 0.0,
                "risk_flags": []
            }
    
    except Exception as e:
        return {
            "error": str(e),
            "profiles_found": [],
            "profiles_verified": [],
            "social_presence_score": 0.0,
            "risk_flags": []
        }


def rank_cv_with_social_and_flowise(
    jd_title: str,
    jd_description: str,
    cv_text: str,
    candidate_name: str,
    email: str = "",
    phone: str = "",
    github_url: str = "",
    linkedin_url: str = "",
    portfolio_url: str = "",
    facebook_url: str = "",
    other_social: str = "",
    evaluate_social: bool = True
):
    """
    Rank CV with social media evaluation via Flowise
    
    Handles partial inputs - only includes fields that are provided
    Evaluates social profiles through Flowise for verification
    Saves results to search history
    """
    
    try:
        # Validate inputs
        if not candidate_name.strip():
            return (None, "❌ Candidate name is required", "", "", "", "")
        
        if not cv_text.strip():
            return (None, "❌ CV content is required", "", "", "", "")
        
        if not jd_description.strip():
            return (None, "❌ Job description is required", "", "", "", "")
        
        # Build social profiles dict - only include provided values
        social_profiles = {
            "email": email.strip() if email.strip() else None,
            "phone": phone.strip() if phone.strip() else None,
            "github": github_url.strip() if github_url.strip() else None,
            "linkedin": linkedin_url.strip() if linkedin_url.strip() else None,
            "portfolio": portfolio_url.strip() if portfolio_url.strip() else None,
            "facebook": facebook_url.strip() if facebook_url.strip() else None,
        }
        
        # Remove None entries
        social_profiles = {k: v for k, v in social_profiles.items() if v}
        
        # Add other social if provided
        if other_social.strip():
            social_profiles["other"] = other_social.strip()
        
        # =====================================================================
        # STEP 1: Call ranking API
        # =====================================================================
        payload = {
            "jd_title": jd_title or "Job Position",
            "jd_description": jd_description,
            "candidate_id": candidate_name.replace(" ", "_").lower(),
            "candidate_name": candidate_name,
            "cv_text": cv_text,
            "social_media_profiles": social_profiles,
            "include_shap": True
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}: {response.text}"
            return (
                None,
                f"❌ Ranking failed: {error_msg}",
                f"Failed to rank CV. Please check the API is running at {API_URL}",
                json.dumps(social_profiles, indent=2),
                "",
                ""
            )
        
        result = response.json()
        
        # Extract ranking results
        match_score = result.get("match_score", 0)
        recommendation = result.get("recommendation", "No recommendation")
        skill_alignment = result.get("skill_alignment", {})
        
        # Format explanation
        shap_analysis = result.get("shap_analysis", {})
        top_features = shap_analysis.get("top_features", [])
        explanation = shap_analysis.get("explanation", "No explanation available")
        
        # Format top features
        if top_features:
            features_str = "\n**Top Features Contributing to Score:**\n" + "\n".join([
                f"  • {feat[0]}: {feat[1]:.4f}" if isinstance(feat, list) else f"  • {feat}"
                for feat in top_features[:5]
            ])
            explanation = f"{explanation}\n{features_str}"
        
        # Add skill alignment info
        if skill_alignment:
            skills_str = "\n**Skill Alignment:**\n"
            if skill_alignment.get("present"):
                skills_str += f"  ✅ Present: {', '.join(skill_alignment['present'][:5])}\n"
            if skill_alignment.get("missing"):
                skills_str += f"  ❌ Missing: {', '.join(skill_alignment['missing'][:5])}"
            explanation = f"{explanation}\n{skills_str}"
        
        # =====================================================================
        # STEP 2: Evaluate social profiles with Flowise (if enabled)
        # =====================================================================
        flowise_evaluation = ""
        social_presence_score = 0.0
        
        if evaluate_social and social_profiles:
            # Build question for Flowise
            cv_summary = cv_text[:300] if cv_text else ""
            flowise_question = build_flowise_question_from_fields(
                candidate_name=candidate_name,
                email=email,
                phone=phone,
                github_url=github_url,
                linkedin_url=linkedin_url,
                portfolio_url=portfolio_url,
                facebook_url=facebook_url,
                other_social=other_social,
                cv_summary=cv_summary
            )
            
            # Call BE for Flowise evaluation (not directly)
            flowise_result = evaluate_with_flowise_via_be(flowise_question)
            
            if "error" not in flowise_result:
                # Format Flowise response
                profiles_verified = flowise_result.get("profiles_verified", [])
                profiles_found = flowise_result.get("profiles_found", [])
                social_presence_score = flowise_result.get("social_presence_score", 0.0)
                risk_flags = flowise_result.get("risk_flags", [])
                
                flowise_evaluation = "**🔗 Social Media Evaluation (via Flowise):**\n"
                
                if profiles_found:
                    flowise_evaluation += f"  📌 Profiles Found: {', '.join(profiles_found)}\n"
                
                if profiles_verified:
                    flowise_evaluation += f"  ✅ Verified: {', '.join(profiles_verified)}\n"
                
                flowise_evaluation += f"  📊 Social Presence Score: {social_presence_score:.1%}\n"
                
                if risk_flags:
                    flowise_evaluation += f"  ⚠️ Flags: {', '.join(risk_flags)}\n"
                
                explanation = f"{explanation}\n\n{flowise_evaluation}"
            else:
                flowise_evaluation = f"⚠️ Flowise evaluation skipped: {flowise_result.get('error', 'Unknown error')}"
        
        # =====================================================================
        # STEP 3: Save to search history
        # =====================================================================
        try:
            save_search_result(
                candidate_name=candidate_name,
                job_title=jd_title,
                match_score=match_score,
                recommendation=recommendation,
                social_profiles=social_profiles,
                flowise_response={"presence_score": social_presence_score},
                notes=f"Ranked at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        except Exception as e:
            print(f"Warning: Could not save to history: {e}")
        
        # Format social display
        social_display = json.dumps(social_profiles, indent=2) if social_profiles else "No social profiles provided"
        
        # Get search history
        history_display = format_search_history_display()
        
        return (
            match_score,
            recommendation,
            explanation,
            social_display,
            flowise_evaluation,
            history_display
        )
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        return (
            None,
            f"❌ Error occurred",
            f"An error occurred while ranking the CV:\n{error_msg}",
            error_msg,
            "",
            ""
        )


def clear_search_history_action():
    """Clear all search history from database"""
    clear_all_search_history()
    return "", format_search_history_display()


# ============================================================================
# Sample Job Descriptions
# ============================================================================

SAMPLE_JDS = {
    "Sample 1: Senior Python Engineer": {
        "title": "Senior Python Engineer",
        "description": """Senior Python Engineer - Full Stack Development

We are looking for an experienced Senior Python Engineer with 5+ years of professional development experience.

**Key Responsibilities:**
- Design and develop scalable Python applications
- Lead code reviews and mentor junior developers
- Architect backend systems using modern frameworks
- Collaborate with product and design teams
- Optimize application performance and security

**Required Skills:**
- 5+ years of Python development experience
- Strong knowledge of Django/FastAPI or equivalent frameworks
- Experience with relational databases (PostgreSQL, MySQL)
- Knowledge of REST API design and development
- Git version control proficiency
- Understanding of SOLID principles and design patterns

**Preferred Qualifications:**
- Experience with Docker and Kubernetes
- Knowledge of AWS or similar cloud platforms
- Experience with machine learning libraries (NumPy, Pandas, Scikit-learn)
- Contribution to open source projects
- Agile/Scrum experience

**What We Offer:**
- Competitive salary: LKR 150,000 - 200,000/month
- Flexible work arrangement (Remote/Office)
- Health insurance and retirement benefits
- Professional development budget
- Collaborative team environment

**Location:** Colombo, Sri Lanka (Remote options available)
**Contact:** +94 77 123 4567"""
    },
    
    "Sample 2: Full Stack JavaScript Developer": {
        "title": "Full Stack JavaScript Developer",
        "description": """Full Stack JavaScript Developer - E-commerce Platform

Join our growing tech team based in Colombo to build scalable web applications!

**Position Overview:**
We're seeking a Full Stack JavaScript Developer to join our product engineering team. You'll work on both frontend and backend systems serving customers across South Asia.

**Your Responsibilities:**
- Develop responsive web applications using React.js
- Build robust Node.js/Express backend services
- Design and optimize database schemas (MongoDB/PostgreSQL)
- Implement RESTful and GraphQL APIs
- Collaborate with product managers and designers
- Participate in code reviews and technical discussions
- Ensure code quality through testing and documentation

**Required Qualifications:**
- 3+ years of JavaScript/TypeScript experience
- Proficiency in React.js or Vue.js
- Strong Node.js/Express knowledge
- Experience with relational and NoSQL databases
- Understanding of RESTful API principles
- Excellent problem-solving skills
- Bachelor's degree in Computer Science or equivalent experience

**Nice to Have:**
- GraphQL experience
- Docker/containerization knowledge
- Experience with CI/CD pipelines
- AWS or GCP familiarity
- Experience with state management (Redux, Context API)
- Performance optimization expertise

**Compensation & Benefits:**
- Salary: LKR 120,000 - 160,000/month
- Health, dental, and wellness benefits
- Flexible remote/office arrangement
- Professional development opportunities
- Collaborative team culture

**Location:** Colombo, Sri Lanka
**Phone Format:** +94 70 123 4567 or 0701 234 567"""
    },
    
    "Sample 3: Data Scientist - Machine Learning": {
        "title": "Data Scientist - Machine Learning",
        "description": """Data Scientist - Machine Learning | FinTech Solutions

**About the Role:**
We're a Colombo-based FinTech startup seeking a Data Scientist to develop ML models for financial analytics and fraud detection. You'll work on challenging problems with real-world impact.

**Key Responsibilities:**
- Develop and deploy machine learning models for financial applications
- Perform exploratory data analysis and feature engineering
- Build data pipelines and ETL processes
- Collaborate with product and engineering teams
- Document models and create technical specifications
- Monitor model performance in production
- Conduct A/B testing and measure model impact

**Required Skills:**
- 3+ years of experience in data science or analytics
- Strong programming: Python (NumPy, Pandas, Scikit-learn)
- Experience with machine learning algorithms and techniques
- SQL proficiency for database queries
- Understanding of statistical analysis and hypothesis testing
- Git and version control
- Experience with Jupyter notebooks

**Preferred Experience:**
- Deep learning frameworks (TensorFlow, PyTorch)
- Big data tools (Spark, Hadoop)
- Cloud platforms (AWS, GCP, Azure)
- Financial/FinTech domain knowledge
- MLOps and model deployment
- Time series analysis

**What We Provide:**
- Competitive salary: LKR 130,000 - 180,000/month
- Flexible work arrangements (Office/Remote)
- Health and wellness benefits
- Learning budget for courses and conferences
- Collaborative research environment
- Impact on growing FinTech ecosystem

**Location:** Colombo, Sri Lanka (Remote available)
**Contact:** +94 76 555 4321"""
    },
    
    "Sample 4: DevOps Engineer - Cloud Infrastructure": {
        "title": "DevOps Engineer - Cloud Infrastructure",
        "description": """DevOps Engineer - Cloud Infrastructure & Automation

**About Us:**
Leading SaaS platform in South Asia serving 5,000+ customers. We're scaling our infrastructure from our Colombo headquarters and need experienced DevOps engineers.

**Your Role:**
- Design and maintain cloud infrastructure on AWS/GCP
- Implement CI/CD pipelines and automation
- Manage containerization and orchestration (Docker, Kubernetes)
- Monitor system performance and resolve infrastructure issues
- Implement security best practices and compliance
- Collaborate with development teams on deployment strategies
- Optimize cloud costs and resource utilization

**Required Qualifications:**
- 4+ years of DevOps/Infrastructure engineering experience
- Strong knowledge of AWS or GCP (or both)
- Hands-on experience with Docker and Kubernetes
- Infrastructure as Code (Terraform, CloudFormation, or Ansible)
- Linux/Unix system administration
- Scripting skills (Python, Bash, or Go)
- CI/CD tools (Jenkins, GitLab CI, GitHub Actions)
- Understanding of networking and security

**Preferred Skills:**
- Kubernetes cluster management
- Prometheus/Grafana monitoring
- Helm charts and package management
- Database administration (PostgreSQL, MySQL)
- Incident response and on-call experience
- Cost optimization expertise
- Enterprise security compliance (ISO 27001, SOC 2)

**Benefits:**
- Salary: LKR 140,000 - 190,000/month
- Remote-first culture with office in Colombo
- Comprehensive benefits package
- Professional development funds
- Collaborative team culture
- On-call rotation support with incentives

**Location:** Colombo, Sri Lanka (Remote-first)
**Contact:** +94 71 777 8888"""
    },
    
    "Sample 5: Product Manager - AI/ML Products": {
        "title": "Product Manager - AI/ML Products",
        "description": """Product Manager - AI/ML Products

**Company:** Leading AI/ML SaaS startup in Sri Lanka (Seed/Series A funded)

**About the Role:**
We're seeking a Product Manager to lead the development of our AI-powered features. You'll work at the intersection of product strategy, technology, and user needs from our Colombo office.

**Key Responsibilities:**
- Define product vision and strategy for AI/ML features
- Collaborate with engineering and design teams in Colombo
- Conduct user research and gather product requirements
- Create product roadmaps and prioritize features
- Analyze metrics and drive data-informed decisions
- Manage product launches and go-to-market strategy
- Communicate product updates to stakeholders and customers

**Required Experience:**
- 3+ years of product management experience
- Experience launching 2+ products or major features
- Understanding of AI/ML concepts and capabilities
- Strong analytical and problem-solving skills
- Excellent communication and presentation abilities
- Experience with metrics and analytics tools
- Ability to work cross-functionally

**Preferred Qualifications:**
- Background in AI/ML products or data science
- Experience with B2B SaaS products
- Knowledge of prompt engineering and LLMs
- Experience with technical product management
- MBA or technical background
- Startup environment experience
- Customer development expertise

**What We Offer:**
- Salary: LKR 130,000 - 170,000/month + equity
- Health, dental, and wellness benefits
- Flexible office/remote arrangement
- Professional development budget
- Collaborative, innovative team
- Direct impact on product direction
- Board-level visibility

**Location:** Colombo, Sri Lanka
**Working Style:** Hybrid (Office in Colombo, Remote days available)
**Contact:** +94 77 989 5555"""
    }
}


def validate_form_inputs(jd_description: str, cv_text: str, candidate_name: str) -> Tuple[bool, str]:
    """
    Validate minimum required inputs
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    errors = []
    
    if not candidate_name or not candidate_name.strip():
        errors.append("Candidate Name is required")
    
    if not jd_description or not jd_description.strip():
        errors.append("Job Description is required")
    
    if not cv_text or not cv_text.strip():
        errors.append("CV/Resume is required")
    
    # Check minimum length
    if jd_description and len(jd_description.strip()) < 50:
        errors.append("Job Description is too short (minimum 50 characters)")
    
    if cv_text and len(cv_text.strip()) < 100:
        errors.append("CV/Resume is too short (minimum 100 characters)")
    
    if errors:
        return False, "❌ Missing required fields:\n• " + "\n• ".join(errors)
    
    return True, "✅ Form is valid"


def check_form_validity(jd_description: str, cv_text: str, candidate_name: str) -> bool:
    """
    Check if form has minimum valid inputs (for button enable/disable)
    """
    is_valid, _ = validate_form_inputs(jd_description, cv_text, candidate_name)
    return is_valid


def load_sample_jd(sample_name: str) -> Tuple[str, str]:
    """
    Load a sample job description
    
    Returns:
        Tuple of (jd_title, jd_description)
    """
    if sample_name in SAMPLE_JDS:
        sample = SAMPLE_JDS[sample_name]
        return sample["title"], sample["description"]
    return "", ""


# ============================================================================
# Gradio Interface
# ============================================================================

with gr.Blocks(title="CV Ranking System - GDPR Compliant") as demo:
    
    # Header with better spacing
    gr.Markdown("""
    # 🎯 CV Ranking System with SHAP Analysis & Social Evaluation
    
    **GDPR/PDPA Compliant Process**
    
    1. Upload Job Description & CV (PDF, DOCX, TXT - max 10MB)
    2. Enter candidate information & **social media links IF provided**
    3. Get ML-based ranking with SHAP explanations
    4. Get Flowise-powered social media verification
    5. View search history (last 5 searches)
    
    ⚠️ *Important: Only enter social links that the candidate explicitly provided*
    """)
    
    # ========================================================================
    # Section 1: File Uploads
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 📁 Upload Files")
        gr.Markdown("*Supported formats: PDF, DOCX, TXT (max 10MB)*")
        
        with gr.Row():
            with gr.Column(scale=1):
                jd_file = gr.File(
                    label="Job Description (Optional - or paste below)",
                    file_types=[".pdf", ".docx", ".txt"],
                    type="filepath"
                )
            with gr.Column(scale=1):
                jd_file_status = gr.Textbox(
                    label="Status",
                    interactive=False,
                    value="Ready"
                )
        
        with gr.Row():
            with gr.Column(scale=1):
                cv_file = gr.File(
                    label="CV/Resume (Optional - or paste below)",
                    file_types=[".pdf", ".docx", ".txt"],
                    type="filepath"
                )
            with gr.Column(scale=1):
                cv_file_status = gr.Textbox(
                    label="Status",
                    interactive=False,
                    value="Ready"
                )
    
    # ========================================================================
    # Section 2: Job and Candidate Information
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 📋 Job and Candidate Information")
        
        with gr.Row():
            with gr.Column(scale=1):
                jd_title = gr.Textbox(
                    label="Job Title",
                    placeholder="e.g., Senior Python Engineer",
                    value="Senior Software Engineer"
                )
            with gr.Column(scale=1):
                candidate_name = gr.Textbox(
                    label="Candidate Name *",
                    placeholder="e.g., John Smith",
                    info="Required"
                )
        
        # Load sample JDs dropdown
        gr.Markdown("**📚 Or load a sample JD for testing:**")
        with gr.Row():
            with gr.Column(scale=4):
                sample_jd_selector = gr.Dropdown(
                    choices=[""] + list(SAMPLE_JDS.keys()),
                    value="",
                    label="Sample Job Descriptions",
                    info="Select a sample to auto-fill JD title and description"
                )
            with gr.Column(scale=1):
                load_sample_button = gr.Button(
                    "📥 Load Sample",
                    size="sm"
                )
        
        jd_description = gr.Textbox(
            label="Job Description *",
            placeholder="Paste full JD here...",
            lines=6,
            info="Required - will be populated from file if uploaded or sample selected"
        )
        
        cv_text = gr.Textbox(
            label="CV/Resume Content *",
            placeholder="Paste CV content here...",
            lines=6,
            info="Required - will be populated from file if uploaded"
        )
        
        # Validation status display
        validation_status = gr.Textbox(
            label="Validation Status",
            interactive=False,
            value="✅ All required fields must be filled",
            lines=3,
            max_lines=5
        )
    
    # ========================================================================
    # Section 3: Contact Information
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 📞 Contact Information (Optional)")
        
        with gr.Row():
            with gr.Column(scale=1):
                email = gr.Textbox(
                    label="Email Address",
                    placeholder="candidate@email.com",
                    info="If provided by candidate"
                )
            with gr.Column(scale=1):
                phone = gr.Textbox(
                    label="Phone Number",
                    placeholder="+94 77 123 4567 or 0771 234 567",
                    info="Sri Lanka format - if provided by candidate"
                )
    
    # ========================================================================
    # Section 4: Social Media (MANUAL INPUT - GDPR Compliant)
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("""
        ### 🔗 Social Media Links (Optional)
        
        **⚠️ IMPORTANT: Only enter links that the candidate explicitly provided**
        
        These can be from:
        - Candidate's CV
        - Candidate's email
        - Candidate's LinkedIn message
        - Any communication where candidate shared them
        
        Leave blank if candidate did NOT provide.
        """)
        
        with gr.Row():
            with gr.Column(scale=1):
                github_url = gr.Textbox(
                    label="GitHub",
                    placeholder="https://github.com/username",
                    info="If candidate provided"
                )
            with gr.Column(scale=1):
                linkedin_url = gr.Textbox(
                    label="LinkedIn",
                    placeholder="https://linkedin.com/in/username",
                    info="If candidate provided"
                )
        
        with gr.Row():
            with gr.Column(scale=1):
                portfolio_url = gr.Textbox(
                    label="Portfolio/Website",
                    placeholder="https://myportfolio.com",
                    info="If candidate provided"
                )
            with gr.Column(scale=1):
                facebook_url = gr.Textbox(
                    label="Facebook",
                    placeholder="https://facebook.com/username",
                    info="If candidate provided"
                )
        
        other_social = gr.Textbox(
            label="Other Social Media/Notes",
            placeholder="e.g., Twitter: @username, Medium: blog.medium.com/@user",
            info="Any other links or notes provided by candidate"
        )
        
        evaluate_social = gr.Checkbox(
            label="✅ Evaluate Social Profiles with Flowise",
            value=True,
            info="Flowise will verify and analyze social profiles"
        )
    
    # ========================================================================
    # Section 5: Process Controls
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 🚀 Process & Controls")
        
        with gr.Row():
            with gr.Column(scale=1):
                pass
            with gr.Column(scale=2):
                rank_button = gr.Button(
                    "🚀 Rank CV & Analyze",
                    size="lg",
                    variant="primary",
                    interactive=False  # Start disabled until form is valid
                )
            with gr.Column(scale=1):
                clear_form_button = gr.Button(
                    "🔄 Clear Form",
                    size="lg"
                )
            with gr.Column(scale=1):
                pass
    
    # ========================================================================
    # Section 6: Results - Main Analysis
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 📊 Ranking Results")
        
        with gr.Row():
            match_score = gr.Number(
                label="Match Score",
                precision=3,
                info="Score from 0 to 1 (higher is better)"
            )
        
        recommendation = gr.Textbox(
            label="Recommendation",
            lines=2,
            interactive=False,
            info="Recommendation based on match score"
        )
        
        explanation = gr.Textbox(
            label="SHAP Analysis & Skill Alignment",
            lines=12,
            interactive=False,
            info="Machine learning explanation and top contributing features"
        )
        
        social_display = gr.Textbox(
            label="Provided Social Profiles (Reference)",
            lines=4,
            interactive=False,
            info="Summary of entered social media links"
        )
    
    # ========================================================================
    # Section 7: Flowise Social Evaluation Results
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 🔗 Flowise Social Media Evaluation")
        
        flowise_evaluation = gr.Textbox(
            label="Social Profile Verification Results",
            lines=6,
            interactive=False,
            info="Flowise evaluation of candidate's social profiles"
        )
    
    # ========================================================================
    # Section 8: Search History
    # ========================================================================
    
    with gr.Group():
        gr.Markdown("### 📜 Search History (Last 5 Searches)")
        
        history_display = gr.Markdown(
            value="No search history yet"
        )
        
        clear_history_button = gr.Button(
            "🗑️ Clear All History",
            size="sm",
            variant="secondary"
        )
    
    # ========================================================================
    # Button Click Handlers
    # ========================================================================
    
    def process_jd_file(file_obj):
        """Handle JD file upload"""
        text, status = process_file_upload(file_obj)
        return text, status
    
    def process_cv_file(file_obj):
        """Handle CV file upload"""
        text, status = process_file_upload(file_obj)
        return text, status
    
    def validate_on_change(jd_desc: str, cv: str, cand_name: str):
        """Validate form and update button state"""
        is_valid, msg = validate_form_inputs(jd_desc, cv, cand_name)
        # Return message for validation status display and button state
        return msg, gr.update(interactive=is_valid)
    
    def load_sample(sample_name: str):
        """Load sample JD"""
        if sample_name:
            title, desc = load_sample_jd(sample_name)
            return title, desc
        return "", ""
    
    def clear_form():
        """Clear all form fields and reset button"""
        return (
            "",  # jd_title
            "",  # jd_description
            "",  # cv_text
            "",  # candidate_name
            "",  # email
            "",  # phone
            "",  # github_url
            "",  # linkedin_url
            "",  # portfolio_url
            "",  # facebook_url
            "",  # other_social
            "",  # flowise_evaluation
            False,  # evaluate_social
            "",  # sample_jd_selector
            "✅ All required fields must be filled",  # validation_status
            gr.update(interactive=False)  # rank_button disabled
        )
    
    def clear_history():
        """Clear search history and update display"""
        clear_search_history_action()
        return format_search_history_display()
    
    # File upload handlers
    jd_file.change(
        fn=process_jd_file,
        inputs=[jd_file],
        outputs=[jd_description, jd_file_status]
    )
    
    cv_file.change(
        fn=process_cv_file,
        inputs=[cv_file],
        outputs=[cv_text, cv_file_status]
    )
    
    # Load sample JD handler
    load_sample_button.click(
        fn=load_sample,
        inputs=[sample_jd_selector],
        outputs=[jd_title, jd_description]
    )
    
    # Validation handlers - trigger on any change to required fields
    jd_description.change(
        fn=validate_on_change,
        inputs=[jd_description, cv_text, candidate_name],
        outputs=[validation_status, rank_button]
    )
    
    cv_text.change(
        fn=validate_on_change,
        inputs=[jd_description, cv_text, candidate_name],
        outputs=[validation_status, rank_button]
    )
    
    candidate_name.change(
        fn=validate_on_change,
        inputs=[jd_description, cv_text, candidate_name],
        outputs=[validation_status, rank_button]
    )
    
    # Main ranking handler
    rank_button.click(
        fn=rank_cv_with_social_and_flowise,
        inputs=[
            jd_title,
            jd_description,
            cv_text,
            candidate_name,
            email,
            phone,
            github_url,
            linkedin_url,
            portfolio_url,
            facebook_url,
            other_social,
            evaluate_social
        ],
        outputs=[
            match_score,
            recommendation,
            explanation,
            social_display,
            flowise_evaluation,
            history_display
        ]
    )
    
    # Clear form handler
    clear_form_button.click(
        fn=clear_form,
        outputs=[
            jd_title,
            jd_description,
            cv_text,
            candidate_name,
            email,
            phone,
            github_url,
            linkedin_url,
            portfolio_url,
            facebook_url,
            other_social,
            flowise_evaluation,
            evaluate_social,
            sample_jd_selector,
            validation_status,
            rank_button
        ]
    )
    
    # Clear history handler
    clear_history_button.click(
        fn=clear_history,
        outputs=[history_display]
    )
    
    # ========================================================================
    # Footer
    # ========================================================================
    
    gr.Markdown("""
    ---
    
    ### 📝 How to Use (GDPR-Compliant Process)
    
    1. **Get candidate's CV**: Recruiter receives CV from candidate
    2. **Get social links**: Ask candidate explicitly to provide any social media links they're comfortable sharing
    3. **Enter in form**: Paste CV, enter links only if provided
    4. **Rank**: Click the ranking button
    5. **Review results**: See match score and SHAP explanation
    
    ### ✅ What Makes This GDPR-Compliant
    
    - ✅ No automatic web scraping
    - ✅ Only data candidate explicitly provided
    - ✅ Transparent process
    - ✅ Clear purpose: CV ranking only
    - ✅ Candidate in control of data
    
    ### ⚠️ Important Notes
    
    - Only enter social links if candidate provided them
    - Don't search the web for candidates' profiles automatically
    - Use Flowise search only as a helper tool - recruiter reviews results
    - Store results securely
    - Delete when no longer needed
    """)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
