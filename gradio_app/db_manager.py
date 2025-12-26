"""
Search History Database Manager
Stores and retrieves last 5 candidate search records
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import os

DB_PATH = os.environ.get("DATABASE_PATH", "./data_storage/search_history.db")
MAX_RECORDS = int(os.environ.get("MAX_SEARCH_HISTORY", 5))

# Ensure data directory exists
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def init_database():
    """Initialize SQLite database with search history table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            candidate_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            match_score REAL,
            recommendation TEXT,
            social_profiles TEXT,
            flowise_response TEXT,
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def save_search_result(
    candidate_name: str,
    job_title: str,
    match_score: float,
    recommendation: str,
    social_profiles: Dict[str, Any],
    flowise_response: Dict[str, Any] = None,
    notes: str = ""
) -> int:
    """
    Save a search result to the database
    
    Args:
        candidate_name: Name of the candidate
        job_title: Job title
        match_score: Match score (0-1)
        recommendation: Recommendation text
        social_profiles: Dict of social profiles
        flowise_response: Flowise API response
        notes: Additional notes
    
    Returns:
        ID of inserted record
    """
    init_database()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO search_history 
        (candidate_name, job_title, match_score, recommendation, social_profiles, flowise_response, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        candidate_name,
        job_title,
        match_score,
        recommendation,
        json.dumps(social_profiles),
        json.dumps(flowise_response) if flowise_response else None,
        notes
    ))
    
    conn.commit()
    record_id = cursor.lastrowid
    
    # Keep only last MAX_RECORDS (delete oldest records)
    # First, count total records
    cursor.execute('SELECT COUNT(*) FROM search_history')
    total_records = cursor.fetchone()[0]
    
    if total_records > MAX_RECORDS:
        # Delete oldest records, keeping only the latest MAX_RECORDS
        cursor.execute(f'''
            DELETE FROM search_history 
            WHERE id IN (
                SELECT id FROM search_history 
                ORDER BY timestamp ASC 
                LIMIT ?
            )
        ''', (total_records - MAX_RECORDS,))
    
    conn.commit()
    conn.close()
    
    return record_id


def get_search_history() -> List[Dict[str, Any]]:
    """
    Retrieve last N search records
    
    Returns:
        List of search history records
    """
    init_database()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, timestamp, candidate_name, job_title, match_score, recommendation, social_profiles, notes
        FROM search_history
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (MAX_RECORDS,))
    
    columns = [description[0] for description in cursor.description]
    results = []
    
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        try:
            record['social_profiles'] = json.loads(record['social_profiles']) if record['social_profiles'] else {}
        except:
            record['social_profiles'] = {}
        results.append(record)
    
    conn.close()
    return results


