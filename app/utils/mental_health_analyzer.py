# backend/app/utils/mental_health_analyzer.py
"""
Mental Health Text Analysis Module
Analyzes messages and posts for mental health indicators using:
1. Keyword detection
2. Sentiment analysis
3. Behavioral pattern tracking
"""

from datetime import datetime, timedelta
import re

# ==================== KEYWORD DICTIONARIES ====================

CRISIS_KEYWORDS = {
    'critical': {
        'keywords': [
            'suicide', 'kill myself', 'want to die', 'end my life', 'end it all',
            'better off dead', 'no reason to live', 'take my life', 'suicidal',
            'end it', 'ending it', 'want to end', 'going to end'
        ],
        'score': 45,
        'category': 'crisis'
    },
    'self_harm': {
        'keywords': [
            'self-harm', 'hurt myself', 'cut myself', 'harm myself', 'cutting',
            'self injury', 'want to hurt'
        ],
        'score': 35,
        'category': 'crisis'
    },
    'severe_distress': {
        'keywords': [
            'give up', 'no point', 'hopeless', 'worthless', 'useless',
            'failure', 'can\'t take it', 'unbearable', 'falling apart',
            'broken', 'nothing matters', 'why bother', 'can\'t go on'
        ],
        'score': 25,
        'category': 'severe'
    },
    'high_distress': {
        'keywords': [
            'depressed', 'depression', 'anxious', 'anxiety', 'panic attack',
            'overwhelmed', 'can\'t cope', 'breaking down', 'stressed out',
            'exhausted mentally', 'losing control', 'scared', 'terrified',
            'isolated', 'alone', 'lonely', 'nobody cares'
        ],
        'score': 15,
        'category': 'high'
    },
    'moderate_concern': {
        'keywords': [
            'stressed', 'worried', 'nervous', 'sad', 'upset', 'tired',
            'struggling', 'difficult time', 'hard to focus', 'can\'t sleep',
            'insomnia', 'nightmare', 'crying', 'unmotivated'
        ],
        'score': 8,
        'category': 'moderate'
    },
    'positive_indicators': {
        'keywords': [
            'feeling better', 'improving', 'grateful', 'thankful', 'hopeful',
            'optimistic', 'proud', 'accomplished', 'happy', 'excited',
            'motivated', 'energized', 'confident', 'peaceful', 'relaxed',
            'relieved', 'progress', 'getting better', 'moving forward'
        ],
        'score': -10,
        'category': 'positive'
    }
}

# Intensity multipliers
INTENSITY_PATTERNS = {
    'very': 1.3,
    'extremely': 1.5,
    'really': 1.2,
    'so': 1.2,
    'too': 1.3,
    'completely': 1.4,
    'totally': 1.4,
    'absolutely': 1.4
}

# Negation words (reduce score)
NEGATION_WORDS = ['not', 'no', 'never', 'neither', 'nobody', 'nothing', 'nowhere', 'hardly', 'barely']


# ==================== CORE ANALYSIS FUNCTION ====================

def analyze_text(text, context='message'):
    """
    Main function to analyze text for mental health indicators
    
    Args:
        text (str): The text to analyze
        context (str): 'message' or 'community_post'
    
    Returns:
        dict: Analysis results with score, level, keywords, etc.
    """
    if not text or not isinstance(text, str):
        return {
            'score': 0,
            'level': 'green',
            'keywords_detected': [],
            'sentiment': 'neutral',
            'needs_attention': False,
            'confidence': 0
        }
    
    text_lower = text.lower().strip()
    
    # Skip very short messages
    if len(text_lower) < 3:
        return {
            'score': 0,
            'level': 'green',
            'keywords_detected': [],
            'sentiment': 'neutral',
            'needs_attention': False,
            'confidence': 0
        }
    
    detected_keywords = []
    base_score = 0
    categories_found = set()
    
    # Check for keywords
    for severity_level, data in CRISIS_KEYWORDS.items():
        keywords = data['keywords']
        keyword_score = data['score']
        category = data['category']
        
        for keyword in keywords:
            if keyword in text_lower:
                # Check for negation
                is_negated = check_negation(text_lower, keyword)
                
                if is_negated:
                    # Reduce score if negated
                    keyword_score *= 0.3
                
                # Check for intensity
                intensity = check_intensity(text_lower, keyword)
                keyword_score *= intensity
                
                detected_keywords.append({
                    'keyword': keyword,
                    'category': category,
                    'severity': severity_level,
                    'negated': is_negated
                })
                
                base_score += keyword_score
                categories_found.add(category)
    
    # Apply behavioral indicators
    behavioral_score = analyze_behavioral_patterns(text_lower)
    base_score += behavioral_score
    
    # Calculate final score (cap between 0-100)
    final_score = max(0, min(100, base_score))
    
    # Determine level
    level = determine_level(final_score)
    
    # Calculate confidence (based on number of indicators found)
    confidence = calculate_confidence(detected_keywords, behavioral_score)
    
    # Determine if needs immediate attention
    needs_attention = level in ['red', 'orange'] or 'crisis' in categories_found
    
    # Get sentiment
    sentiment = get_sentiment(detected_keywords, final_score)
    
    # Generate recommendations
    recommendations = generate_recommendations(level, categories_found)
    
    return {
        'score': round(final_score, 2),
        'level': level,
        'keywords_detected': detected_keywords,
        'sentiment': sentiment,
        'needs_attention': needs_attention,
        'confidence': confidence,
        'categories': list(categories_found),
        'recommendations': recommendations,
        'context': context
    }


