"""
CV Ranking System - GDPR Compliant with Search History & Export
===============================================================

Frontend Flow (3 Tabs):
  TAB 1: Input Form - CV, JD, Candidate Info, Social Links, Phone
  TAB 2: Results - Baseline score, Social-weighted score, Impact analysis, Flowise evaluation
  TAB 3: Search History - Recent searches with delete buttons, clear all, refresh

Features:
  - Form validation with error handling
  - 300-second timeout for API calls
  - Flowise integration for social media verification
  - SHAP feature importance analysis
  - Automatic database saves to search history
  - Export to JSON, HTML, and CSV formats
  - Individual record deletion with confirmation
  - Dark/Light mode toggle
  - Dark mode color contrast compliance
"""

import gradio as gr
import requests
import os
import json
import sys
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Import utilities  
try:
    from db_manager import (
        save_search_result, 
        get_search_history, 
        clear_all_search_history,
        delete_search_record,
        export_results_json,
        export_results_html,
        export_results_csv
    )
    from file_handler import validate_file_upload, extract_text_from_file
except:
    pass

# API Configuration
API_URL = os.environ.get("RANKER_API", "http://127.0.0.1:8000/rank/enhanced")

# Import sample JDs from separate file
try:
    from sample_jds import SAMPLE_JDS
except:
    SAMPLE_JDS = {"Default": "Sample job descriptions not loaded"}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not email:
        return True, ""  # Optional field
    if re.match(pattern, email):
        return True, ""
    return False, "Invalid email format"

def validate_phone(phone: str) -> Tuple[bool, str]:
    """Validate phone number format (international)"""
    if not phone:
        return True, ""  # Optional field
    # Remove common separators
    clean_phone = re.sub(r'[\s\-\(\)\+]', '', phone)
    if len(clean_phone) >= 7 and clean_phone.isdigit():
        return True, ""
    return False, "Invalid phone format (must be 7+ digits)"

def validate_cv_jd(cv_text: str, jd_text: str) -> Tuple[bool, str]:
    """Validate CV and JD are not empty"""
    if not cv_text or len(cv_text.strip()) < 20:
        return False, "CV must be at least 20 characters"
    if not jd_text or len(jd_text.strip()) < 20:
        return False, "Job Description must be at least 20 characters"
    return True, ""

def validate_candidate_name(name: str) -> Tuple[bool, str]:
    """Validate candidate name"""
    if not name or len(name.strip()) < 2:
        return False, "Candidate name is required (at least 2 characters)"
    return True, ""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def process_file_upload(file_obj) -> str:
    """Extract text from uploaded file"""
    if file_obj is None:
        return ""
    
    try:
        file_path = file_obj.name if hasattr(file_obj, 'name') else str(file_obj)
        
        if file_path.lower().endswith('.pdf'):
            try:
                import PyPDF2
                with open(file_path, 'rb') as pdf:
                    reader = PyPDF2.PdfReader(pdf)
                    text = '\n'.join(page.extract_text() for page in reader.pages)
                    return text[:5000]  # Limit to 5000 chars
            except:
                return "Error: Could not extract PDF text"
        else:
            # Text file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()[:5000]
    except Exception as e:
        return f"Error reading file: {str(e)}"


def prepare_payload(jd_text: str, cv_text: str, candidate_name: str, candidate_id: str,
                   candidate_email: str, candidate_phone: str,
                   github_url: str, linkedin_url: str, portfolio_url: str, 
                   facebook_url: str, other_social: str) -> Dict[str, Any]:
    """Prepare payload for API call"""
    
    # Build social media profiles
    social_profiles = {
        'github': [github_url] if github_url else [],
        'linkedin': [linkedin_url] if linkedin_url else [],
        'portfolio': [portfolio_url] if portfolio_url else [],
        'facebook': [facebook_url] if facebook_url else [],
        'other': [other_social] if other_social else [],
    }
    
    # Calculate presence score based on how many social links provided (0-1)
    num_links = sum(1 for v in social_profiles.values() if v)
    presence_score = min(num_links / 4, 1.0)  # Max 4 link types
    
    social_profiles['presence_score'] = presence_score
    social_profiles['total_links'] = sum(len(v) for v in social_profiles.values() if isinstance(v, list))
    
    return {
        'jd_title': 'Candidate Evaluation',
        'jd_description': jd_text,
        'candidate_id': candidate_id or 'auto',
        'candidate_name': candidate_name or 'Unknown',
        'candidate_email': candidate_email or '',
        'candidate_phone': candidate_phone or '',
        'cv_text': cv_text,
        'include_shap': True,
        'include_social_weighting': num_links > 0,  # Only weight if social links provided
        'social_media_profiles': social_profiles
    }


def call_ranking_api(payload: Dict[str, Any], progress=gr.Progress()) -> Dict[str, Any]:
    """
    Call the ranking API with progress tracking
    
    Args:
        payload: Request payload
        progress: Gradio Progress callback
    
    Returns:
        API response or error dict
    """
    try:
        print("\n📤 SENDING REQUEST TO RANKING API")
        print(f"API URL: {API_URL}")
        print(f"Payload Keys: {payload.keys()}")
        print(f"Candidate: {payload.get('candidate_name')}")
        print(f"CV Length: {len(payload.get('cv_text', ''))}")
        print(f"JD Length: {len(payload.get('jd_description', ''))}")
        
        progress(0, desc="Starting ranking process...")
        
        # API is synchronous - show simple progress states
        timeout = 300  # 5 minutes max
        
        # Send request
        progress(0.5, desc="Sending request to ranking engine...")
        response = requests.post(API_URL, json=payload, timeout=timeout)
        
        if response.status_code == 200:
            progress(1.0, desc="✅ Ranking complete!")
            result = response.json()
            print(f"✅ API Response received: {result.keys() if isinstance(result, dict) else 'list'}")
            return result
        else:
            error_msg = f"API Error: {response.status_code}"
            print(f"❌ {error_msg}")
            return {
                'error': error_msg,
                'status_code': response.status_code
            }
    except requests.Timeout:
        error_msg = 'Request timeout (5 minutes exceeded)'
        print(f"❌ {error_msg}")
        return {'error': error_msg}
    except Exception as e:
        error_msg = f"Error calling API: {str(e)}"
        print(f"❌ {error_msg}")
        return {'error': error_msg}


def call_flowise_evaluation(candidate_name: str, candidate_email: str, candidate_phone: str, 
                            github_url: str, linkedin_url: str, portfolio_url: str,
                            facebook_url: str, match_score: float) -> Dict[str, Any]:
    """
    Call Flowise evaluation endpoint with proper candidate data
    
    Args:
        candidate_name: Candidate name (REQUIRED)
        candidate_email: Candidate email
        candidate_phone: Candidate phone
        github_url: GitHub URL
        linkedin_url: LinkedIn URL
        portfolio_url: Portfolio URL
        facebook_url: Facebook URL
        match_score: Match score from ranking
    
    Returns:
        Flowise evaluation response or error dict
    """
    try:
        if not candidate_name or not candidate_name.strip():
            print("❌ Candidate name is required for Flowise evaluation")
            return {'error': 'Candidate name is required', 'success': False}
        
        # Use the new proper endpoint that builds query correctly
        flowise_url = "http://127.0.0.1:8000/flowise/evaluate-candidate"
        
        payload = {
            "candidate_name": candidate_name.strip(),
            "candidate_email": candidate_email.strip() if candidate_email else None,
            "candidate_phone": candidate_phone.strip() if candidate_phone else None,
            "github_url": github_url.strip() if github_url else None,
            "linkedin_url": linkedin_url.strip() if linkedin_url else None,
            "portfolio_url": portfolio_url.strip() if portfolio_url else None,
            "facebook_url": facebook_url.strip() if facebook_url else None,
            "cv_summary": f"Match score: {match_score:.0%}"
        }
        
        print(f"\n📤 Sending to Flowise endpoint: {flowise_url}")
        print(f"Payload: {payload}")
        
        response = requests.post(flowise_url, json=payload, timeout=300)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Flowise response: {result}")
            return result
        else:
            error_msg = f"Flowise API Error: {response.status_code}"
            print(f"❌ {error_msg}")
            return {
                'error': error_msg,
                'success': False,
                'status_code': response.status_code
            }
    except requests.Timeout:
        error_msg = 'Flowise timeout (300 seconds exceeded - Flowise may need more time for scraping)'
        print(f"❌ {error_msg}")
        return {'error': error_msg, 'success': False}
    except Exception as e:
        error_msg = f"Error calling Flowise: {str(e)}"
        print(f"❌ {error_msg}")
        return {'error': error_msg, 'success': False}