def get_search_result_by_id(record_id: int) -> Dict[str, Any]:
    """Get a specific search result by ID"""
    init_database()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, timestamp, candidate_name, job_title, match_score, recommendation, social_profiles, flowise_response, notes
        FROM search_history
        WHERE id = ?
    ''', (record_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    columns = [description[0] for description in cursor.description]
    record = dict(zip(columns, row))
    
    try:
        record['social_profiles'] = json.loads(record['social_profiles']) if record['social_profiles'] else {}
        record['flowise_response'] = json.loads(record['flowise_response']) if record['flowise_response'] else {}
    except:
        pass
    
    return record


def clear_all_search_history():
    """Clear all search history"""
    init_database()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM search_history')
    conn.commit()
    conn.close()


def format_search_history_display() -> str:
    """Format search history for display in UI"""
    history = get_search_history()
    
    if not history:
        return "No search history yet"
    
    display = "## Recent Searches (Last 5):\n\n"
    
    for i, record in enumerate(history, 1):
        display += f"**{i}. {record['candidate_name']}** - {record['job_title']}\n"
        display += f"   • Score: {record['match_score']:.1%}\n"
        display += f"   • Time: {record['timestamp']}\n"
        display += f"   • {record['recommendation'][:100]}...\n\n"
    
    return display


def delete_search_record(record_id: int) -> bool:
    """Delete a specific search record by ID"""
    try:
        init_database()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM search_history WHERE id = ?', (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting record {record_id}: {e}")
        return False


def export_results_json(full_response: Dict[str, Any], candidate_name: str = "result") -> str:
    """
    Export ranking results as JSON file
    
    Args:
        full_response: Complete response dict from ranking API
        candidate_name: Name for the export file
    
    Returns:
        Path to exported file
    """
    try:
        export_dir = Path("./exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = candidate_name.replace(' ', '_').replace('/', '_')[:50]
        export_path = export_dir / f"{safe_name}_{timestamp}.json"
        
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(full_response, f, indent=2, default=str)
        
        return str(export_path)
    except Exception as e:
        print(f"Error exporting JSON: {e}")
        return None


def export_results_html(html_content: str, candidate_name: str = "result") -> str:
    """
    Export results as self-contained HTML file
    
    Args:
        html_content: HTML string to export
        candidate_name: Name for the export file
    
    Returns:
        Path to exported file
    """
    try:
        export_dir = Path("./exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = candidate_name.replace(' ', '_').replace('/', '_')[:50]
        export_path = export_dir / f"{safe_name}_{timestamp}.html"
        
        # Wrap in minimal HTML structure if not already wrapped
        if not html_content.startswith('<!DOCTYPE'):
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV Ranking Report - {candidate_name}</title>
</head>
<body>
{html_content}
</body>
</html>"""
        
        with open(export_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(export_path)
    except Exception as e:
        print(f"Error exporting HTML: {e}")
        return None


def export_results_csv(full_response: Dict[str, Any], candidate_name: str = "result") -> str:
    """
    Export comprehensive ranking results as CSV file including SHAP analysis
    
    Args:
        full_response: Complete response dict from ranking API
        candidate_name: Name for the export file
    
    Returns:
        Path to exported file
    """
    try:
        import csv
        
        export_dir = Path("./exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = candidate_name.replace(' ', '_').replace('/', '_')[:50]
        export_path = export_dir / f"{safe_name}_{timestamp}.csv"
        
        # Comprehensive CSV export with all available data
        rows = []
        rows.append(['Metric', 'Value'])
        rows.append(['', ''])
        
        # === CANDIDATE INFORMATION ===
        rows.append(['=== CANDIDATE INFORMATION ===', ''])
        rows.append(['Candidate Name', full_response.get('candidate_name', 'N/A')])
        rows.append(['Candidate ID', full_response.get('candidate_id', 'N/A')])
        rows.append(['Run ID', full_response.get('run_id', 'N/A')])
        rows.append(['', ''])
        
        # === MATCH SCORES ===
        rows.append(['=== MATCH SCORES ===', ''])
        rows.append(['Match Score', full_response.get('match_score', 'N/A')])
        rows.append(['Match Percentage', f"{full_response.get('match_percentage', 'N/A')}%"])
        rows.append(['Semantic Score', full_response.get('semantic_score', 'N/A')])
        rows.append(['Confidence', full_response.get('confidence', 'N/A')])
        rows.append(['', ''])
        
        # === SKILL ANALYSIS ===
        if full_response.get('skill_alignment'):
            skills = full_response['skill_alignment']
            # Ensure skills is a dict
            if isinstance(skills, dict):
                rows.append(['=== SKILL ANALYSIS ===', ''])
                present_skills = skills.get('present', [])
                missing_skills = skills.get('missing', [])
                rows.append(['Skills Present', ', '.join(present_skills) if isinstance(present_skills, list) else str(present_skills)]) 
                rows.append(['Skills Missing', ', '.join(missing_skills) if isinstance(missing_skills, list) else str(missing_skills)])
                
                # Add skill overlap if available
                if full_response.get('skill_overlap'):
                    overlap = full_response['skill_overlap']
                    if isinstance(overlap, dict):
                        rows.append(['Skill Overlap Percentage', f"{overlap.get('overlap_percentage', 'N/A')}%"])
                    elif isinstance(overlap, (int, float)):
                        rows.append(['Skill Overlap Percentage', f"{overlap}%"])
                rows.append(['', ''])
        
        # === SOCIAL WEIGHTING ===
        if full_response.get('social_weighting'):
            sw = full_response['social_weighting']
            # Ensure sw is a dict
            if isinstance(sw, dict):
                rows.append(['=== SOCIAL WEIGHTING ===', ''])
                rows.append(['Baseline Score', sw.get('baseline_prediction', 'N/A')])
                rows.append(['Social-Weighted Score', sw.get('social_weighted_prediction', 'N/A')])
                rows.append(['Delta', sw.get('delta', 'N/A')])
                rows.append(['Delta Percentage', f"{sw.get('delta_percentage', 'N/A')}%"])
                rows.append(['Weight Factor', sw.get('weight_factor', 'N/A')])
                rows.append(['Composite Social Score', sw.get('social_composite_score', 'N/A')])
                rows.append(['', ''])
        
        # === FEATURE CONTRIBUTION ANALYSIS (Interpretable ML Explanation) ===
        if full_response.get('shap_analysis'):
            shap = full_response['shap_analysis']
            # Ensure shap is a dict
            if isinstance(shap, dict):
                rows.append(['=== FEATURE CONTRIBUTION ANALYSIS ===', ''])
                rows.append(['Methodology', shap.get('methodology', 'Empirically-weighted feature importance')])
                rows.append(['', ''])
                
                # Top features (interpretable contributions)
                if shap.get('top_features'):
                    rows.append(['Top Contributing Factors:', ''])
                    rows.append(['Note:', 'These are interpretable feature contributions, not direct SHAP values'])
                    rows.append(['', ''])
                    for item in shap['top_features']:
                        try:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                feature_name = str(item[0])
                                feature_value = float(item[1])
                                direction = 'Positive ↑' if feature_value > 0 else 'Negative ↓'
                                rows.append([f"  {direction}: {feature_name}", f"{feature_value:.6f}"])
                            elif isinstance(item, dict):
                                feature_name = item.get('feature', 'Unknown')
                                feature_value = float(item.get('value', 0))
                                direction = 'Positive ↑' if feature_value > 0 else 'Negative ↓'
                                rows.append([f"  {direction}: {feature_name}", f"{feature_value:.6f}"])
                        except (ValueError, TypeError, IndexError) as e:
                            rows.append([f"  Error parsing feature", str(e)])
                    rows.append(['', ''])
                
                # Explanation text
                if shap.get('explanation'):
                    rows.append(['AI Explanation:', shap['explanation']])
                    rows.append(['', ''])
                
                # Summary stats
                summary = shap.get('summary', {})
                if summary and isinstance(summary, dict):
                    rows.append(['Summary Statistics:', ''])
                    rows.append(['  Positive Features', summary.get('num_positive_features', 'N/A')])
                    rows.append(['  Negative Features', summary.get('num_negative_features', 'N/A')])
                    rows.append(['  Total Positive Impact', f"{summary.get('total_positive_impact', 0):.6f}"])
                    rows.append(['  Total Negative Impact', f"{summary.get('total_negative_impact', 0):.6f}"])
                    rows.append(['', ''])
        
        # === VALIDATION GATES ===
        if full_response.get('gates'):
            gates = full_response['gates']
            rows.append(['=== VALIDATION GATES ===', ''])
            for gate_name, gate_status in gates.items():
                status_text = 'PASS' if gate_status else 'FAIL'
                rows.append([gate_name, status_text])
            rows.append(['', ''])
        
        # === RECOMMENDATION ===
        if full_response.get('recommendation'):
            rows.append(['=== RECOMMENDATION ===', ''])
            rows.append(['Recommendation', full_response['recommendation']])
            rows.append(['', ''])
        
        # === SOCIAL PROFILES ===
        if full_response.get('social_profiles'):
            profiles = full_response['social_profiles']
            # Ensure profiles is a dict
            if not isinstance(profiles, dict):
                profiles = {}
            
            rows.append(['=== SOCIAL PROFILES ===', ''])
            
            # Helper to safely extract any value to string
            def safe_str(value, default='Not provided'):
                if value is None:
                    return default
                if isinstance(value, list):
                    return str(value[0]) if value else default
                if isinstance(value, (int, float, bool)):
                    return str(value)
                return str(value) if value else default
            
            # LinkedIn
            rows.append(['LinkedIn URL', safe_str(profiles.get('linkedin'))])
            rows.append(['LinkedIn Present', 'Yes' if profiles.get('linkedin_present') else 'No'])
            rows.append(['LinkedIn Behavior Score', safe_str(profiles.get('linkedin_behavior_score'), 'N/A')])
            rows.append(['LinkedIn Behavior Label', safe_str(profiles.get('linkedin_behavior_label'), 'N/A')])
            rows.append(['', ''])
            
            # Facebook
            rows.append(['Facebook URL', safe_str(profiles.get('facebook'))])
            rows.append(['Facebook Present', 'Yes' if profiles.get('facebook_present') else 'No'])
            rows.append(['Facebook Behavior Score', safe_str(profiles.get('facebook_behavior_score'), 'N/A')])
            rows.append(['Facebook Behavior Label', safe_str(profiles.get('facebook_behavior_label'), 'N/A')])
            rows.append(['', ''])
            
            # GitHub
            rows.append(['GitHub URL', safe_str(profiles.get('github'))])
            rows.append(['GitHub Present', 'Yes' if profiles.get('github_present') else 'No'])
            rows.append(['', ''])
            
            # WhatsApp
            rows.append(['WhatsApp', safe_str(profiles.get('whatsapp'))])
            rows.append(['WhatsApp Verified', 'Yes' if profiles.get('whatsapp_present') else 'No'])
            rows.append(['', ''])
            
            # Overall social metrics
            rows.append(['Overall Social Presence Score', safe_str(profiles.get('social_presence_score'), 'N/A')])
            rows.append(['Social Composite Score', safe_str(profiles.get('social_composite_score'), 'N/A')])
            rows.append(['Profiles Valid Count', safe_str(profiles.get('profiles_valid'), 'N/A')])
        
        # Write comprehensive data to CSV
        with open(export_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        
        print(f"✅ CSV export successful: {export_path}")
        return str(export_path)
    except Exception as e:
        import traceback
        print(f"❌ Error exporting CSV: {e}")
        print(f"Full traceback:\n{traceback.format_exc()}")
        return None


def cleanup_old_records():
    """
    Manually cleanup old records, keeping only the latest MAX_RECORDS
    Call this if automatic cleanup isn't working
    """
    init_database()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count total records
    cursor.execute('SELECT COUNT(*) FROM search_history')
    total_records = cursor.fetchone()[0]
    
    print(f"📊 Total records in database: {total_records}")
    print(f"📌 Maximum records to keep: {MAX_RECORDS}")
    
    if total_records > MAX_RECORDS:
        records_to_delete = total_records - MAX_RECORDS
        
        # Show records that will be deleted
        cursor.execute(f'''
            SELECT id, timestamp, candidate_name 
            FROM search_history 
            ORDER BY timestamp ASC 
            LIMIT ?
        ''', (records_to_delete,))
        
        old_records = cursor.fetchall()
        print(f"\n🗑️  Deleting {records_to_delete} oldest record(s):")
        for record in old_records:
            print(f"   - ID: {record[0]}, Time: {record[1]}, Candidate: {record[2]}")
        
        # Delete oldest records
        cursor.execute(f'''
            DELETE FROM search_history 
            WHERE id IN (
                SELECT id FROM search_history 
                ORDER BY timestamp ASC 
                LIMIT ?
            )
        ''', (records_to_delete,))
        
        conn.commit()
        print(f"\n✅ Cleanup complete! Kept latest {MAX_RECORDS} records.")
    else:
        print(f"✅ No cleanup needed. Current records ({total_records}) ≤ max ({MAX_RECORDS})")
    
    # Show remaining records
    cursor.execute('''
        SELECT id, timestamp, candidate_name 
        FROM search_history 
        ORDER BY timestamp DESC
    ''')
    remaining = cursor.fetchall()
    print(f"\n📋 Remaining records ({len(remaining)}):")
    for i, record in enumerate(remaining, 1):
        print(f"   {i}. ID: {record[0]}, Time: {record[1]}, Candidate: {record[2]}")
    
    conn.close()