# ==================== HELPER FUNCTIONS ====================

def check_negation(text, keyword):
    """Check if keyword is negated (e.g., 'not depressed')"""
    # Find position of keyword
    keyword_pos = text.find(keyword)
    if keyword_pos == -1:
        return False
    
    # Check 10 characters before keyword for negation words
    before_text = text[max(0, keyword_pos - 10):keyword_pos].strip()
    
    for negation in NEGATION_WORDS:
        if negation in before_text.split():
            return True
    
    return False


def check_intensity(text, keyword):
    """Check for intensity modifiers near keyword"""
    keyword_pos = text.find(keyword)
    if keyword_pos == -1:
        return 1.0
    
    # Check 15 characters before keyword
    before_text = text[max(0, keyword_pos - 15):keyword_pos].lower()
    
    for intensifier, multiplier in INTENSITY_PATTERNS.items():
        if intensifier in before_text:
            return multiplier
    
    return 1.0


def analyze_behavioral_patterns(text):
    """Analyze text for behavioral red flags"""
    score = 0
    
    # ALL CAPS (yelling/distress)
    if len(text) > 10 and text.isupper():
        score += 5
    
    # Excessive punctuation (!!! or ???)
    if '!!!' in text or '???' in text:
        score += 3
    
    # Repetition (e.g., "help help help")
    words = text.split()
    for i in range(len(words) - 2):
        if words[i] == words[i + 1] == words[i + 2]:
            score += 5
            break
    
    # Question about self-harm or crisis
    crisis_questions = ['how to', 'ways to', 'should i']
    for q in crisis_questions:
        if q in text and any(crisis in text for crisis in ['die', 'end', 'kill', 'hurt']):
            score += 15
    
    return score


def determine_level(score):
    """Determine wellness level based on score"""
    if score >= 80:
        return 'red'      # Critical - immediate attention
    elif score >= 60:
        return 'orange'   # High concern - reach out soon
    elif score >= 30:
        return 'yellow'   # Monitor - check in
    else:
        return 'green'    # Healthy


def calculate_confidence(keywords, behavioral_score):
    """Calculate confidence in the analysis (0-100)"""
    # More indicators = higher confidence
    keyword_count = len(keywords)
    
    if keyword_count == 0 and behavioral_score == 0:
        return 0
    
    confidence = min(100, (keyword_count * 15) + (behavioral_score * 2))
    return round(confidence, 2)


def get_sentiment(keywords, score):
    """Determine overall sentiment"""
    if score >= 60:
        return 'very_negative'
    elif score >= 30:
        return 'negative'
    elif score >= 15:
        return 'slightly_negative'
    elif any(kw.get('category') == 'positive' for kw in keywords):
        return 'positive'
    else:
        return 'neutral'


def generate_recommendations(level, categories):
    """Generate action recommendations based on analysis"""
    recommendations = []
    
    if 'crisis' in categories or level == 'red':
        recommendations.append('Immediate intervention recommended')
        recommendations.append('Contact counselor or crisis helpline')
        recommendations.append('Do not leave person alone')
    elif level == 'orange':
        recommendations.append('Reach out within 24 hours')
        recommendations.append('Offer support and resources')
        recommendations.append('Schedule counseling session')
    elif level == 'yellow':
        recommendations.append('Check in with student')
        recommendations.append('Provide wellness resources')
        recommendations.append('Monitor for changes')
    else:
        recommendations.append('Continue regular wellness checks')
        recommendations.append('Encourage positive habits')
    
    return recommendations


# ==================== WELLNESS SUMMARY & TRENDS ====================