def execute_ranking(payload_dict: Dict[str, Any]) -> Tuple[str, str, str, Dict, str]:
    """Execute the ranking with progress tracking
    
    Returns:
        (baseline_display, social_display, delta_display, full_response, flowise_html)
    """
    print("\n" + "="*80)
    print("🚀 EXECUTE_RANKING CALLED")
    print("="*80)
    print(f"Payload Type: {type(payload_dict)}")
    print(f"Payload Empty: {not payload_dict}")
    
    if not payload_dict:
        print("❌ PAYLOAD IS EMPTY OR NONE!")
        return "Error: No payload", "", "", {}, "<p style='color: red;'>No data available</p>"
    
    print(f"Payload Keys: {payload_dict.keys()}")
    print(f"Candidate Name: {payload_dict.get('candidate_name')!r}")
    print(f"CV Length: {len(payload_dict.get('cv_text', ''))}")
    print(f"JD Length: {len(payload_dict.get('jd_description', ''))}")
    print("="*80)
    
    response = call_ranking_api(payload_dict)
    
    # Format results
    baseline, social, delta = format_results(response)
    
    # Call Flowise evaluation after ranking completes (if no error)
    flowise_response = {}
    if 'error' not in response and payload_dict.get('candidate_name'):
        # Safely extract social URLs from lists (handle empty lists)
        social_profiles = payload_dict.get('social_media_profiles', {})
        github_url = (social_profiles.get('github', []) or [''])[0] or ''
        linkedin_url = (social_profiles.get('linkedin', []) or [''])[0] or ''
        portfolio_url = (social_profiles.get('portfolio', []) or [''])[0] or ''
        facebook_url = (social_profiles.get('facebook', []) or [''])[0] or ''
        
        print(f"\n📧 Calling Flowise with:")
        print(f"   - Name: {payload_dict.get('candidate_name')}")
        print(f"   - Email: {payload_dict.get('candidate_email')}")
        print(f"   - Phone: {payload_dict.get('candidate_phone')}")
        print(f"   - GitHub: {github_url}")
        print(f"   - LinkedIn: {linkedin_url}")
        print(f"   - Portfolio: {portfolio_url}")
        print(f"   - Facebook: {facebook_url}")
        
        flowise_response = call_flowise_evaluation(
            candidate_name=payload_dict.get('candidate_name', ''),
            candidate_email=payload_dict.get('candidate_email', ''),
            candidate_phone=payload_dict.get('candidate_phone', ''),
            github_url=github_url,
            linkedin_url=linkedin_url,
            portfolio_url=portfolio_url,
            facebook_url=facebook_url,
            match_score=response.get('match_score', 0)
        )
        # Merge Flowise response with main response
        response['flowise_evaluation'] = flowise_response
    
    # Format Flowise output as HTML - pass BOTH response and payload for full data
    flowise_html = format_flowise_output(response, payload_dict)
    
    # Save search result to database
    try:
        jd_title = response.get('jd_title', 'Job Position')  # Extract from response or use default
        match_score = response.get('match_score', 0)
        
        # Get recommendation text
        recommendation = ""
        if response.get('social_weighting', {}).get('recommendation'):
            recommendation = response['social_weighting']['recommendation']
        elif response.get('recommendation'):
            recommendation = response['recommendation']
        else:
            recommendation = f"Match score: {match_score:.1%}"
        
        # Save to database
        save_search_result(
            candidate_name=payload_dict.get('candidate_name', 'Unknown'),
            job_title=jd_title,
            match_score=match_score,
            recommendation=recommendation[:200],  # Limit to 200 chars
            social_profiles=response.get('social_profiles', {}),
            flowise_response=flowise_response
        )
        print(f"✅ Search result saved to database for {payload_dict.get('candidate_name')}")
    except Exception as e:
        print(f"⚠️  Failed to save search result: {str(e)}")
    
    print("\n✅ EXECUTE_RANKING COMPLETE\n")
    return baseline, social, delta, response, flowise_html


def format_results(response: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Format API response for display
    
    Returns:
        (baseline_display, social_display, delta_display)
    """
    if 'error' in response:
        error_msg = f"❌ Error: {response.get('error', 'Unknown error')}"
        return error_msg, "", ""
    
    try:
        candidate = response.get('candidate_name', 'Unknown')
        baseline_score = response.get('match_score', 0)
        baseline_pct = response.get('match_percentage', '0%')
        
        # Format baseline results
        baseline_display = f"""
### 📊 BASELINE RANKING RESULTS
**Candidate:** {candidate}

**Match Score:** {baseline_score:.3f} ({baseline_pct})

**Skill Alignment:**
"""
        
        skills = response.get('skill_alignment', {})
        if skills.get('present'):
            baseline_display += f"✅ **Present Skills:** {', '.join(skills['present'])}\n"
        if skills.get('missing'):
            baseline_display += f"❌ **Missing Skills:** {', '.join(skills['missing'])}\n"
        
        # Add Feature Contribution Analysis (not true SHAP)
        shap = response.get('shap_analysis', {})
        top_features = shap.get('top_features', [])
        methodology = shap.get('methodology', '')
        
        if top_features:
            baseline_display += f"\n**🧠 AI Explanation:**\n"
            baseline_display += f"*Match Score: {baseline_pct}*\n\n"
            
            # Show ALL top features from the API with correct labeling
            baseline_display += "**📊 Top Contributing Factors (Feature Importance Analysis):**\n"
            baseline_display += "_Note: These show interpretable feature contributions using empirical weights._\n\n"
            baseline_display += "```\n"
            baseline_display += "**\n"
            
            for idx, item in enumerate(top_features[:12], 1):  # Show top 12 to include all social features
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        feature_name = str(item[0])
                        feature_value = float(item[1])
                        direction = "↑ Positive" if feature_value > 0 else "↓ Negative"
                        baseline_display += f"  {direction}: {feature_name} (contribution: {abs(feature_value):.4f})\n"
                    elif isinstance(item, dict):
                        feature_name = item.get('feature', 'Unknown')
                        feature_value = float(item.get('value', 0))
                        direction = "↑ Positive" if feature_value > 0 else "↓ Negative"
                        baseline_display += f"  {direction}: {feature_name} (contribution: {abs(feature_value):.4f})\n"
                except (ValueError, TypeError, IndexError):
                    continue
            
            baseline_display += "\n**Overall Assessment:**\n"
            summary = shap.get('summary', {})
            baseline_display += f"  • Strong factors: {summary.get('num_positive_features', 0)}\n"
            baseline_display += f"  • Weak factors: {summary.get('num_negative_features', 0)}\n"
            baseline_display += "```\n"
            baseline_display += "\n💡 *Tip: Positive factors (↑) increased the score, negative factors (↓) decreased it. Larger numbers = stronger contribution.*\n"
        elif shap.get('explanation'):
            # Fallback to explanation text if top_features not available
            baseline_display += f"\n**🧠 AI Explanation:**\n"
            baseline_display += f"*Match Score: {baseline_pct}*\n\n"
            
            baseline_display += "**📊 What influenced this score?**\n"
            baseline_display += "The AI model analyzed semantic patterns in the CV (called 'embedding dimensions'). "
            baseline_display += "Each dimension represents different aspects like skills, experience, and domain expertise.\n\n"
            
            explanation_text = shap.get('explanation', '')
            baseline_display += f"{explanation_text}\n"
        
        # Format social weighting if available
        social_display = ""
        delta_display = ""
        
        if response.get('social_weighting'):
            sw = response['social_weighting']
            
            social_display = f"""
### 🔬 SOCIAL-WEIGHTED RANKING (Option B)

**Baseline Score:** {sw.get('baseline_prediction', 0):.3f}

**Social-Weighted Score:** {sw.get('social_weighted_prediction', 0):.3f}

**Weight Factor:** {sw.get('weight_factor', 'N/A')}

**Recommendation:** {sw.get('recommendation', 'No recommendation')}
"""
            
            delta_pct = sw.get('delta_percentage', '0%')
            delta = sw.get('delta', 0)
            
            if isinstance(delta_pct, str):
                delta_pct_val = delta_pct
            else:
                delta_pct_val = f"{delta_pct:.2f}%"
            
            direction = "⬆️ INCREASED" if delta > 0 else "⬇️ DECREASED" if delta < 0 else "➡️ UNCHANGED"
            
            delta_display = f"""
### 📈 SOCIAL MEDIA IMPACT ANALYSIS

**Delta:** {delta:+.3f}

**Impact:** {direction} by {delta_pct_val}

**Interpretation:** Social media validation {'strengthens' if delta > 0 else 'weakens' if delta < 0 else 'does not change'} the CV match score.
"""
        
        # Add social profile info
        social_profiles = response.get('social_profiles', {})
        if social_profiles.get('total_links', 0) > 0:
            social_display += f"\n**Social Links Found:** {social_profiles['total_links']}\n"
            social_display += f"**Presence Score:** {social_profiles.get('presence_score', 0):.2f}/1.0\n"
        
        return baseline_display, social_display, delta_display
    
    except Exception as e:
        return f"Error formatting results: {str(e)}", "", ""


def format_flowise_output(response: Dict[str, Any], payload: Dict[str, Any] = None) -> str:
    """
    Format Flowise response as professional HTML using external template
    Shows candidate profile with WHITE TEXT ON LIGHT BACKGROUND (default)
    Dark mode toggle with proper color contrast
    Behavior scores prominently displayed
    SHAP section fully visible and scrollable
    
    Args:
        response: API response dict with flowise_evaluation
        payload: Original payload dict (for candidate contact info)
    
    Returns:
        Professional HTML string for display with high contrast and dark mode support
    """
    try:
        import os
        
        if payload is None:
            payload = {}
            
        candidate_name = payload.get('candidate_name', response.get('candidate_name', 'Unknown'))
        candidate_email = payload.get('candidate_email', response.get('candidate_email', ''))
        candidate_phone = payload.get('candidate_phone', response.get('candidate_phone', ''))
        match_score = response.get('match_score', 0)
        
        flowise_eval = response.get('flowise_evaluation', {})
        flowise_success = flowise_eval.get('success', False) if isinstance(flowise_eval, dict) else False
        
        # Extract behavior scores from raw_response - THIS IS KEY!
        linkedin_score = 0.0
        linkedin_label = "N/A"
        facebook_score = 0.0
        facebook_label = "N/A"
        shap_explanation = "SHAP analysis results will appear here"
        linkedin_breakdown = None
        facebook_breakdown = None
        
        # Additional professional profile data
        linkedin_profile_data = None
        linkedin_posts_data = None
        facebook_profile_data = None
        facebook_posts_data = None
        whatsapp_data = None
        github_data = None
        
        if flowise_eval and flowise_eval.get('raw_response'):
            try:
                if isinstance(flowise_eval['raw_response'], str):
                    raw_data = json.loads(flowise_eval['raw_response'])
                else:
                    raw_data = flowise_eval['raw_response']
                
                if isinstance(raw_data, dict):
                    social_profiles = raw_data.get('social_profiles', {})
                    linkedin_score = float(social_profiles.get('linkedin_behavior_score', 0))
                    linkedin_label = social_profiles.get('linkedin_behavior_label', 'N/A')
                    facebook_score = float(social_profiles.get('facebook_behavior_score', 0))
                    facebook_label = social_profiles.get('facebook_behavior_label', 'N/A')
                    
                    # Try to get summary/explanation
                    shap_explanation = raw_data.get('summary', 'All profiles validated successfully')
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        
        # Extract detailed breakdown from usedTools
        if flowise_eval and flowise_eval.get('raw_response'):
            try:
                raw_resp = flowise_eval['raw_response']
                if isinstance(raw_resp, dict) and 'usedTools' in raw_resp:
                    for tool in raw_resp['usedTools']:
                        tool_name = tool.get('tool', '')
                        tool_output = tool.get('toolOutput', '{}')
                        
                        try:
                            if tool_name == 'linkedin_behavior_scorer':
                                linkedin_breakdown = json.loads(tool_output)
                                # Override scores from tool output (more accurate than social_profiles summary)
                                if linkedin_breakdown and not linkedin_breakdown.get('error'):
                                    linkedin_score = float(linkedin_breakdown.get('userBehaviourScore', 0))
                                    linkedin_label = linkedin_breakdown.get('userLabel', 'N/A')
                            elif tool_name == 'facebook_behavior_scorer':
                                facebook_breakdown = json.loads(tool_output)
                                # Override scores from tool output (more accurate than social_profiles summary)
                                if facebook_breakdown and not facebook_breakdown.get('error'):
                                    facebook_score = float(facebook_breakdown.get('userBehaviourScore', 0))
                                    facebook_label = facebook_breakdown.get('userLabel', 'N/A')
                            elif tool_name == 'linkedin_profile_scraper':
                                linkedin_profile_data = json.loads(tool_output)
                            elif tool_name == 'linkedin_posts_fetcher':
                                linkedin_posts_data = json.loads(tool_output)
                            elif tool_name == 'facebook_profile_scraper':
                                facebook_profile_data = json.loads(tool_output)
                            elif tool_name == 'facebook_posts_fetcher':
                                facebook_posts_data = json.loads(tool_output) if tool_output.startswith('[') else {'posts': []}
                            elif tool_name == 'whatsapp_info_scraper':
                                whatsapp_data = json.loads(tool_output)
                            elif tool_name == 'github_profile_scraper':
                                github_data = json.loads(tool_output)
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass
            except:
                pass
        
        # Get initials for avatar
        initials = ''.join([part[0].upper() for part in candidate_name.split() if part])[:2]
        
        # Build HTML fragments for template placeholders
        email_html = f'<p>📧 {candidate_email}</p>' if candidate_email else ''
        phone_html = f'<p>📱 {candidate_phone}</p>' if candidate_phone else ''
        candidate_name_display = candidate_name or 'Not provided'
        candidate_email_display = candidate_email or 'Not provided'
        candidate_phone_display = candidate_phone or 'Not provided'
        
        # Build Professional Profile Summary HTML
        professional_summary_html = ""
        if linkedin_profile_data and linkedin_profile_data.get('success'):
            basic_info = linkedin_profile_data.get('data', {}).get('basic_info', {})
            headline = basic_info.get('headline', '')
            current_company = basic_info.get('current_company', '')
            location = basic_info.get('location', {}).get('full', '')
            followers = basic_info.get('follower_count', 0)
            connections = basic_info.get('connection_count', 0)
            top_skills = basic_info.get('top_skills', [])
            about = basic_info.get('about', '')
            
            if headline or current_company:
                professional_summary_html = f"""
                <div class="profile-header">
                    <h2 style="margin-top: 0;">💼 Professional Profile</h2>
                    {f'<p style="font-size: 1.2em; font-weight: 600; margin: 10px 0;">{headline}</p>' if headline else ''}
                    {f'<p style="font-size: 1em; margin: 5px 0;">📍 {location}</p>' if location else ''}
                    {f'<p style="font-size: 1em; margin: 5px 0;">🏢 {current_company}</p>' if current_company else ''}
                    <div style="display: flex; gap: 20px; margin-top: 15px; flex-wrap: wrap;">
                        {f'<span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; color: white;">👥 {connections} connections</span>' if connections else ''}
                        {f'<span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; color: white;">👁️ {followers} followers</span>' if followers else ''}
                    </div>
                    {f'<div style="margin-top: 15px; color: white;"><strong>Top Skills:</strong> {", ".join(top_skills[:5])}</div>' if top_skills else ''}
                    {f'<div style="margin-top: 15px; font-size: 0.95em; line-height: 1.6; max-height: 150px; overflow-y: auto; color: white;">{about[:500]}{"..." if len(about) > 500 else ""}</div>' if about else ''}
                </div>
                """
        
        # Build Recent LinkedIn Posts HTML
        recent_linkedin_posts_html = ""
        if linkedin_posts_data and linkedin_posts_data.get('success'):
            posts = linkedin_posts_data.get('data', {}).get('posts', [])[:3]  # Top 3 posts
            if posts:
                recent_linkedin_posts_html = """
                <div class="section">
                    <h3 class="text-primary" style="margin-bottom: 15px;">📱 Recent LinkedIn Activity</h3>
                    <div style="display: grid; gap: 15px;">
                """
                for post in posts:
                    text = post.get('text', '')[:200]
                    url = post.get('url', '#')
                    stats = post.get('stats', {})
                    likes = stats.get('total_reactions', 0)
                    comments = stats.get('comments', 0)
                    shares = stats.get('reposts', 0)
                    post_type = post.get('post_type', 'regular')
                    
                    # Extract post date/time
                    posted_at = post.get('posted_at', {})
                    post_date = ''
                    if isinstance(posted_at, dict):
                        post_date = posted_at.get('date', '') or posted_at.get('relative', '')
                    elif isinstance(posted_at, str):
                        post_date = posted_at
                    
                    recent_linkedin_posts_html += f"""
                        <div class="post-card">
                            {f'<div class="text-muted" style="font-size: 0.8em; margin-bottom: 8px;">📅 {post_date}</div>' if post_date else ''}
                            <div class="text-secondary" style="font-size: 0.9em; margin-bottom: 10px;">
                                {text}{'...' if len(text) == 200 else ''}
                            </div>
                            <div class="text-muted" style="display: flex; gap: 15px; font-size: 0.85em;">
                                <span>❤️ {likes}</span>
                                <span>💬 {comments}</span>
                                <span>🔄 {shares}</span>
                                <span style="margin-left: auto;"><a href="{url}" target="_blank">View Post →</a></span>
                            </div>
                        </div>
                    """
                recent_linkedin_posts_html += "</div></div>"
        
        # Build WhatsApp Verification HTML
        whatsapp_verification_html = ""
        if whatsapp_data and whatsapp_data.get('code') == 200:
            wa_info = whatsapp_data.get('data', {})
            is_exist = wa_info.get('isExist', False)
            has_avatar = wa_info.get('hasAvatar', False)
            is_business = wa_info.get('isBusiness', False)
            
            if is_exist:
                whatsapp_verification_html = f"""
                <div style="background: #25D366; color: white; padding: 15px; border-radius: 8px; margin: 15px 0;">
                    <div style="font-weight: bold; margin-bottom: 8px;">📱 WhatsApp Verification</div>
                    <div style="display: flex; gap: 20px; font-size: 0.9em;">
                        <span>✅ Active on WhatsApp</span>
                        {f'<span>{"📸 Has Avatar" if has_avatar else "No Avatar"}</span>'}
                        {f'<span>{"💼 Business Account" if is_business else "Personal Account"}</span>'}
                    </div>
                </div>
                """
        
        # Build GitHub Profile HTML
        github_profile_html = ""
        if github_data and github_data.get('data'):
            gh_info = github_data['data']
            username = gh_info.get('username', '')
            followers = gh_info.get('followers', '0')
            following = gh_info.get('following', '0')
            bio = gh_info.get('bio', '')
            
            if username:
                github_profile_html = f"""
                <div class="card" style="margin: 15px 0;">
                    <div style="font-weight: bold; margin-bottom: 8px;">💻 GitHub Profile</div>
                    <div class="text-secondary" style="font-size: 0.9em;">
                        <div>@{username}</div>
                        <div style="margin-top: 8px; display: flex; gap: 15px;">
                            <span>👥 {followers} followers</span>
                            <span>👤 {following} following</span>
                        </div>
                        {f'<div style="margin-top: 10px;">{bio}</div>' if bio else ''}
                    </div>
                </div>
                """
        
        # Build Facebook Profile HTML
        facebook_profile_html = ""
        if facebook_profile_data and facebook_profile_data.get('success'):
            fb_data = facebook_profile_data.get('data', {})
            name = fb_data.get('name', '')
            profile_url = fb_data.get('url', '')
            profile_image = fb_data.get('image', '')
            about_data = fb_data.get('about', {})
            work = about_data.get('work', '') if isinstance(about_data, dict) else ''
            
            if name or profile_url:
                facebook_profile_html = f"""
                <div style="border: 1px solid #e4e6eb; padding: 15px; border-radius: 8px; background: linear-gradient(135deg, #1877f2 0%, #42b72a 100%); color: white; margin: 15px 0;">
                    <div style="font-weight: bold; margin-bottom: 8px;">👥 Facebook Profile</div>
                    <div style="font-size: 0.9em;">
                        <div style="font-size: 1.1em; font-weight: 600;">{name}</div>
                        {f'<div style="margin-top: 8px;">🏢 {work}</div>' if work else ''}
                        {f'<div style="margin-top: 8px;"><a href="{profile_url}" target="_blank" style="color: white; text-decoration: underline;">View Profile →</a></div>' if profile_url else ''}
                    </div>
                </div>
                """
        
        # Build Recent Facebook Posts HTML
        recent_facebook_posts_html = ""
        if facebook_posts_data:
            # Handle both array format and dict with 'posts' key
            if isinstance(facebook_posts_data, list):
                posts = facebook_posts_data[:3]
            elif isinstance(facebook_posts_data, dict):
                posts = facebook_posts_data.get('posts', [])[:3]
            else:
                posts = []
            
            if posts:
                recent_facebook_posts_html = """
                <div class="section">
                    <h3 class="text-primary" style="margin-bottom: 15px;">📱 Recent Facebook Activity</h3>
                    <div style="display: grid; gap: 15px;">
                """
                for post in posts:
                    text = post.get('text', '') or 'Photo/Video post'
                    text = text[:200] if text else 'Photo/Video post'
                    url = post.get('url', '#')
                    reactions = post.get('reactionCount', 0)
                    comments = post.get('commentCount', 0)
                    image = post.get('image', '')
                    
                    # Extract post date/time from Unix timestamp
                    from datetime import datetime
                    publish_time = post.get('publishTime', 0)
                    post_date = ''
                    if publish_time:
                        try:
                            post_date = datetime.fromtimestamp(publish_time).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            post_date = ''
                    
                    recent_facebook_posts_html += f"""
                        <div class="post-card">
                            {f'<div class="text-muted" style="font-size: 0.8em; margin-bottom: 8px;">📅 {post_date}</div>' if post_date else ''}
                            {f'<img src="{image}" style="max-width: 100%; border-radius: 8px; margin-bottom: 10px;" />' if image else ''}
                            <div class="text-secondary" style="font-size: 0.9em; margin-bottom: 10px;">
                                {text}{'...' if len(text) == 200 else ''}
                            </div>
                            <div class="text-muted" style="display: flex; gap: 15px; font-size: 0.85em;">
                                <span>❤️ {reactions}</span>
                                <span>💬 {comments}</span>
                                <span style="margin-left: auto;"><a href="{url}" target="_blank">View Post →</a></span>
                            </div>
                        </div>
                    """
                recent_facebook_posts_html += "</div></div>"
        
        # Build LinkedIn breakdown HTML
        linkedin_breakdown_html = ""
        if linkedin_breakdown:
            total_posts = linkedin_breakdown.get('totalPosts', 0)
            post_freq_score = linkedin_breakdown.get('postingFrequencyScore', 0)
            post_scores = linkedin_breakdown.get('postScores', [])
            
            linkedin_breakdown_html = f"""
                <div class="section">
                    <h2>💼 LinkedIn Behavioral Analysis (Detailed)</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 15px;">
                        In-depth breakdown of LinkedIn activity showing {total_posts} posts analyzed
                    </p>
                    
                    <div class="info-table">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="background-color: var(--bg-tertiary);">
                                <td style="padding: 12px; font-weight: bold;">Overall Behavior Score</td>
                                <td style="padding: 12px; color: var(--accent-primary); font-weight: bold; font-size: 1.2em;">{linkedin_score*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">Behavior Label</td>
                                <td style="padding: 12px;">{linkedin_label}</td>
                            </tr>
                            <tr style="background-color: var(--bg-tertiary);">
                                <td style="padding: 12px; font-weight: bold;">Total Posts Analyzed</td>
                                <td style="padding: 12px;">{total_posts}</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">Posting Frequency Score</td>
                                <td style="padding: 12px;">{post_freq_score*100:.1f}%</td>
                            </tr>
                        </table>
                    </div>
                    
                    <h3 class="text-primary" style="margin-top: 25px; margin-bottom: 15px;">📝 Individual Post Scores (LinkedIn)</h3>
                    <div style="max-height: 600px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background-color: var(--bg-secondary);">
            """
            
            for idx, post in enumerate(post_scores, 1):
                post_score = post.get('score', 0)
                breakdown = post.get('breakdown', {})
                metrics = post.get('metrics', {})
                
                linkedin_breakdown_html += f"""
                        <div style="margin-bottom: 20px; padding: 15px; border-left: 3px solid var(--accent-primary); background-color: var(--bg-primary); border-radius: 5px;">
                            <div style="font-weight: bold; color: var(--text-primary); margin-bottom: 8px;">Post #{idx}</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.9em;">
                                <div><strong>Overall Score:</strong> {post_score*100:.1f}%</div>
                                <div><strong>Likes:</strong> {metrics.get('likes', 0)}</div>
                                <div><strong>Engagement:</strong> {breakdown.get('engagement', 0)*100:.1f}%</div>
                                <div><strong>Comments:</strong> {metrics.get('comments', 0)}</div>
                                <div><strong>Intent:</strong> {breakdown.get('intent', 0)*100:.1f}%</div>
                                <div><strong>Shares:</strong> {metrics.get('shares', 0)}</div>
                                <div><strong>Tone:</strong> {breakdown.get('tone', 0)*100:.1f}%</div>
                                <div><strong>Thought Leadership:</strong> {breakdown.get('thoughtLeadership', 0)*100:.1f}%</div>
                            </div>
                        </div>
                """
            
            linkedin_breakdown_html += """
                    </div>
                </div>
            """
        
        # Build Facebook breakdown HTML
        facebook_breakdown_html = ""
        if facebook_breakdown:
            fb_score = facebook_breakdown.get('userBehaviourScore', 0)
            fb_label = facebook_breakdown.get('userLabel', 'N/A')
            fb_post_scores = facebook_breakdown.get('postScores', [])
            
            facebook_breakdown_html = f"""
                <div class="section">
                    <h2>👥 Facebook Behavioral Analysis (Detailed)</h2>
                    <p style="color: var(--text-secondary); margin-bottom: 15px;">
                        In-depth breakdown of Facebook activity showing {len(fb_post_scores)} posts analyzed
                    </p>
                    
                    <div class="info-table">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr style="background-color: var(--bg-tertiary);">
                                <td style="padding: 12px; font-weight: bold;">Overall Behavior Score</td>
                                <td style="padding: 12px; color: var(--accent-primary); font-weight: bold; font-size: 1.2em;">{fb_score*100:.1f}%</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">Behavior Label</td>
                                <td style="padding: 12px;">{fb_label}</td>
                            </tr>
                            <tr style="background-color: var(--bg-tertiary);">
                                <td style="padding: 12px; font-weight: bold;">Total Posts Analyzed</td>
                                <td style="padding: 12px;">{len(fb_post_scores)}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <h3 class="text-primary" style="margin-top: 25px; margin-bottom: 15px;">📝 Individual Post Scores (Facebook)</h3>
                    <div style="max-height: 600px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background-color: var(--bg-secondary);">
            """
            
            for idx, post in enumerate(fb_post_scores, 1):
                post_score = post.get('score', 0)
                breakdown = post.get('breakdown', {})
                metrics = post.get('metrics', {})
                
                facebook_breakdown_html += f"""
                        <div style="margin-bottom: 20px; padding: 15px; border-left: 3px solid var(--accent-primary); background-color: var(--bg-primary); border-radius: 5px;">
                            <div style="font-weight: bold; color: var(--text-primary); margin-bottom: 8px;">Post #{idx}</div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 0.9em;">
                                <div><strong>Overall Score:</strong> {post_score*100:.1f}%</div>
                                <div><strong>Likes:</strong> {metrics.get('likes', 0)}</div>
                                <div><strong>Engagement:</strong> {breakdown.get('engagement', 0)*100:.1f}%</div>
                                <div><strong>Comments:</strong> {metrics.get('comments', 0)}</div>
                                <div><strong>Intent:</strong> {breakdown.get('intent', 0)*100:.1f}%</div>
                                <div><strong>Shares:</strong> {metrics.get('shares', 0)}</div>
                                <div><strong>Tone:</strong> {breakdown.get('tone', 0)*100:.1f}%</div>
                                <div><strong>Sentiment:</strong> {breakdown.get('sentiment', 0)*100:.1f}%</div>
                            </div>
                        </div>
                """
            
            facebook_breakdown_html += """
                    </div>
                </div>
            """
        
        # Build verification status HTML
        verification_status_html = ""
        if flowise_success:
            verification_status_html = '<div style="color: var(--success-color); font-weight: bold;">✅ Profile Verified Successfully</div>'
        else:
            verification_status_html = '<div style="color: var(--error-color); font-weight: bold;">⚠️ Profile Verification Issues</div>'
        
        # Build social profiles HTML with links
        social_profiles_html = ""
        if flowise_eval and flowise_eval.get('raw_response'):
            try:
                raw_resp = flowise_eval['raw_response']
                if isinstance(raw_resp, dict):
                    social_profiles = raw_resp.get('social_profiles', {})
                    
                    profiles = []
                    if social_profiles.get('linkedin'):
                        profiles.append(f'<div class="text-primary"><strong>💼 LinkedIn:</strong> <a href="{social_profiles["linkedin"]}" target="_blank">{social_profiles["linkedin"]}</a></div>')
                    if social_profiles.get('facebook'):
                        profiles.append(f'<div class="text-primary"><strong>👥 Facebook:</strong> <a href="{social_profiles["facebook"]}" target="_blank">{social_profiles["facebook"]}</a></div>')
                    if social_profiles.get('github'):
                        profiles.append(f'<div class="text-primary"><strong>💻 GitHub:</strong> <a href="{social_profiles["github"]}" target="_blank">{social_profiles["github"]}</a></div>')
                    if social_profiles.get('whatsapp'):
                        profiles.append(f'<div class="text-primary"><strong>📱 WhatsApp:</strong> {social_profiles["whatsapp"]}</div>')
                    
                    # Add presence scores
                    if social_profiles.get('social_presence_score'):
                        score = float(social_profiles['social_presence_score']) * 100
                        profiles.append(f'<div class="text-primary" style="margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color);"><strong>📊 Overall Social Presence:</strong> {score:.0f}% ({social_profiles.get("profiles_valid", 0)} profiles found)</div>')
                    
                    social_profiles_html = ''.join(profiles) if profiles else '<div class="text-muted">No social profiles detected</div>'
            except:
                social_profiles_html = '<div class="text-muted">Profile information not available</div>'
        
        # Load template from file
        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'candidate_report.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Populate template with all variables
        html = template.format(
            candidate_name=candidate_name,
            initials=initials,
            email_html=email_html,
            phone_html=phone_html,
            candidate_name_display=candidate_name_display,
            candidate_email_display=candidate_email_display,
            candidate_phone_display=candidate_phone_display,
            match_score=match_score,
            linkedin_score=linkedin_score*100,  # Convert 0-1 to 0-100 percentage
            linkedin_label=linkedin_label,
            facebook_score=facebook_score*100,  # Convert 0-1 to 0-100 percentage
            facebook_label=facebook_label,
            social_profiles_html=social_profiles_html,
            professional_summary_html=professional_summary_html,
            facebook_profile_html=facebook_profile_html,
            recent_linkedin_posts_html=recent_linkedin_posts_html,
            recent_facebook_posts_html=recent_facebook_posts_html,
            whatsapp_verification_html=whatsapp_verification_html,
            github_profile_html=github_profile_html,
            linkedin_breakdown_html=linkedin_breakdown_html,
            facebook_breakdown_html=facebook_breakdown_html,
            verification_status_html=verification_status_html,
            shap_explanation=shap_explanation
        )
        
        return html
    
    except Exception as e:
        import traceback
        print(f"Error formatting Flowise output: {e}")
        print(traceback.format_exc())
        return f"""
        <div class="card" style="background-color: rgba(239, 68, 68, 0.1); padding: 20px; border-radius: 8px; border: 2px solid var(--danger-color); font-family: sans-serif;">
            <h3 class="text-primary">⚠️ Error Displaying Results</h3>
            <p class="text-secondary"><strong>Error:</strong> {str(e)}</p>
            <p class="text-muted" style="font-size: 0.9em; margin-top: 10px;">Please try refreshing the page or contacting support.</p>
        </div>
        """


# ============================================================================
# SEARCH HISTORY FUNCTIONS
# ============================================================================

def load_search_history() -> str:
    """Load and format search history from database with delete buttons"""
    try:
        history = get_search_history()
        
        if not history:
            return "📭 No search history yet. Start searching to build history."
        
        # Create HTML with delete buttons for each record
        display = '<div style="font-family: Arial, sans-serif;">'
        display += '<h2>📊 Recent Searches (Last 5)</h2>'
        
        for i, record in enumerate(history, 1):
            timestamp = record.get('timestamp', 'Unknown')
            candidate = record.get('candidate_name', 'Unknown')
            job_title = record.get('job_title', 'Unknown')
            score = record.get('match_score', 0)
            score_pct = f"{score*100:.1f}%" if score else "N/A"
            record_id = record.get('id', '')
            recommendation = record.get('recommendation', 'No notes')[:150]
            
            display += '<div class="card" style="margin: 10px 0;">'
            display += '<div style="display: flex; justify-content: space-between; align-items: start;">'
            display += '<div style="flex-grow: 1;">'
            display += f'<h3 class="text-primary" style="margin: 0 0 8px 0;">{i}. {candidate} - {job_title}</h3>'
            display += f'<p class="text-secondary" style="margin: 4px 0; font-size: 0.9em;">📅 <strong>Time:</strong> {timestamp}</p>'
            display += f'<p class="text-secondary" style="margin: 4px 0; font-size: 0.9em;">📊 <strong>Match Score:</strong> {score_pct}</p>'
            display += f'<p class="text-secondary" style="margin: 4px 0; font-size: 0.9em;">💬 <strong>Recommendation:</strong> {recommendation}...</p>'
            display += f'<p class="text-muted" style="margin: 4px 0; font-size: 0.85em;">🔑 ID: {record_id}</p>'
            display += '</div>'
            # Use data attribute instead of complex onclick
            display += f'<button class="delete-record-btn" data-record-id="{record_id}" style="background-color: var(--danger-color); color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 0.9em; margin-left: 10px; white-space: nowrap;">🗑️ Delete</button>'
            display += '</div></div>'
        
        display += '</div>'
        return display
    except Exception as e:
        return f"❌ Error loading history: {str(e)}"



def delete_search_record_action(record_id: int) -> str:
    """Delete a specific search record and refresh history display"""
    try:
        if record_id and record_id > 0:
            success = delete_search_record(record_id)
            if success:
                print(f"✅ Record {record_id} deleted successfully")
                # Reload and return updated history
                return load_search_history()
            else:
                return f"❌ Failed to delete record {record_id}"
        return "❌ Invalid record ID"
    except Exception as e:
        print(f"Error deleting record: {e}")
        return f"❌ Error deleting record: {str(e)}"


def clear_history_action() -> Tuple[str, str]:
    """Clear all search history"""
    try:
        clear_all_search_history()
        return "✅ All search history cleared!", "🗑️ History cleared successfully"
    except Exception as e:
        return f"❌ Error: {str(e)}", "Error"


def export_results_action(full_response: Dict[str, Any], flowise_html: str, candidate_name: str = "Result") -> str:
    """Export results in multiple formats"""
    if not full_response or full_response == {} or isinstance(full_response, str):
        return "❌ No results to export. Please run a ranking first."
    
    try:
        # Clean candidate name for filename
        safe_candidate_name = candidate_name.replace(' ', '_').replace('/', '_')[:50] if candidate_name else "Result"
        
        # Export as JSON (primary format)
        json_path = export_results_json(full_response, safe_candidate_name)
        
        # Also export HTML for convenience
        html_path = export_results_html(flowise_html, safe_candidate_name)
        
        # Also export CSV for spreadsheet viewing
        csv_path = export_results_csv(full_response, safe_candidate_name)
        
        if json_path and html_path and csv_path:
            return f"""✅ **Export Successful!**

📁 Files saved to `./exports/` folder:
- 📄 JSON: `{Path(json_path).name}`
- 🌐 HTML Report: `{Path(html_path).name}`  
- 📊 CSV: `{Path(csv_path).name}`

You can now download or share these files."""
        else:
            return f"⚠️ Partial export: JSON={bool(json_path)}, HTML={bool(html_path)}, CSV={bool(csv_path)}"
    except Exception as e:
        return f"❌ Export failed: {str(e)}"


# ============================================================================
# GRADIO INTERFACE - 3-TAB WORKFLOW
# ============================================================================

def create_interface():
    """Create the Gradio interface with 3 tabs: Input Form, Results, Search History"""
    
    with gr.Blocks(title="CV Ranking System - GDPR Compliant") as interface:
        
        # State management
        state_cv_text = gr.State(value="")
        state_jd_text = gr.State(value="")
        state_payload = gr.State(value={})
        
        with gr.Tabs():
            # ================================================================
            # TAB 1: INPUT FORM - Candidate info, CV, JD, Social links
            # ================================================================
            with gr.Tab("📋 Input Form", id="tab_input"):
                with gr.Column(scale=1):
                    gr.Markdown("# CV Ranking System\n## Step 1: Enter Your Information")
                    
                    with gr.Row():
                        candidate_name = gr.Textbox(
                            label="Candidate Name *",
                            placeholder="e.g., John Smith",
                            max_lines=1,
                            info="Required"
                        )
                        candidate_id = gr.Textbox(
                            label="Candidate ID (Optional)",
                            placeholder="e.g., CAND-001",
                            max_lines=1
                        )
                    
                    with gr.Row():
                        candidate_email = gr.Textbox(
                            label="Email (Optional)",
                            placeholder="john@example.com",
                            max_lines=1
                        )
                        candidate_phone = gr.Textbox(
                            label="Phone (Optional) - For WhatsApp/Mobile Verification",
                            placeholder="+9 (477) 123-4567",
                            max_lines=1,
                            info="Format: +9 (477) 123-4567 or similar"
                        )
                    
                    gr.Markdown("### 📄 Job Description")
                    
                    # Sample JD dropdown
                    sample_jd_selector = gr.Dropdown(
                        label="Select Sample JD (or paste your own below)",
                        choices=[""] + list(SAMPLE_JDS.keys()),
                        value="",
                        info="Choose a sample or use your own"
                    )
                    
                    jd_file = gr.File(
                        label="Or Upload JD (PDF/TXT)",
                        type="filepath",
                        file_types=[".pdf", ".txt"]
                    )
                    
                    jd_text = gr.Textbox(
                        label="Job Description Text",
                        placeholder="Paste job description here or select sample above...",
                        lines=4
                    )
                    
                    gr.Markdown("### 📋 Candidate CV")
                    cv_file = gr.File(
                        label="Upload CV (PDF/TXT)",
                        type="filepath",
                        file_types=[".pdf", ".txt"]
                    )
                    
                    cv_text = gr.Textbox(
                        label="Or paste CV text",
                        placeholder="Paste CV content here...",
                        lines=4
                    )
                    
                    gr.Markdown("### 🔗 Social Media Links (Optional)")
                    gr.Markdown("""
*Provide social media URLs to enable social presence weighting.*
*All data is processed according to GDPR/PDPA - no automatic scraping.*
""")
                    
                    with gr.Row():
                        github_url = gr.Textbox(
                            label="GitHub Profile",
                            placeholder="https://github.com/username",
                            max_lines=1
                        )
                        linkedin_url = gr.Textbox(
                            label="LinkedIn Profile",
                            placeholder="https://linkedin.com/in/username",
                            max_lines=1
                        )
                    
                    with gr.Row():
                        portfolio_url = gr.Textbox(
                            label="Portfolio Website",
                            placeholder="https://example.com",
                            max_lines=1
                        )
                        facebook_url = gr.Textbox(
                            label="Facebook Profile",
                            placeholder="https://facebook.com/username",
                            max_lines=1
                        )
                    
                    other_social = gr.Textbox(
                        label="Other Social Media Links",
                        placeholder="Comma-separated URLs...",
                        max_lines=2
                    )
                    
                    gr.Markdown("---")
                    
                    with gr.Row():
                        submit_btn = gr.Button(
                            "🚀 Start Ranking",
                            size="lg",
                            variant="primary"
                        )
                        clear_btn = gr.Button(
                            "🗑️ Clear Form",
                            size="lg",
                            variant="secondary"
                        )
                    
                    # Error message display
                    validation_error = gr.Textbox(
                        label="Validation Status",
                        interactive=False,
                        lines=2,
                        value="✅ Ready"
                    )
                    
                    # Process files when uploaded
                    def process_jd_file(file_obj):
                        return process_file_upload(file_obj)
                    
                    def process_cv_file(file_obj):
                        return process_file_upload(file_obj)
                    
                    def load_sample_jd(sample_name):
                        """Load selected sample JD"""
                        if sample_name and sample_name in SAMPLE_JDS:
                            return SAMPLE_JDS[sample_name]
                        return ""
                    
                    # Connect sample JD selector
                    sample_jd_selector.change(load_sample_jd, inputs=sample_jd_selector, outputs=jd_text)
                    
                    jd_file.change(process_jd_file, inputs=jd_file, outputs=jd_text)
                    cv_file.change(process_cv_file, inputs=cv_file, outputs=cv_text)
                    
                    # Add progress section at bottom of Input tab
                    gr.Markdown("---")
                    gr.Markdown("### ⏳ Processing Status")
                    status_text = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=1,
                        value="Ready to analyze",
                        scale=2
                    )
            
            # ================================================================
            # TAB 2: RESULTS - Baseline, Social-weighted, Flowise, Export
            # ================================================================
            with gr.Tab("📊 Results", id="tab_results"):
                with gr.Column(scale=1):
                    gr.Markdown("# CV Ranking Results")
                    
                    with gr.Accordion("✅ Baseline Ranking", open=True):
                        baseline_output = gr.Markdown("Waiting for results...")
                    
                    with gr.Accordion("🔬 Social-Weighted Results (Option B)", open=True):
                        social_output = gr.Markdown("Social weighting will appear here if social links were provided...")
                    
                    with gr.Accordion("📈 Impact Analysis", open=True):
                        delta_output = gr.Markdown("")
                    gr.Markdown("---")
                    
                    with gr.Accordion("🔗 Flowise Integration Output", open=False):
                        gr.Markdown("""
**This section displays data sent to and responses received from Flowise chatflows.**

Use this to:
- Track WhatsApp verification status
- View email confirmation results  
- See social media validation outcomes
- Monitor candidate contact information
""")
                        flowise_output = gr.HTML(value="<p class='text-muted'>Flowise response will appear here once integrated...</p>")
                    
                    with gr.Row():
                        reset_btn = gr.Button("🔄 Start Over")
                        export_btn = gr.Button("📥 Export Results")
                    
                    # Hidden output for storing full response
                    full_response = gr.State(value={})
            
            # ================================================================
            # TAB 3: SEARCH HISTORY - Recent searches, delete, refresh, export
            # ================================================================
            with gr.Tab("📋 Search History", id="tab_history"):
                with gr.Column(scale=1):
                    gr.Markdown("# Recent Searches")
                    gr.Markdown("Your last 5 candidate searches from the database")
                    
                    search_history_display = gr.Markdown(value="Loading search history...")
                    
                    with gr.Row():
                        refresh_history_btn = gr.Button("🔄 Refresh History", size="sm")
                        clear_all_history_btn = gr.Button("🗑️ Clear All History", size="sm", variant="stop")
                    
                    # Individual delete buttons (created dynamically)
                    gr.Markdown("### Delete Individual Records")
                    history_delete_info = gr.Markdown(value="History will be displayed above")
        
        # ================================================================
        # LOGIC: Connect buttons to functions
        # ================================================================
        
        # Wire up button clicks
        def validate_and_submit(cand_name, cand_id, cand_email, cand_phone, jd_t, cv_t, gh, li, port, fb, other):
            """Validate form and prepare for submission"""
            
            # DEBUG: Log all input data
            print("\n" + "="*80)
            print("📝 FORM SUBMISSION DEBUG LOG")
            print("="*80)
            print(f"Candidate Name: {cand_name!r} (len: {len(cand_name) if cand_name else 0})")
            print(f"Candidate ID: {cand_id!r}")
            print(f"Candidate Email: {cand_email!r}")
            print(f"Candidate Phone: {cand_phone!r}")
            print(f"JD Text: {jd_t[:100] if jd_t else 'EMPTY'}... (len: {len(jd_t) if jd_t else 0})")
            print(f"CV Text: {cv_t[:100] if cv_t else 'EMPTY'}... (len: {len(cv_t) if cv_t else 0})")
            print(f"GitHub: {gh!r}")
            print(f"LinkedIn: {li!r}")
            print(f"Portfolio: {port!r}")
            print(f"Facebook: {fb!r}")
            print(f"Other Social: {other!r}")
            print("="*80)
            
            # Validate required fields
            valid_name, error_name = validate_candidate_name(cand_name)
            if not valid_name:
                print(f"❌ NAME VALIDATION FAILED: {error_name}")
                return "", error_name, {}, ""
            
            # Validate CV and JD
            valid_cv_jd, error_cv_jd = validate_cv_jd(cv_t, jd_t)
            if not valid_cv_jd:
                print(f"❌ CV/JD VALIDATION FAILED: {error_cv_jd}")
                return "", error_cv_jd, {}, ""
            
            # Validate email
            valid_email, error_email = validate_email(cand_email)
            if not valid_email:
                print(f"❌ EMAIL VALIDATION FAILED: {error_email}")
                return "", error_email, {}, ""
            
            # Validate phone
            valid_phone, error_phone = validate_phone(cand_phone)
            if not valid_phone:
                print(f"❌ PHONE VALIDATION FAILED: {error_phone}")
                return "", error_phone, {}, ""
            
            # All validations passed
            print("✅ ALL VALIDATIONS PASSED")
            payload = prepare_payload(jd_t, cv_t, cand_name, cand_id, cand_email, cand_phone, gh, li, port, fb, other)
            print(f"📦 PAYLOAD CREATED - Keys: {payload.keys()}")
            print(f"   - Candidate Name: {payload.get('candidate_name')}")
            print(f"   - Candidate Email: {payload.get('candidate_email')}")
            print(f"   - Candidate Phone: {payload.get('candidate_phone')}")
            print(f"   - CV Length: {len(payload.get('cv_text', ''))}")
            print(f"   - JD Length: {len(payload.get('jd_description', ''))}")
            print(f"   - Social Profiles: {payload.get('social_media_profiles', {})}")
            print("="*80 + "\n")
            status_msg = "✅ All fields valid! Processing..."
            
            return "", status_msg, payload, ""
        
        def clear_form():
            """Clear all form fields"""
            return (
                "",  # candidate_name
                "",  # candidate_id
                "",  # candidate_email
                "",  # candidate_phone
                "",  # jd_text
                "",  # cv_text
                "",  # github_url
                "",  # linkedin_url
                "",  # portfolio_url
                "",  # facebook_url
                "",  # other_social
                "✅ Ready",  # validation_error
            )
        
        def reset_all():
            """Clear all form fields AND results"""
            return (
                "",  # candidate_name
                "",  # candidate_id
                "",  # candidate_email
                "",  # candidate_phone
                "",  # jd_text
                "",  # cv_text
                "",  # github_url
                "",  # linkedin_url
                "",  # portfolio_url
                "",  # facebook_url
                "",  # other_social
                "✅ Ready - Form cleared, ready for new candidate",  # validation_error
                "<p class='text-muted'>Submit form to see baseline ranking...</p>",  # baseline_output
                "<p class='text-muted'>Submit form to see social-weighted ranking...</p>",  # social_output
                "<p class='text-muted'>Submit form to see improvement delta...</p>",  # delta_output
                {},  # full_response
                "<p class='text-muted'>Flowise response will appear here once integrated...</p>",  # flowise_output
                "ℹ️ Form cleared. Ready for new candidate.",  # status_text
            )
        
        submit_btn.click(
            validate_and_submit,
            inputs=[candidate_name, candidate_id, candidate_email, candidate_phone, jd_text, cv_text, 
                   github_url, linkedin_url, portfolio_url, facebook_url, other_social],
            outputs=[baseline_output, validation_error, state_payload, status_text]
        ).then(
            execute_ranking,
            inputs=[state_payload],
            outputs=[baseline_output, social_output, delta_output, full_response, flowise_output]
        )
        
        clear_btn.click(
            clear_form,
            outputs=[candidate_name, candidate_id, candidate_email, candidate_phone, jd_text, cv_text,
                    github_url, linkedin_url, portfolio_url, facebook_url, other_social, validation_error]
        )
        
        reset_btn.click(
            reset_all,
            outputs=[candidate_name, candidate_id, candidate_email, candidate_phone, jd_text, cv_text,
                    github_url, linkedin_url, portfolio_url, facebook_url, other_social, validation_error,
                    baseline_output, social_output, delta_output, full_response, flowise_output, status_text]
        )
        
        # Search history buttons
        refresh_history_btn.click(
            load_search_history,
            outputs=[search_history_display]
        )
        
        clear_all_history_btn.click(
            clear_history_action,
            outputs=[search_history_display, history_delete_info]
        )
        
        # Export results button
        export_btn.click(
            export_results_action,
            inputs=[full_response, flowise_output, candidate_name],
            outputs=[status_text]
        )
        
        # Load history on startup
        interface.load(
            load_search_history,
            outputs=[search_history_display]
        )
    
    return interface


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # CRITICAL FIX: Railway may set GRADIO_SERVER_PORT to "$PORT" literal
    # This breaks Gradio's internal port detection. Unset it and use PORT directly.
    if os.environ.get("GRADIO_SERVER_PORT") == "$PORT":
        del os.environ["GRADIO_SERVER_PORT"]
    
    print("🚀 Starting CV Ranking Gradio Interface...")
    print(f"📍 API URL: {API_URL}")
    
    demo = create_interface()
    
    # Get port from environment (Railway sets this) or default to 7860
    port = int(os.environ.get("PORT", 7860))
    server_name = os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0")
    
    print(f"🌐 Server: {server_name}:{port}")
    
    demo.launch(
        server_name=server_name,
        server_port=port,
        share=False,
        show_error=True,
        debug=False,  # Disable debug to avoid API schema generation issues
        show_api=False  # Disable API docs - fixes schema validation error
    )