def get_wellness_summary(wellness_logs):
    """Generate summary from wellness logs"""
    if not wellness_logs:
        return {
            'total_checks': 0,
            'average_score': 0,
            'level_breakdown': {
                'red': 0,
                'orange': 0,
                'yellow': 0,
                'green': 0
            }
        }
    
    total_checks = len(wellness_logs)
    total_score = sum(log.get('score', 0) for log in wellness_logs)
    average_score = total_score / total_checks if total_checks > 0 else 0
    
    level_counts = {'red': 0, 'orange': 0, 'yellow': 0, 'green': 0}
    for log in wellness_logs:
        level = log.get('level', 'green')
        if level in level_counts:
            level_counts[level] += 1
    
    return {
        'total_checks': total_checks,
        'average_score': round(average_score, 2),
        'level_breakdown': level_counts
    }


def get_trend_analysis(wellness_logs):
    """Analyze trends in wellness data"""
    if not wellness_logs or len(wellness_logs) < 2:
        return {
            'trend': 'insufficient_data',
            'direction': 'neutral',
            'change_percentage': 0
        }
    
    # Sort by timestamp (oldest first)
    sorted_logs = sorted(wellness_logs, key=lambda x: x.get('timestamp', datetime.min))
    
    # Compare first half vs second half
    mid_point = len(sorted_logs) // 2
    first_half = sorted_logs[:mid_point]
    second_half = sorted_logs[mid_point:]
    
    avg_first = sum(log.get('score', 0) for log in first_half) / len(first_half)
    avg_second = sum(log.get('score', 0) for log in second_half) / len(second_half)
    
    change = avg_second - avg_first
    change_percentage = (change / max(avg_first, 1)) * 100
    
    # Determine trend direction
    if change > 10:
        trend = 'worsening'
        direction = 'up'
    elif change < -10:
        trend = 'improving'
        direction = 'down'
    else:
        trend = 'stable'
        direction = 'neutral'
    
    return {
        'trend': trend,
        'direction': direction,
        'change_percentage': round(change_percentage, 2),
        'current_average': round(avg_second, 2),
        'previous_average': round(avg_first, 2)
    }


# ==================== PATTERN DETECTION ====================

def detect_sudden_change(user_id, new_score, db):
    """Detect sudden changes in wellness score"""
    # Get last 5 scores
    recent_logs = list(db.mental_health_logs.find(
        {'user_id': user_id}
    ).sort('timestamp', -1).limit(5))
    
    if len(recent_logs) < 3:
        return False, None
    
    # Calculate average of previous scores
    previous_scores = [log.get('score', 0) for log in recent_logs]
    avg_previous = sum(previous_scores) / len(previous_scores)
    
    # Check if new score is significantly different
    difference = abs(new_score - avg_previous)
    
    if difference > 30:  # Sudden spike of 30+ points
        return True, {
            'type': 'sudden_increase' if new_score > avg_previous else 'sudden_decrease',
            'difference': round(difference, 2),
            'previous_average': round(avg_previous, 2),
            'new_score': new_score
        }
    
    return False, None


def detect_prolonged_distress(user_id, db):
    """Detect if user has been in distress for extended period"""
    # Get last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    recent_logs = list(db.mental_health_logs.find({
        'user_id': user_id,
        'timestamp': {'$gte': seven_days_ago}
    }))
    
    if len(recent_logs) < 5:
        return False, None
    
    # Check if majority are concerning (orange/red)
    concerning_count = sum(1 for log in recent_logs if log.get('level') in ['orange', 'red'])
    
    if concerning_count >= len(recent_logs) * 0.6:  # 60% or more concerning
        return True, {
            'type': 'prolonged_distress',
            'duration_days': 7,
            'concerning_checks': concerning_count,
            'total_checks': len(recent_logs)
        }
    
    return False, None


def detect_isolation_pattern(user_id, db):
    """Detect if user is showing isolation behavior"""
    # Check message frequency
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    
    # Recent week messages
    recent_messages = db.messages.count_documents({
        'sender_id': user_id,
        'timestamp': {'$gte': seven_days_ago}
    })
    
    # Previous week messages
    previous_messages = db.messages.count_documents({
        'sender_id': user_id,
        'timestamp': {'$gte': fourteen_days_ago, '$lt': seven_days_ago}
    })
    
    # Check community activity
    recent_posts = db.community_posts.count_documents({
        'author_id': user_id,
        'created_at': {'$gte': seven_days_ago}
    })
    
    # If significant drop in activity
    if previous_messages > 10 and recent_messages < previous_messages * 0.3:
        return True, {
            'type': 'reduced_communication',
            'previous_activity': previous_messages,
            'current_activity': recent_messages,
            'community_posts': recent_posts
        }
    
    return False, None


# ==================== EXPORT FUNCTIONS ====================

__all__ = [
    'analyze_text',
    'get_wellness_summary',
    'get_trend_analysis',
    'detect_sudden_change',
    'detect_prolonged_distress',
    'detect_isolation_pattern'
]